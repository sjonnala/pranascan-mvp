"""
POS-based rPPG processor for centre-ROI RGB traces.

Algorithm:
  1. Validate the RGB trace: frame count, timestamp order, and temporal span.
  2. Resample sparse traces onto a regular timeline. The production target is
     30 FPS; lower-rate traces are upsampled to preserve a stable filter path.
  3. Apply POS (Plane-Orthogonal-to-Skin) projection across the RGB channels to
     derive a Blood Volume Pulse (BVP) waveform.
  4. Bandpass filter the BVP to the cardiac band (0.7-4.0 Hz).
  5. Estimate the dominant cardiac frequency, then detect peaks with a spacing
     constraint derived from that frequency.
  6. Compute heart rate from the mean inter-beat interval and HRV via RMSSD.
  7. Estimate a respiratory proxy from the low-frequency envelope of the BVP.
  8. Score signal quality as cardiac-band power over total BVP power.

Input contract:
  frame_data: list of FrameSample (t_ms, r_mean, g_mean, b_mean)
  Expected acquisition: ~30 FPS RGB traces from Vision Camera.

Output:
  RppgResult (hr_bpm, hrv_ms, respiratory_rate, quality_score, flags)

Privacy:
  Only per-frame RGB means are processed - never raw face video pixels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import signal


@dataclass
class FrameSample:
    """Single video-frame colour channel means."""

    t_ms: float
    r_mean: float
    g_mean: float
    b_mean: float


@dataclass
class RppgResult:
    """rPPG-derived wellness indicator values. Not diagnostic values."""

    hr_bpm: float | None
    hrv_ms: float | None
    respiratory_rate: float | None
    quality_score: float
    flags: list[str]


@dataclass(frozen=True)
class RppgBvpSignal:
    """Intermediate POS-derived BVP waveform with timeline metadata."""

    timestamps_s: np.ndarray
    bvp: np.ndarray
    sample_rate_hz: float
    quality_score: float
    flags: list[str]


MIN_FRAMES = 60
MIN_TEMPORAL_SPAN_S = 8.0
MIN_USEFUL_FS = 30.0
UPSAMPLE_TARGET_FS = 30.0
HR_LOW_HZ = 0.7
HR_HIGH_HZ = 4.0
RESP_LOW_HZ = 0.1
RESP_HIGH_HZ = 0.5
BUTTER_ORDER = 4
MIN_SPECTRAL_QUALITY = 0.05
PEAK_DISTANCE_FRACTION = 0.65


def process_frames(frames: Sequence[FrameSample]) -> RppgResult:
    """Process RGB frame traces into HR, RMSSD, and a respiratory proxy."""
    try:
        bvp_signal = extract_bvp(frames)
    except ValueError as exc:
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=0.0,
            flags=[str(exc)],
        )

    dominant_frequency = _dominant_frequency(
        bvp_signal.bvp,
        bvp_signal.sample_rate_hz,
        HR_LOW_HZ,
        HR_HIGH_HZ,
    )
    if dominant_frequency is None:
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=bvp_signal.quality_score,
            flags=[*bvp_signal.flags, "insufficient_peaks"],
        )

    prominence = max(0.01, float(np.std(bvp_signal.bvp)) * 0.08)
    min_peak_distance = max(
        1,
        int(PEAK_DISTANCE_FRACTION * bvp_signal.sample_rate_hz / dominant_frequency),
    )
    peaks, _ = signal.find_peaks(
        bvp_signal.bvp,
        distance=min_peak_distance,
        prominence=prominence,
    )

    flags = list(bvp_signal.flags)
    if len(peaks) < 3:
        flags.append("insufficient_peaks")
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=bvp_signal.quality_score,
            flags=flags,
        )

    peak_times = bvp_signal.timestamps_s[peaks]
    ibi_s = np.diff(peak_times)

    mean_ibi_s = float(np.mean(ibi_s))
    hr_bpm = round(60.0 / mean_ibi_s, 1) if mean_ibi_s > 0 else None
    if hr_bpm is not None and not (30.0 <= hr_bpm <= 220.0):
        flags.append("hr_out_of_range")
        hr_bpm = float(np.clip(hr_bpm, 30.0, 220.0))

    hrv_ms = None
    if len(ibi_s) >= 3:
        rr_diffs_ms = np.diff(ibi_s * 1000.0)
        hrv_ms = round(float(np.sqrt(np.mean(rr_diffs_ms**2))), 2)

    respiratory_rate = _estimate_respiratory_rate(bvp_signal.bvp, bvp_signal.sample_rate_hz)

    return RppgResult(
        hr_bpm=hr_bpm,
        hrv_ms=hrv_ms,
        respiratory_rate=respiratory_rate,
        quality_score=bvp_signal.quality_score,
        flags=flags,
    )


def extract_bvp(frames: Sequence[FrameSample]) -> RppgBvpSignal:
    """Project a regularised RGB trace into a POS-derived BVP waveform."""
    flags: list[str] = []
    timestamps_s, rgb = _validate_and_materialize(frames)

    diffs = np.diff(timestamps_s)
    median_dt = float(np.median(diffs[diffs > 0]))
    sample_rate_hz = 1.0 / median_dt

    target_fs = sample_rate_hz
    if sample_rate_hz < MIN_USEFUL_FS:
        target_fs = UPSAMPLE_TARGET_FS
        flags.append("low_framerate_upsampled")

    regular_timestamps = np.arange(timestamps_s[0], timestamps_s[-1], 1.0 / target_fs)
    if regular_timestamps.size < MIN_FRAMES:
        raise ValueError("insufficient_frames")

    regular_rgb = np.column_stack(
        [np.interp(regular_timestamps, timestamps_s, rgb[:, index]) for index in range(3)]
    )
    if float(np.max(np.std(regular_rgb, axis=0))) < 1e-3:
        raise ValueError("flat_signal")

    detrended_rgb = signal.detrend(regular_rgb, axis=0)

    bvp = _extract_pos_waveform(detrended_rgb)
    bvp_std = float(np.std(bvp))
    if bvp_std < 1e-6:
        raise ValueError("flat_signal")

    normalized_bvp = bvp / bvp_std
    filtered_bvp = _bandpass_signal(normalized_bvp, target_fs, HR_LOW_HZ, HR_HIGH_HZ)
    if filtered_bvp is None:
        raise ValueError("filter_error")

    total_power = float(np.mean(normalized_bvp**2))
    cardiac_power = float(np.mean(filtered_bvp**2))
    quality_score = round(
        min(cardiac_power / total_power, 1.0) if total_power > 1e-9 else 0.0,
        4,
    )
    if quality_score < MIN_SPECTRAL_QUALITY:
        flags.append("low_signal_quality")

    return RppgBvpSignal(
        timestamps_s=regular_timestamps,
        bvp=filtered_bvp,
        sample_rate_hz=target_fs,
        quality_score=quality_score,
        flags=flags,
    )


def build_frame_samples(frame_data: list[dict]) -> list[FrameSample]:
    """Convert raw JSON frame_data entries into FrameSample objects."""
    return [
        FrameSample(
            t_ms=float(entry["t_ms"]),
            r_mean=float(entry["r_mean"]),
            g_mean=float(entry["g_mean"]),
            b_mean=float(entry["b_mean"]),
        )
        for entry in frame_data
    ]


def _validate_and_materialize(frames: Sequence[FrameSample]) -> tuple[np.ndarray, np.ndarray]:
    if len(frames) < MIN_FRAMES:
        raise ValueError("insufficient_frames")

    timestamps_s = np.array([frame.t_ms / 1000.0 for frame in frames], dtype=np.float64)
    rgb = np.column_stack(
        [
            np.array([frame.r_mean for frame in frames], dtype=np.float64),
            np.array([frame.g_mean for frame in frames], dtype=np.float64),
            np.array([frame.b_mean for frame in frames], dtype=np.float64),
        ]
    )

    diffs = np.diff(timestamps_s)
    if diffs.size == 0 or int(np.sum(diffs <= 0)) > 1:
        raise ValueError("irregular_timestamps")

    if float(timestamps_s[-1] - timestamps_s[0]) < MIN_TEMPORAL_SPAN_S:
        raise ValueError("insufficient_temporal_span")

    return timestamps_s, rgb


def _extract_pos_waveform(rgb: np.ndarray) -> np.ndarray:
    channel_mean = np.mean(rgb, axis=0, keepdims=True)
    channel_mean[channel_mean == 0.0] = 1.0
    normalized = (rgb / channel_mean) - 1.0

    s1 = normalized[:, 1] - normalized[:, 2]
    s2 = (-2.0 * normalized[:, 0]) + normalized[:, 1] + normalized[:, 2]
    s2_std = float(np.std(s2))
    alpha = float(np.std(s1) / s2_std) if s2_std > 1e-6 else 0.0

    return signal.detrend(s1 + alpha * s2)


def _bandpass_signal(
    trace: np.ndarray,
    sample_rate_hz: float,
    low_hz: float,
    high_hz: float,
) -> np.ndarray | None:
    nyq = sample_rate_hz / 2.0
    low = low_hz / nyq
    high = min(high_hz / nyq, 0.99)

    if not (0 < low < high < 1.0):
        return None

    try:
        b, a = signal.butter(BUTTER_ORDER, [low, high], btype="bandpass")
        return signal.filtfilt(b, a, trace)
    except Exception:  # noqa: BLE001
        return None


def _estimate_respiratory_rate(trace: np.ndarray, sample_rate_hz: float) -> float | None:
    respiratory_band = _bandpass_signal(trace, sample_rate_hz, RESP_LOW_HZ, RESP_HIGH_HZ)
    if respiratory_band is None:
        return None

    peaks, _ = signal.find_peaks(
        respiratory_band,
        distance=max(1, int(1.5 * sample_rate_hz)),
    )
    if len(peaks) < 2:
        return None

    mean_ibi_s = float(np.mean(np.diff(peaks / sample_rate_hz)))
    if mean_ibi_s <= 0:
        return None

    respiratory_rate = round(60.0 / mean_ibi_s, 1)
    return respiratory_rate if 5.0 <= respiratory_rate <= 45.0 else None


def _dominant_frequency(
    trace: np.ndarray,
    sample_rate_hz: float,
    low_hz: float,
    high_hz: float,
) -> float | None:
    frequencies, power = signal.periodogram(trace, fs=sample_rate_hz)
    mask = (frequencies >= low_hz) & (frequencies <= high_hz)
    if not np.any(mask):
        return None

    masked_power = power[mask]
    if masked_power.size == 0 or float(np.max(masked_power)) <= 0.0:
        return None

    return float(frequencies[mask][int(np.argmax(masked_power))])
