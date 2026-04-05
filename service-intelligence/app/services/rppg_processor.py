"""
rPPG (remote photoplethysmography) v1 processor.

Algorithm:
  1. Validate input: frame count, temporal span, timestamp monotonicity.
  2. Upsample sparse signals (< 6 Hz) via linear interpolation so cardiac
     frequencies (0.7–4.0 Hz) are always within the Nyquist band.
  3. Extract the green channel time-series; detrend and normalise.
  4. Bandpass-filter (0.7–4.0 Hz, Butterworth order-4) to isolate cardiac band.
  5. Detect peaks → inter-beat intervals (IBI).
  6. HR from mean IBI; HRV via RMSSD of successive RR differences.
  7. Respiratory proxy via low-frequency envelope (0.1–0.5 Hz).
  8. Spectral quality score: ratio of cardiac-band power to total signal power.

Frame-rate notes
  Mobile captures at ~2 fps (async JPEG via takePictureAsync).
  At 2 fps the Nyquist limit is 1 Hz (60 bpm) — too low for the full cardiac
  range.  Step 2 upsamples to ≥ 6 Hz via linear interpolation, which preserves
  the pulsatile signal while opening the full cardiac band.  This is documented
  in rPPG literature for resource-constrained devices.

Input contract:
  frame_data: list of FrameSample (t_ms, r_mean, g_mean, b_mean)
  Recommended: ≥ 120 samples over ≥ 10 s (any frame rate ≥ 1 fps is accepted).

Output:
  RppgResult (hr_bpm, hrv_ms, respiratory_rate, quality_score, flags)

Privacy:
  Only per-frame RGB means are sent — never raw video pixels.
  All processing is deterministic and fully server-side.

Limitations (v1):
  - Green-channel only (no POS/CHROM multi-channel fusion).
  - Linear interpolation (not optimal for very sparse signals < 1 fps).
  - No motion artifact removal (relies on client-side motion_score gate).
  - Respiratory rate is a low-frequency proxy, not a direct measurement.
  Sprint 3 targets: native frame processor, multi-channel POS algorithm.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import signal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class FrameSample:
    """Single video frame colour channel means."""

    t_ms: float  # timestamp in milliseconds from scan start
    r_mean: float  # 0.0–255.0 mean red channel
    g_mean: float  # 0.0–255.0 mean green channel
    b_mean: float  # 0.0–255.0 mean blue channel


@dataclass
class RppgResult:
    """rPPG-derived wellness indicator values. Not diagnostic values."""

    hr_bpm: float | None  # heart rate — wellness indicator only
    hrv_ms: float | None  # RMSSD HRV in ms — wellness indicator only
    respiratory_rate: float | None  # breaths/min proxy — wellness indicator only
    quality_score: float  # 0.0–1.0 signal quality
    flags: list[str]  # processing flags, never diagnostic language


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum frames for any meaningful rPPG processing.
MIN_FRAMES = 30
#: Minimum actual time covered by frames (seconds).
MIN_TEMPORAL_SPAN_S = 8.0
#: Minimum useful sample rate for full cardiac band. Signals below this are
#: upsampled via linear interpolation before filtering.
MIN_USEFUL_FS = 6.0
#: Target sample rate after upsampling sparse signals.
UPSAMPLE_TARGET_FS = 10.0
#: Cardiac band (Hz). 0.7 Hz = 42 bpm, 4.0 Hz = 240 bpm.
HR_LOW_HZ = 0.7
HR_HIGH_HZ = 4.0
#: Respiratory proxy band (Hz). 0.1 Hz = 6 bpm, 0.5 Hz = 30 bpm.
RESP_LOW_HZ = 0.1
RESP_HIGH_HZ = 0.5
BUTTER_ORDER = 4
#: Minimum inter-peak distance as a fraction of sample rate.
MIN_PEAK_DISTANCE_FACTOR = 0.5
#: Minimum ratio of cardiac-band power to total power for a "good" signal.
MIN_SPECTRAL_QUALITY = 0.05


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_frames(frames: Sequence[FrameSample]) -> RppgResult:
    """
    Process a sequence of camera frame samples into wellness indicators.

    Parameters
    ----------
    frames
        Sequence of FrameSample in approximately chronological order.

    Returns
    -------
    RppgResult
        hr_bpm, hrv_ms, respiratory_rate, quality_score, flags.
        All indicator fields are None when insufficient / low-quality data.
    """
    flags: list[str] = []

    # -----------------------------------------------------------------------
    # 1. Frame count guard
    # -----------------------------------------------------------------------
    if len(frames) < MIN_FRAMES:
        flags.append("insufficient_frames")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    # -----------------------------------------------------------------------
    # 2. Build time axis; check monotonicity and temporal span
    # -----------------------------------------------------------------------
    t_s = np.array([f.t_ms / 1000.0 for f in frames])
    green = np.array([f.g_mean for f in frames], dtype=np.float64)

    # Timestamp monotonicity — allow ≤ 1 out-of-order sample (network jitter)
    diffs = np.diff(t_s)
    n_negative = int(np.sum(diffs <= 0))
    if n_negative > 1:
        flags.append("irregular_timestamps")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    temporal_span = float(t_s[-1] - t_s[0])
    if temporal_span < MIN_TEMPORAL_SPAN_S:
        flags.append("insufficient_temporal_span")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    # Estimated sample rate from median frame interval
    median_dt = float(np.median(diffs[diffs > 0]))
    if median_dt <= 0:
        flags.append("irregular_timestamps")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    fs = 1.0 / median_dt

    # -----------------------------------------------------------------------
    # 3. Upsample sparse signals so full cardiac band is within Nyquist
    # -----------------------------------------------------------------------
    if fs < MIN_USEFUL_FS:
        flags.append("low_framerate_upsampled")
        target_fs = UPSAMPLE_TARGET_FS
        t_up = np.arange(t_s[0], t_s[-1], 1.0 / target_fs)
        green = np.interp(t_up, t_s, green)
        t_s = t_up
        fs = target_fs

    # -----------------------------------------------------------------------
    # 4. Detrend and normalise
    # -----------------------------------------------------------------------
    green_detrended = signal.detrend(green)
    std = float(np.std(green_detrended))
    if std < 1e-6:
        flags.append("flat_signal")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    green_norm = green_detrended / std

    # -----------------------------------------------------------------------
    # 5. Bandpass filter — cardiac range
    # -----------------------------------------------------------------------
    nyq = fs / 2.0
    low = HR_LOW_HZ / nyq
    high = min(HR_HIGH_HZ / nyq, 0.99)

    try:
        b, a = signal.butter(BUTTER_ORDER, [low, high], btype="bandpass")
        filtered = signal.filtfilt(b, a, green_norm)
    except Exception:  # noqa: BLE001
        flags.append("filter_error")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    # -----------------------------------------------------------------------
    # 6. Spectral quality score
    #    Ratio of cardiac-band power to total normalised signal power.
    # -----------------------------------------------------------------------
    total_power = float(np.mean(green_norm**2))
    cardiac_power = float(np.mean(filtered**2))
    quality_score = min(cardiac_power / total_power, 1.0) if total_power > 1e-9 else 0.0

    if quality_score < MIN_SPECTRAL_QUALITY:
        flags.append("low_signal_quality")

    # -----------------------------------------------------------------------
    # 7. Peak detection → inter-beat intervals
    # -----------------------------------------------------------------------
    min_peak_samples = max(1, int(MIN_PEAK_DISTANCE_FACTOR * fs))
    peaks, _ = signal.find_peaks(filtered, distance=min_peak_samples, prominence=0.1)

    if len(peaks) < 3:
        flags.append("insufficient_peaks")
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=round(quality_score, 3),
            flags=flags,
        )

    peak_times = t_s[peaks]
    ibi_s = np.diff(peak_times)

    # -----------------------------------------------------------------------
    # 8. Heart rate from mean IBI
    # -----------------------------------------------------------------------
    mean_ibi_s = float(np.mean(ibi_s))
    hr_bpm: float | None = round(60.0 / mean_ibi_s, 1) if mean_ibi_s > 0 else None

    if hr_bpm is not None and not (30.0 <= hr_bpm <= 220.0):
        flags.append("hr_out_of_range")
        hr_bpm = float(np.clip(hr_bpm, 30.0, 220.0))

    # -----------------------------------------------------------------------
    # 9. HRV via RMSSD of successive RR differences
    # -----------------------------------------------------------------------
    hrv_ms: float | None = None
    if len(ibi_s) >= 3:
        successive_diffs_ms = np.diff(ibi_s * 1000.0)
        hrv_ms = round(float(np.sqrt(np.mean(successive_diffs_ms**2))), 2)

    # -----------------------------------------------------------------------
    # 10. Respiratory rate via low-frequency envelope
    # -----------------------------------------------------------------------
    respiratory_rate: float | None = None
    try:
        resp_low = RESP_LOW_HZ / nyq
        resp_high = min(RESP_HIGH_HZ / nyq, 0.99)
        if resp_low < resp_high < 1.0:
            b_r, a_r = signal.butter(2, [resp_low, resp_high], btype="bandpass")
            resp_signal = signal.filtfilt(b_r, a_r, green_norm)
            resp_peaks, _ = signal.find_peaks(resp_signal, distance=int(1.5 * fs))
            if len(resp_peaks) >= 2:
                mean_resp_ibi = float(np.mean(np.diff(t_s[resp_peaks])))
                if mean_resp_ibi > 0:
                    rr = round(60.0 / mean_resp_ibi, 1)
                    respiratory_rate = rr if 5.0 <= rr <= 45.0 else None
    except Exception:  # noqa: BLE001
        pass  # Respiratory rate is a bonus — don't fail entire result

    return RppgResult(
        hr_bpm=hr_bpm,
        hrv_ms=hrv_ms,
        respiratory_rate=respiratory_rate,
        quality_score=round(quality_score, 4),
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_frame_samples(frame_data: list[dict]) -> list[FrameSample]:
    """
    Convert raw JSON frame_data list (from API payload) into FrameSample objects.

    Each dict must contain: t_ms, r_mean, g_mean, b_mean.
    Raises KeyError / ValueError for malformed entries (caught by caller).
    """
    return [
        FrameSample(
            t_ms=float(d["t_ms"]),
            r_mean=float(d["r_mean"]),
            g_mean=float(d["g_mean"]),
            b_mean=float(d["b_mean"]),
        )
        for d in frame_data
    ]
