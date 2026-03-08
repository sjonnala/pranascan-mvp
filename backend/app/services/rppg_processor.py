"""
rPPG (remote photoplethysmography) first-pass processor.

Approach:
  1. Extract the green channel from per-frame RGB mean time-series.
  2. Apply a bandpass filter (0.7–4.0 Hz → 42–240 bpm).
  3. Detect peaks in the filtered signal → inter-beat intervals (IBI).
  4. Compute HR (bpm) from mean IBI.
  5. Compute HRV via RMSSD of successive RR differences.
  6. Compute respiratory rate proxy via low-frequency envelope (0.1–0.5 Hz).

Input contract:
  frame_data: list of FrameSample (t_ms, r_mean, g_mean, b_mean)
  Nominal sample rate: ~30 fps → 900 samples for 30s scan.

Output:
  RppgResult (hr_bpm, hrv_ms, respiratory_rate, quality_score)

Privacy note:
  Only per-frame RGB means are sent — never raw video pixels.
  All processing is deterministic and fully server-side.
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
    """Single video frame colour means."""

    t_ms: float  # timestamp in milliseconds from scan start
    r_mean: float  # 0.0–255.0 mean red channel value
    g_mean: float  # 0.0–255.0 mean green channel value
    b_mean: float  # 0.0–255.0 mean blue channel value


@dataclass
class RppgResult:
    """rPPG-derived wellness indicator values."""

    hr_bpm: float | None  # heart rate in beats per minute
    hrv_ms: float | None  # RMSSD heart rate variability in milliseconds
    respiratory_rate: float | None  # breaths per minute (proxy)
    quality_score: float  # 0.0–1.0 signal quality
    flags: list[str]  # e.g. ["insufficient_frames", "low_signal_quality"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_FRAMES = 60  # minimum frames required for meaningful rPPG (~2s at 30fps)
HR_LOW_HZ = 0.7  # 42 bpm
HR_HIGH_HZ = 4.0  # 240 bpm
RESP_LOW_HZ = 0.1  # 6 bpm
RESP_HIGH_HZ = 0.5  # 30 bpm
BUTTER_ORDER = 4  # Butterworth filter order
MIN_PEAK_DISTANCE_FACTOR = 0.5  # peaks must be at least 0.5s apart
SIGNAL_QUALITY_THRESHOLD = 0.2  # normalised std threshold for usable signal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_frames(frames: Sequence[FrameSample]) -> RppgResult:
    """
    Process a sequence of camera frame samples into wellness indicators.

    Parameters
    ----------
    frames:
        Sequence of FrameSample in chronological order.

    Returns
    -------
    RppgResult with hr_bpm, hrv_ms, respiratory_rate, quality_score.
    """
    flags: list[str] = []

    if len(frames) < MIN_FRAMES:
        flags.append("insufficient_frames")
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=0.0,
            flags=flags,
        )

    # -----------------------------------------------------------------------
    # 1. Build time axis and green-channel signal
    # -----------------------------------------------------------------------
    t_s = np.array([f.t_ms / 1000.0 for f in frames])
    green = np.array([f.g_mean for f in frames], dtype=np.float64)

    # Estimate sample rate from median frame interval
    dt = np.diff(t_s)
    if len(dt) == 0 or np.median(dt) <= 0:
        flags.append("irregular_timestamps")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    fs = 1.0 / float(np.median(dt))  # Hz

    # -----------------------------------------------------------------------
    # 2. Detrend and normalise
    # -----------------------------------------------------------------------
    green_detrended = signal.detrend(green)
    std = float(np.std(green_detrended))
    if std < 1e-6:
        flags.append("flat_signal")
        return RppgResult(
            hr_bpm=None, hrv_ms=None, respiratory_rate=None, quality_score=0.0, flags=flags
        )

    green_norm = green_detrended / std

    # Signal quality: ratio of signal std to max — higher is more varied/usable
    quality_score = min(std / 20.0, 1.0)  # 20 ADU ≈ good face rPPG signal
    if quality_score < SIGNAL_QUALITY_THRESHOLD:
        flags.append("low_signal_quality")

    # -----------------------------------------------------------------------
    # 3. Bandpass filter for cardiac frequency range
    # -----------------------------------------------------------------------
    nyq = fs / 2.0
    low = HR_LOW_HZ / nyq
    high = min(HR_HIGH_HZ / nyq, 0.99)  # clamp below Nyquist

    try:
        b, a = signal.butter(BUTTER_ORDER, [low, high], btype="bandpass")
        filtered = signal.filtfilt(b, a, green_norm)
    except Exception:  # noqa: BLE001
        flags.append("filter_error")
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=quality_score,
            flags=flags,
        )

    # -----------------------------------------------------------------------
    # 4. Peak detection → inter-beat intervals
    # -----------------------------------------------------------------------
    min_peak_samples = max(1, int(MIN_PEAK_DISTANCE_FACTOR * fs))
    peaks, _ = signal.find_peaks(filtered, distance=min_peak_samples, prominence=0.1)

    if len(peaks) < 2:
        flags.append("insufficient_peaks")
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=quality_score,
            flags=flags,
        )

    # IBI in seconds
    peak_times = t_s[peaks]
    ibi_s = np.diff(peak_times)

    # -----------------------------------------------------------------------
    # 5. HR from mean IBI
    # -----------------------------------------------------------------------
    mean_ibi_s = float(np.mean(ibi_s))
    hr_bpm = round(60.0 / mean_ibi_s, 1) if mean_ibi_s > 0 else None

    # Sanity check
    if hr_bpm is not None and not (30 <= hr_bpm <= 220):
        flags.append("hr_out_of_range")
        hr_bpm = float(np.clip(hr_bpm, 30, 220))

    # -----------------------------------------------------------------------
    # 6. HRV via RMSSD
    # -----------------------------------------------------------------------
    hrv_ms: float | None = None
    if len(ibi_s) >= 2:
        successive_diffs = np.diff(ibi_s * 1000.0)  # ms
        hrv_ms = round(float(np.sqrt(np.mean(successive_diffs**2))), 2)

    # -----------------------------------------------------------------------
    # 7. Respiratory rate via low-frequency envelope of rPPG
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
                resp_times = t_s[resp_peaks]
                mean_resp_ibi = float(np.mean(np.diff(resp_times)))
                if mean_resp_ibi > 0:
                    respiratory_rate = round(60.0 / mean_resp_ibi, 1)
                    if not (5 <= respiratory_rate <= 45):
                        respiratory_rate = None
    except Exception:  # noqa: BLE001
        pass  # Respiratory rate is a bonus; don't fail the whole result

    return RppgResult(
        hr_bpm=hr_bpm,
        hrv_ms=hrv_ms,
        respiratory_rate=respiratory_rate,
        quality_score=round(quality_score, 3),
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_frame_samples(frame_data: list[dict]) -> list[FrameSample]:
    """
    Convert raw JSON frame_data list (from API payload) into FrameSample objects.

    Each dict must have: t_ms, r_mean, g_mean, b_mean.
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
