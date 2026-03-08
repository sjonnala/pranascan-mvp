"""
Voice DSP first-pass processor — jitter, shimmer, and SNR from audio samples.

Approach:
  1. Input: amplitude envelope samples (normalised -1.0 to 1.0) at 4410 Hz.
  2. F0 estimation via zero-crossing rate (proxy for voiced segment period).
  3. Jitter: cycle-to-cycle period variation = std(period) / mean(period) × 100.
  4. Shimmer: cycle-to-cycle amplitude variation = std(amp) / mean(amp) × 100.
  5. SNR proxy: ratio of RMS voiced energy to RMS silence energy.

Input contract:
  audio_samples: list of float in [-1.0, 1.0], sample rate = 4410 Hz.
  A 5-second recording → 22,050 samples (downsampled from 44100 Hz by client).

Output:
  VoiceResult (jitter_pct, shimmer_pct, snr_db, voiced_fraction, flags)

Privacy note:
  Only amplitude samples are sent — no identifiable voice characteristics.
  Processing is fully server-side and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 4410  # Hz (downsampled from 44100)
MIN_SAMPLES = SAMPLE_RATE * 2  # at least 2 seconds
SILENCE_THRESHOLD = 0.01  # amplitude below this is silence
F0_LOW_HZ = 80.0  # minimum F0 — lowest typical voice fundamental
F0_HIGH_HZ = 400.0  # maximum F0 — highest typical voice fundamental
MIN_VOICED_FRACTION = 0.5  # >50% of recording must be voiced
NOISE_FLOOR_DB = -60.0  # dB floor for SNR calculation


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class VoiceResult:
    """Voice DSP-derived wellness indicator values."""

    jitter_pct: float | None  # cycle-to-cycle period variation (%)
    shimmer_pct: float | None  # cycle-to-cycle amplitude variation (%)
    snr_db: float | None  # signal-to-noise ratio in dB
    voiced_fraction: float  # fraction of recording that is voiced
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_audio(samples: Sequence[float]) -> VoiceResult:
    """
    Process normalised audio amplitude samples into voice wellness indicators.

    Parameters
    ----------
    samples:
        Sequence of float in [-1.0, 1.0] at SAMPLE_RATE Hz.

    Returns
    -------
    VoiceResult with jitter_pct, shimmer_pct, snr_db.
    """
    flags: list[str] = []
    arr = np.array(samples, dtype=np.float64)

    if len(arr) < MIN_SAMPLES:
        flags.append("insufficient_samples")
        return VoiceResult(
            jitter_pct=None,
            shimmer_pct=None,
            snr_db=None,
            voiced_fraction=0.0,
            flags=flags,
        )

    # -----------------------------------------------------------------------
    # 1. Detect voiced vs silence frames (20ms frames)
    # -----------------------------------------------------------------------
    frame_size = int(SAMPLE_RATE * 0.02)  # 20ms frames
    num_frames = len(arr) // frame_size
    frame_rms = np.array(
        [
            float(np.sqrt(np.mean(arr[i * frame_size : (i + 1) * frame_size] ** 2)))
            for i in range(num_frames)
        ]
    )

    voiced_mask = frame_rms > SILENCE_THRESHOLD
    voiced_fraction = float(np.mean(voiced_mask))

    if voiced_fraction < MIN_VOICED_FRACTION:
        flags.append("insufficient_voiced_content")

    # -----------------------------------------------------------------------
    # 2. SNR proxy: RMS voiced / RMS silence
    # -----------------------------------------------------------------------
    voiced_rms_vals = frame_rms[voiced_mask]
    silence_rms_vals = frame_rms[~voiced_mask]

    snr_db: float | None = None
    if len(voiced_rms_vals) > 0:
        voiced_rms = float(np.mean(voiced_rms_vals))
        if len(silence_rms_vals) > 0 and float(np.mean(silence_rms_vals)) > 1e-8:
            noise_rms = float(np.mean(silence_rms_vals))
            snr_db = round(20.0 * math.log10(voiced_rms / noise_rms), 1)
        else:
            snr_db = 40.0  # No detectable silence → very high SNR

    if snr_db is not None and snr_db < 10.0:
        flags.append("high_noise")

    # -----------------------------------------------------------------------
    # 3. Extract voiced segment for F0 analysis
    # -----------------------------------------------------------------------
    if voiced_fraction < MIN_VOICED_FRACTION or len(voiced_rms_vals) < 5:
        return VoiceResult(
            jitter_pct=None,
            shimmer_pct=None,
            snr_db=snr_db,
            voiced_fraction=voiced_fraction,
            flags=flags,
        )

    # Work on voiced frames only
    voiced_frames_idx = np.where(voiced_mask)[0]
    voiced_samples = np.concatenate(
        [arr[i * frame_size : (i + 1) * frame_size] for i in voiced_frames_idx]
    )

    # -----------------------------------------------------------------------
    # 4. F0 estimation via autocorrelation (more robust than ZCR)
    # -----------------------------------------------------------------------
    # Bandpass filter voiced signal to F0 range
    nyq = SAMPLE_RATE / 2.0
    low = F0_LOW_HZ / nyq
    high = min(F0_HIGH_HZ / nyq, 0.99)

    try:
        b, a = signal.butter(4, [low, high], btype="bandpass")
        voiced_filtered = signal.filtfilt(b, a, voiced_samples)
    except Exception:  # noqa: BLE001
        flags.append("filter_error")
        return VoiceResult(
            jitter_pct=None,
            shimmer_pct=None,
            snr_db=snr_db,
            voiced_fraction=voiced_fraction,
            flags=flags,
        )

    # Find peaks in filtered voiced signal (each peak ≈ one glottal cycle)
    min_period_samples = int(SAMPLE_RATE / F0_HIGH_HZ)  # shortest cycle
    max_period_samples = int(SAMPLE_RATE / F0_LOW_HZ)   # longest cycle

    peaks, properties = signal.find_peaks(
        voiced_filtered,
        distance=min_period_samples,
        prominence=0.005,
    )

    if len(peaks) < 4:
        flags.append("insufficient_glottal_cycles")
        return VoiceResult(
            jitter_pct=None,
            shimmer_pct=None,
            snr_db=snr_db,
            voiced_fraction=voiced_fraction,
            flags=flags,
        )

    # -----------------------------------------------------------------------
    # 5. Jitter = cycle-to-cycle period variation
    # -----------------------------------------------------------------------
    periods = np.diff(peaks).astype(float)  # in samples
    # Filter out unreasonable periods
    valid = (periods >= min_period_samples) & (periods <= max_period_samples)
    periods = periods[valid]

    jitter_pct: float | None = None
    if len(periods) >= 3:
        mean_period = float(np.mean(periods))
        if mean_period > 0:
            jitter_pct = round(float(np.std(periods)) / mean_period * 100.0, 3)

    # -----------------------------------------------------------------------
    # 6. Shimmer = cycle-to-cycle amplitude variation
    # -----------------------------------------------------------------------
    # Amplitude at each detected peak
    peak_amplitudes = np.abs(voiced_filtered[peaks])

    shimmer_pct: float | None = None
    if len(peak_amplitudes) >= 3:
        mean_amp = float(np.mean(peak_amplitudes))
        if mean_amp > 1e-8:
            shimmer_pct = round(float(np.std(peak_amplitudes)) / mean_amp * 100.0, 3)

    return VoiceResult(
        jitter_pct=jitter_pct,
        shimmer_pct=shimmer_pct,
        snr_db=snr_db,
        voiced_fraction=round(voiced_fraction, 3),
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_audio_samples(raw: list[float]) -> list[float]:
    """
    Validate and clamp audio sample values from API payload.
    Samples must be in [-1.0, 1.0] range.
    """
    return [max(-1.0, min(1.0, float(v))) for v in raw]
