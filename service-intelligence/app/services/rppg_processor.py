"""
POS-based rPPG processor for centre-ROI RGB traces.

Algorithm:
  1. Validate the RGB trace: frame count, timestamp order, and temporal span.
     Isolated duplicate / out-of-order millisecond timestamps (typical of a
     JS-thread stall draining queued samples) are repaired instead of
     rejecting the scan; the scan is rejected only when more than
     ``MAX_CORRUPTED_TIMESTAMP_FRACTION`` of frames are corrupted.
  2. Resample sparse traces onto a regular timeline. The production target is
     30 FPS; lower-rate traces are upsampled to preserve a stable filter path.
  3. Apply windowed POS (Plane-Orthogonal-to-Skin, Wang et al. 2017,
     Algorithm 1): temporal normalisation and the alpha projection are done
     per short window (default 1.6 s) and overlap-added, so auto-exposure and
     white-balance changes are normalised locally instead of over 30 s.
  4. Bandpass filter the BVP to the cardiac band (0.7-4.0 Hz).
  5. Estimate the dominant cardiac frequency and a spectral SNR around it.
  6. Abstain when spectral quality or SNR is below threshold: return
     ``hr_bpm=None`` / ``hrv_ms=None`` with explicit abstention flags rather
     than reporting a heart rate from noise.
  7. Otherwise detect peaks with a spacing constraint derived from the
     dominant frequency and compute heart rate from the mean inter-beat
     interval. HRV (RMSSD) is withheld when the effective delivered frame
     rate is below ``MIN_HRV_FPS``.
  8. Estimate a respiratory proxy from the low-frequency envelope of the BVP.

Input contract:
  frame_data: list of FrameSample (t_ms, r_mean, g_mean, b_mean)
  Expected acquisition: ~30 FPS RGB traces from Vision Camera.

Output:
  RppgResult (hr_bpm, hrv_ms, respiratory_rate, quality_score, flags,
  snr_db, effective_fps, abstained, abstention_reason)

Privacy:
  Only per-frame RGB means are processed - never raw face video pixels.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
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
    # Spectral SNR (dB) around the dominant cardiac frequency; None when the
    # trace never reached spectral analysis (validation / filter failures).
    snr_db: float | None = None
    # Frame rate actually delivered by the camera: (frames - 1) / span.
    effective_fps: float | None = None
    # True when the processor declined to report a heart rate because the
    # spectral evidence for a pulse was too weak ("no pulse" abstention).
    abstained: bool = False
    abstention_reason: str | None = None


@dataclass(frozen=True)
class RppgBvpSignal:
    """Intermediate POS-derived BVP waveform with timeline metadata."""

    timestamps_s: np.ndarray
    bvp: np.ndarray
    sample_rate_hz: float
    quality_score: float
    flags: list[str]
    effective_fps: float | None = None


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

# Windowed POS (Wang et al. 2017): window length in seconds. 1.6 s is the
# paper's default (about one cardiac cycle at 40 BPM). Configurable per call.
POS_WINDOW_S = 1.6

# "No pulse" abstention: minimum spectral SNR in dB, measured as power within
# +/-SNR_FUNDAMENTAL_HALF_WIDTH_HZ of the dominant frequency and
# +/-SNR_HARMONIC_HALF_WIDTH_HZ of its first harmonic, over the remaining
# power in the 0.7-4.0 Hz band (de Haan & Jeanne 2013 style). Chosen from the
# Monte-Carlo calibration in tests/test_phase0_budget_phone_fixes.py: pure
# noise sits well below it, clean and moderately noisy pulses well above.
MIN_SNR_DB = -3.0
SNR_FUNDAMENTAL_HALF_WIDTH_HZ = 0.1
SNR_HARMONIC_HALF_WIDTH_HZ = 0.2

# Timestamp repair: reject the scan only when more than this fraction of the
# frames had duplicate or out-of-order timestamps.
MAX_CORRUPTED_TIMESTAMP_FRACTION = 0.05

# HRV (RMSSD) needs beat timing finer than ~40 ms; withhold it below 25 FPS.
MIN_HRV_FPS = 25.0


def process_frames(
    frames: Sequence[FrameSample],
    *,
    pos_window_s: float = POS_WINDOW_S,
    min_snr_db: float = MIN_SNR_DB,
    min_spectral_quality: float = MIN_SPECTRAL_QUALITY,
) -> RppgResult:
    """Process RGB frame traces into HR, RMSSD, and a respiratory proxy.

    Returns ``hr_bpm=None`` with ``abstained=True`` when the spectral evidence
    for a pulse is below ``min_spectral_quality`` or ``min_snr_db``.
    """
    try:
        bvp_signal = extract_bvp(frames, pos_window_s=pos_window_s)
    except ValueError as exc:
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=0.0,
            flags=[str(exc)],
        )

    effective_fps = bvp_signal.effective_fps
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
            effective_fps=effective_fps,
        )

    snr_db = _spectral_snr_db(bvp_signal.bvp, bvp_signal.sample_rate_hz, dominant_frequency)
    flags = list(bvp_signal.flags)

    abstention_reasons: list[str] = []
    if bvp_signal.quality_score < min_spectral_quality:
        abstention_reasons.append("low_spectral_quality")
    if snr_db < min_snr_db:
        abstention_reasons.append("low_spectral_snr")
    if abstention_reasons:
        flags.extend(
            [
                "hr_abstained",
                "no_reliable_pulse",
                *(f"abstain_reason:{reason}" for reason in abstention_reasons),
            ]
        )
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=bvp_signal.quality_score,
            flags=list(dict.fromkeys(flags)),
            snr_db=snr_db,
            effective_fps=effective_fps,
            abstained=True,
            abstention_reason=abstention_reasons[0],
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

    if len(peaks) < 3:
        flags.append("insufficient_peaks")
        return RppgResult(
            hr_bpm=None,
            hrv_ms=None,
            respiratory_rate=None,
            quality_score=bvp_signal.quality_score,
            flags=flags,
            snr_db=snr_db,
            effective_fps=effective_fps,
        )

    peak_times = bvp_signal.timestamps_s[peaks]
    ibi_s = np.diff(peak_times)

    mean_ibi_s = float(np.mean(ibi_s))
    hr_bpm = round(60.0 / mean_ibi_s, 1) if mean_ibi_s > 0 else None
    if hr_bpm is not None and not (30.0 <= hr_bpm <= 220.0):
        flags.append("hr_out_of_range")
        hr_bpm = float(np.clip(hr_bpm, 30.0, 220.0))

    hrv_ms = None
    if effective_fps is not None and effective_fps < MIN_HRV_FPS:
        flags.append("hrv_withheld_low_fps")
    elif len(ibi_s) >= 3:
        rr_diffs_ms = np.diff(ibi_s * 1000.0)
        hrv_ms = round(float(np.sqrt(np.mean(rr_diffs_ms**2))), 2)

    respiratory_rate = _estimate_respiratory_rate(bvp_signal.bvp, bvp_signal.sample_rate_hz)

    return RppgResult(
        hr_bpm=hr_bpm,
        hrv_ms=hrv_ms,
        respiratory_rate=respiratory_rate,
        quality_score=bvp_signal.quality_score,
        flags=flags,
        snr_db=snr_db,
        effective_fps=effective_fps,
    )


def _detrend_linear(data: np.ndarray) -> np.ndarray:
    """Stable linear detrending that avoids lapack division by zero bugs on synthetic signals."""
    n_samples = data.shape[0]
    x_centered = np.arange(n_samples, dtype=np.float64) - (n_samples - 1) / 2.0
    sum_x2 = np.sum(x_centered**2)

    detrended = np.zeros_like(data)
    if data.ndim == 1:
        slope = np.sum(x_centered * data) / sum_x2
        trend = slope * x_centered + np.mean(data)
        return data - trend

    for i in range(data.shape[1]):
        y = data[:, i]
        y_mean = np.mean(y)
        slope = np.sum(x_centered * (y - y_mean)) / sum_x2
        trend = slope * x_centered + y_mean
        detrended[:, i] = y - trend

    return detrended


def extract_bvp(
    frames: Sequence[FrameSample],
    *,
    pos_window_s: float = POS_WINDOW_S,
) -> RppgBvpSignal:
    """Project a regularised RGB trace into a windowed-POS BVP waveform."""
    flags: list[str] = []
    timestamps_s, rgb, timestamp_flags = _validate_and_materialize(frames)
    flags.extend(timestamp_flags)

    span_s = float(timestamps_s[-1] - timestamps_s[0])
    effective_fps = round((timestamps_s.size - 1) / span_s, 2) if span_s > 0 else None

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

    if "low_framerate_upsampled" in flags:
        from scipy.interpolate import CubicSpline

        regular_rgb = np.column_stack(
            [CubicSpline(timestamps_s, rgb[:, index])(regular_timestamps) for index in range(3)]
        )
    else:
        regular_rgb = np.column_stack(
            [np.interp(regular_timestamps, timestamps_s, rgb[:, index]) for index in range(3)]
        )
    if float(np.max(np.std(regular_rgb, axis=0))) < 1e-3:
        raise ValueError("flat_signal")

    # Windowed POS needs the raw (DC-bearing) channels: its per-window
    # temporal normalisation divides by the window mean. The previous global
    # path divided a linearly detrended (zero-mean) trace by its mean.
    bvp = _detrend_linear(_extract_pos_waveform(regular_rgb, target_fs, pos_window_s))
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
        effective_fps=effective_fps,
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


def _validate_and_materialize(
    frames: Sequence[FrameSample],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
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

    if timestamps_s.size < 2:
        raise ValueError("irregular_timestamps")

    timestamps_s, rgb, corrupted = _repair_timestamps(timestamps_s, rgb)
    if corrupted > MAX_CORRUPTED_TIMESTAMP_FRACTION * len(frames):
        raise ValueError("irregular_timestamps")

    flags: list[str] = []
    if corrupted > 0:
        flags.append("duplicate_timestamps_repaired")

    if timestamps_s.size < MIN_FRAMES:
        raise ValueError("insufficient_frames")

    if float(timestamps_s[-1] - timestamps_s[0]) < MIN_TEMPORAL_SPAN_S:
        raise ValueError("insufficient_temporal_span")

    return timestamps_s, rgb, flags


def _repair_timestamps(
    timestamps_s: np.ndarray,
    rgb: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Repair isolated JS-stall timestamp glitches.

    Mobile stamps samples on the JS thread; a stall makes queued samples drain
    back-to-back with identical (or, rarely, earlier) millisecond stamps.

    - Out-of-order samples (stamp earlier than an already accepted sample) are
      dropped.
    - Runs of identical stamps are kept and nudged: the k samples of a run are
      spread evenly between the run's stamp and the next distinct stamp (or by
      the median frame interval at the end of the trace).

    Returns the repaired arrays and the number of corrupted frames (dropped
    plus nudged), so the caller can reject traces that are mostly corrupt.
    """
    keep = np.ones(timestamps_s.size, dtype=bool)
    running_max = -math.inf
    for index, stamp in enumerate(timestamps_s):
        if stamp < running_max:
            keep[index] = False
        else:
            running_max = stamp
    dropped = int(np.sum(~keep))
    timestamps_s = timestamps_s[keep].copy()
    rgb = rgb[keep]

    diffs = np.diff(timestamps_s)
    if not np.any(diffs == 0):
        return timestamps_s, rgb, dropped

    positive = diffs[diffs > 0]
    if positive.size == 0:
        raise ValueError("irregular_timestamps")
    median_dt = float(np.median(positive))

    nudged = 0
    start = 0
    count = timestamps_s.size
    while start < count:
        end = start
        while end + 1 < count and timestamps_s[end + 1] == timestamps_s[start]:
            end += 1
        run_length = end - start + 1
        if run_length > 1:
            nudged += run_length - 1
            base = timestamps_s[start]
            step = (timestamps_s[end + 1] - base) / run_length if end + 1 < count else median_dt
            for offset in range(1, run_length):
                timestamps_s[start + offset] = base + offset * step
        start = end + 1

    return timestamps_s, rgb, dropped + nudged


def _extract_pos_waveform(
    rgb: np.ndarray,
    sample_rate_hz: float = UPSAMPLE_TARGET_FS,
    window_s: float = POS_WINDOW_S,
) -> np.ndarray:
    """Windowed POS with overlap-add (Wang et al. 2017, Algorithm 1).

    For every window of ``window_s`` seconds (stride one sample):
      Cn = C / mean(C)                 temporal normalisation per window
      S1 = Gn - Bn,  S2 = Gn + Bn - 2Rn  projection onto the POS plane
      h  = S1 + (std(S1) / std(S2)) * S2
      H[window] += h - mean(h)         overlap-add

    ``sample_rate_hz`` defaults to ``UPSAMPLE_TARGET_FS`` so existing callers
    that pass only ``rgb`` keep working.
    """
    if window_s <= 0:
        raise ValueError("invalid_pos_window")

    sample_count = rgb.shape[0]
    window_len = max(2, int(math.ceil(window_s * sample_rate_hz)))
    window_len = min(window_len, sample_count)

    windows = sliding_window_view(rgb, window_len, axis=0)  # (n_windows, 3, window_len)
    window_means = np.mean(windows, axis=2, keepdims=True)
    window_means = np.where(np.abs(window_means) < 1e-9, 1.0, window_means)
    normalized = windows / window_means

    s1 = normalized[:, 1, :] - normalized[:, 2, :]
    s2 = (-2.0 * normalized[:, 0, :]) + normalized[:, 1, :] + normalized[:, 2, :]
    s1_std = np.std(s1, axis=1)
    s2_std = np.std(s2, axis=1)
    alpha = np.divide(s1_std, s2_std, out=np.zeros_like(s1_std), where=s2_std > 1e-12)

    h = s1 + alpha[:, None] * s2
    h = h - np.mean(h, axis=1, keepdims=True)

    n_windows = h.shape[0]
    indices = np.arange(n_windows)[:, None] + np.arange(window_len)[None, :]
    pulse = np.zeros(sample_count, dtype=np.float64)
    np.add.at(pulse, indices.ravel(), h.ravel())
    return pulse


def _spectral_snr_db(trace: np.ndarray, sample_rate_hz: float, fundamental_hz: float) -> float:
    """Spectral SNR (dB) of a cardiac-band trace around a fundamental frequency.

    Signal = power within +/-0.1 Hz of the fundamental and +/-0.2 Hz of its
    first harmonic; noise = all other power in the 0.7-4.0 Hz band.
    """
    frequencies, power = signal.periodogram(trace, fs=sample_rate_hz)
    band = (frequencies >= HR_LOW_HZ) & (frequencies <= HR_HIGH_HZ)
    signal_mask = band & (
        (np.abs(frequencies - fundamental_hz) <= SNR_FUNDAMENTAL_HALF_WIDTH_HZ)
        | (np.abs(frequencies - 2.0 * fundamental_hz) <= SNR_HARMONIC_HALF_WIDTH_HZ)
    )
    noise_mask = band & ~signal_mask
    signal_power = float(np.sum(power[signal_mask]))
    noise_power = float(np.sum(power[noise_mask]))
    if signal_power <= 0.0:
        return -math.inf
    if noise_power <= 1e-30:
        return math.inf
    return round(10.0 * math.log10(signal_power / noise_power), 2)


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
    """Return the dominant *fundamental* cardiac frequency using sub-harmonic summation.

    Plain periodogram peak-picking often locks onto the 2nd or 3rd harmonic of
    the true cardiac frequency, especially after POS projection on low-frame-
    rate upsampled traces.  Sub-harmonic summation weights each candidate
    frequency by the sum of power at its first few harmonics so that the true
    fundamental scores higher than any single harmonic peak.
    """
    frequencies, power = signal.periodogram(trace, fs=sample_rate_hz)
    mask = (frequencies >= low_hz) & (frequencies <= high_hz)
    if not np.any(mask):
        return None

    masked_freqs = frequencies[mask]
    masked_power = power[mask]
    if masked_power.size == 0 or float(np.max(masked_power)) <= 0.0:
        return None

    # Sub-harmonic summation: for each candidate fundamental f, accumulate
    # the spectral power at f, 2f, 3f (where they exist within the Nyquist
    # limit).  This gives the true fundamental a scoring boost because its
    # harmonics contribute, while a harmonic's "harmonics" fall outside the
    # cardiac band or are much weaker.
    #
    # We weight each harmonic by 1/h so the fundamental power dominates the
    # score.  Without this, SHS may prefer a sub-harmonic whose 2nd harmonic
    # happens to coincide with the actual peak (e.g. choosing 50 BPM over
    # 100 BPM because the 2nd harmonic of 50 is the 100 BPM peak).
    n_harmonics = 3
    shs_score = np.zeros_like(masked_power)
    freq_resolution = float(frequencies[1] - frequencies[0]) if len(frequencies) > 1 else 1.0
    max_power = float(np.max(masked_power))

    for idx, f0 in enumerate(masked_freqs):
        # Require the candidate fundamental itself to have meaningful power;
        # otherwise a low-power sub-harmonic can win just because its
        # harmonics align with strong peaks.
        if masked_power[idx] < max_power * 0.05:
            continue
        total = 0.0
        for h in range(1, n_harmonics + 1):
            harmonic_freq = f0 * h
            # Find the nearest bin in the full frequency array
            bin_idx = int(round(harmonic_freq / freq_resolution))
            if 0 <= bin_idx < len(power):
                total += power[bin_idx] / h
        shs_score[idx] = total

    return float(masked_freqs[int(np.argmax(shs_score))])
