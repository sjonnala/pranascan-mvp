"""Contact-PPG morphology processor for Weekly Deep Dive scans."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import signal

from app.services.rppg_processor import FrameSample

MIN_FRAMES = 300
MIN_TEMPORAL_SPAN_S = 20.0
TARGET_FS = 60.0
MIN_USEFUL_FS = 30.0
HR_LOW_HZ = 0.7
HR_HIGH_HZ = 5.0


@dataclass(frozen=True)
class MorphologyResult:
    hr_bpm: float | None
    hrv_ms: float | None
    stiffness_index: float | None
    quality_score: float
    flags: list[str]


def process_morphology_frames(
    frames: Sequence[FrameSample],
    user_height_cm: float | None,
) -> MorphologyResult:
    try:
        timestamps_s, pulse, sample_rate_hz, quality_score, flags = _prepare_signal(frames)
    except ValueError as exc:
        return MorphologyResult(
            hr_bpm=None,
            hrv_ms=None,
            stiffness_index=None,
            quality_score=0.0,
            flags=[str(exc)],
        )

    peaks = _detect_peaks(pulse, sample_rate_hz)
    if len(peaks) < 3:
        return MorphologyResult(
            hr_bpm=None,
            hrv_ms=None,
            stiffness_index=None,
            quality_score=quality_score,
            flags=[*flags, "insufficient_peaks"],
        )

    peak_times = timestamps_s[peaks]
    ibi_s = np.diff(peak_times)
    hr_bpm = round(float(60.0 / np.mean(ibi_s)), 1)
    hrv_ms = None
    if len(ibi_s) >= 3:
        rr_diffs_ms = np.diff(ibi_s * 1000.0)
        hrv_ms = round(float(np.sqrt(np.mean(rr_diffs_ms**2))), 2)

    stiffness_index = None
    morphology_flags = list(flags)
    if user_height_cm is None:
        morphology_flags.append("height_required_for_stiffness_index")
    else:
        average_cycle, cycle_fs = _average_cycle(pulse, peaks, sample_rate_hz)
        if average_cycle is None:
            morphology_flags.append("insufficient_cycles_for_morphology")
        else:
            stiffness_index = _compute_stiffness_index(average_cycle, cycle_fs, user_height_cm)
            if stiffness_index is None:
                morphology_flags.append("morphology_peaks_not_found")

    return MorphologyResult(
        hr_bpm=hr_bpm,
        hrv_ms=hrv_ms,
        stiffness_index=stiffness_index,
        quality_score=quality_score,
        flags=morphology_flags,
    )


def _prepare_signal(
    frames: Sequence[FrameSample],
) -> tuple[np.ndarray, np.ndarray, float, float, list[str]]:
    if len(frames) < MIN_FRAMES:
        raise ValueError("insufficient_frames")

    timestamps_s = np.array([frame.t_ms / 1000.0 for frame in frames], dtype=np.float64)
    diffs = np.diff(timestamps_s)
    if diffs.size == 0 or np.any(diffs <= 0):
        raise ValueError("irregular_timestamps")
    if float(timestamps_s[-1] - timestamps_s[0]) < MIN_TEMPORAL_SPAN_S:
        raise ValueError("insufficient_temporal_span")

    raw_signal = np.array([frame.r_mean for frame in frames], dtype=np.float64)
    if float(np.std(raw_signal)) < 1e-3:
        raise ValueError("flat_signal")

    native_fs = 1.0 / float(np.median(diffs))
    if native_fs < MIN_USEFUL_FS:
        raise ValueError("insufficient_framerate")

    target_fs = max(native_fs, TARGET_FS)
    regular_timestamps = np.arange(timestamps_s[0], timestamps_s[-1], 1.0 / target_fs)
    regular_signal = np.interp(regular_timestamps, timestamps_s, raw_signal)
    detrended = signal.detrend(regular_signal)

    filtered = _bandpass_signal(detrended, target_fs, HR_LOW_HZ, HR_HIGH_HZ)
    if filtered is None:
        raise ValueError("filter_error")

    filtered_std = float(np.std(filtered))
    if filtered_std < 1e-6:
        raise ValueError("flat_signal")

    normalized = filtered / filtered_std
    total_power = float(np.mean(detrended**2))
    cardiac_power = float(np.mean(normalized**2))
    quality_score = round(
        min(cardiac_power / total_power, 1.0) if total_power > 1e-9 else 0.0,
        4,
    )
    flags: list[str] = []
    if quality_score < 0.05:
        flags.append("low_signal_quality")

    return regular_timestamps, normalized, target_fs, quality_score, flags


def _bandpass_signal(
    values: np.ndarray,
    sample_rate_hz: float,
    low_hz: float,
    high_hz: float,
) -> np.ndarray | None:
    nyquist = sample_rate_hz / 2.0
    low = low_hz / nyquist
    high = high_hz / nyquist
    if not 0 < low < high < 1:
        return None

    b, a = signal.butter(4, [low, high], btype="bandpass")
    padlen = min(len(values) - 1, 3 * (max(len(a), len(b)) - 1))
    if padlen <= 0:
        return None

    return signal.filtfilt(b, a, values, padlen=padlen)


def _detect_peaks(pulse: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    dominant_frequency = _dominant_frequency(pulse, sample_rate_hz)
    if dominant_frequency is None:
        return np.array([], dtype=int)

    prominence = max(0.05, float(np.std(pulse)) * 0.08)
    min_distance = max(1, int((sample_rate_hz / dominant_frequency) * 0.65))
    peaks, _ = signal.find_peaks(pulse, distance=min_distance, prominence=prominence)
    return peaks


def _dominant_frequency(pulse: np.ndarray, sample_rate_hz: float) -> float | None:
    frequencies, spectrum = signal.periodogram(pulse, fs=sample_rate_hz)
    mask = (frequencies >= HR_LOW_HZ) & (frequencies <= HR_HIGH_HZ)
    if not np.any(mask):
        return None

    band_frequencies = frequencies[mask]
    band_spectrum = spectrum[mask]
    if band_spectrum.size == 0 or np.allclose(band_spectrum, 0.0):
        return None

    return float(band_frequencies[int(np.argmax(band_spectrum))])


def _average_cycle(
    pulse: np.ndarray,
    peaks: np.ndarray,
    sample_rate_hz: float,
) -> tuple[np.ndarray | None, float]:
    cycles: list[np.ndarray] = []
    target_points = 200

    for start_index, end_index in zip(peaks[:-1], peaks[1:], strict=False):
        segment = pulse[start_index:end_index + 1]
        if len(segment) < 10:
            continue

        source_x = np.linspace(0.0, 1.0, len(segment))
        target_x = np.linspace(0.0, 1.0, target_points)
        cycles.append(np.interp(target_x, source_x, segment))

    if len(cycles) < 2:
        return None, float(target_points)

    average_cycle = np.mean(np.vstack(cycles), axis=0)
    mean_cycle_seconds = float(np.mean(np.diff(peaks))) / sample_rate_hz
    cycle_fs = target_points / mean_cycle_seconds if mean_cycle_seconds > 1e-6 else float(target_points)
    return average_cycle, cycle_fs


def _compute_stiffness_index(
    average_cycle: np.ndarray,
    cycle_fs: float,
    user_height_cm: float,
) -> float | None:
    window_length = min(len(average_cycle) - 1 if len(average_cycle) % 2 == 0 else len(average_cycle), 21)
    if window_length < 7:
        return None
    if window_length % 2 == 0:
        window_length -= 1

    smoothed_cycle = signal.savgol_filter(average_cycle, window_length=window_length, polyorder=3)
    apg = signal.savgol_filter(
        smoothed_cycle,
        window_length=window_length,
        polyorder=3,
        deriv=2,
        delta=1.0 / cycle_fs,
    )

    maxima, _ = signal.find_peaks(apg, prominence=max(0.01, float(np.std(apg)) * 0.1))
    minima, _ = signal.find_peaks(-apg, prominence=max(0.01, float(np.std(apg)) * 0.1))

    extrema = sorted(
        [(int(index), "max") for index in maxima] + [(int(index), "min") for index in minima],
        key=lambda item: item[0],
    )
    if len(extrema) < 4:
        return None

    a_index = None
    d_index = None
    state = "a"
    for index, kind in extrema:
        if state == "a" and kind == "max":
            a_index = index
            state = "b"
        elif state == "b" and kind == "min" and a_index is not None and index > a_index:
            state = "c"
        elif state == "c" and kind == "max" and a_index is not None and index > a_index:
            state = "d"
        elif state == "d" and kind == "min" and a_index is not None and index > a_index:
            d_index = index
            break

    if a_index is None or d_index is None or d_index <= a_index:
        return None

    delta_t_s = (d_index - a_index) / cycle_fs
    if delta_t_s <= 1e-6:
        return None

    height_m = user_height_cm / 100.0
    return round(height_m / delta_t_s, 3)
