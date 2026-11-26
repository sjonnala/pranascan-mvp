"""
Voice DSP processor — local jitter, local shimmer, SNR and HNR from a sustained vowel.

Phase 0 voice safety rewrite (see the Cycle-1 voice budget-phone audit, bugs B1-B18).
The previous version treated loudness as voice (frame RMS > 0.01), reported a 40 dB
"SNR" whenever a fan or TV filled the pauses, counted harmonics as glottal cycles and
measured jitter/shimmer as std/mean. This version answers only when it can show that
the clip holds a periodic, voice-like signal, and otherwise abstains with reasons.

Pipeline (classical DSP only, deterministic):
  1. Clipping check: > 1 % of samples at full scale -> abstain ``clipping_detected``.
  2. DC removal + 60 Hz high-pass (second-order sections, ``sosfiltfilt``).
  3. Narrow notches on 50 Hz mains harmonics, only where a stationary peak exists.
  4. YIN per 40 ms frame (10 ms hop): F0 and aperiodicity (CMNDF minimum).
  5. Voicing = periodic (aperiodicity < 0.30, F0 75-450 Hz) AND above an adaptive
     energy floor. Loudness alone never counts as voice.
  6. Contiguous voiced runs >= 0.25 s are kept; runs are never concatenated.
  7. Stationary-tone rejection: a run whose F0 barely moves (CV < 0.3 %) and sits on a
     50 Hz multiple is treated as machinery (mixer, fan motor, transformer hum).
  8. SNR from voiced vs unvoiced frame power. No unvoiced frames -> ``snr_db = None``
     with ``no_noise_reference`` (never a sentinel). HNR from in-run aperiodicity.
  9. Cycle tracking by waveform matching at the run's F0, with sub-sample refinement on
     an 8x upsampled copy; cycle amplitude = peak-to-peak of the raw upsampled cycle.
 10. Praat-style local jitter / shimmer: mean absolute difference of consecutive
     periods (amplitudes) divided by their mean, so slow intonation is not jitter.
 11. Explicit abstention: ``jitter_pct = shimmer_pct = None`` plus a reason flag
     (``no_voice_detected``, ``insufficient_voiced_duration``, ``clipping_detected``,
     ``high_noise``, ``insufficient_glottal_cycles``, ``insufficient_samples``).
     Shimmer alone is withheld below 12 dB HNR (``shimmer_withheld_low_hnr``) because
     additive noise inflates it.

Input contract:
  audio_samples: list of float in [-1.0, 1.0], sample rate = 4410 Hz (2-5 s).

Output:
  VoiceResult (jitter_pct, shimmer_pct, snr_db, voiced_fraction, flags, hnr_db, f0_hz,
  voiced_duration_s, abstention_reason). These are wellness indicators only.

Privacy note:
  ``audio_samples`` is a down-sampled voice *waveform*, not just a loudness envelope.
  At 4.41 kHz it still carries pitch, the lower formants and timbre, which can support
  speaker identification. Treat it as personal data: process it transiently, never log
  or persist it, and prefer on-device feature extraction that sends only scalar
  indicators (audit §7.6 / §8.4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 4410  # Hz (input contract; downsampled by the client)
MIN_SAMPLES = SAMPLE_RATE * 2  # at least 2 seconds

FRAME_SAMPLES = int(0.040 * SAMPLE_RATE)  # 176 samples = 40 ms YIN window
HOP_SAMPLES = int(0.010 * SAMPLE_RATE)  # 44 samples = 10 ms hop
F0_LOW_HZ = 75.0  # lowest typical voice fundamental
F0_HIGH_HZ = 450.0  # highest typical voice (covers higher-pitched voices)
_TAU_MIN = int(SAMPLE_RATE / F0_HIGH_HZ)
_TAU_MAX = int(np.ceil(SAMPLE_RATE / F0_LOW_HZ))

HIGH_PASS_HZ = 60.0  # removes DC drift, handling rumble and the 50 Hz fundamental
MAINS_HZ = 50.0  # India / EU mains
MAINS_HARMONICS = 8
MAINS_PROMINENCE = 10.0  # line must stand 10 dB above its 2-15 Hz neighbourhood ...
MAINS_LINE_HALF_WIDTH_HZ = 0.6  # ... and hold most of its power within +/-0.6 Hz ...
MAINS_SPREAD_HALF_WIDTH_HZ = 5.0  # ... of the power within +/-5 Hz
MAINS_CONCENTRATION = 0.5

APERIODICITY_MAX = 0.30  # YIN CMNDF minimum below this -> periodic frame
YIN_THRESHOLD = 0.15  # absolute threshold for the YIN dip search
ENERGY_FLOOR_FACTOR = 4.0  # voiced frames must exceed 4x the 10th-percentile power ...
ENERGY_FLOOR_CEILING = 0.1  # ... capped at 10 % of the 90th-percentile power (see below)
MIN_FRAME_POWER = 1e-8  # digital silence guard (about -80 dBFS)

MIN_RUN_S = 0.25  # contiguous voiced run must last at least this long
MIN_DETECTED_VOICE_S = 0.25  # below this the clip holds no voice at all
MIN_VOICED_S = 1.0  # total voiced duration required to measure jitter
MIN_CYCLES = 40  # consecutive valid cycle pairs required for local jitter

STATIONARY_TONE_CV_MAX = 0.003  # F0 coefficient of variation below this ...
STATIONARY_TONE_MAINS_TOL = 0.01  # ... within 1 % of a 50 Hz multiple -> machinery

CLIP_LEVEL = 0.98  # |sample| at or above this counts as full scale
CLIP_ABSTAIN_FRACTION = 0.01  # > 1 % clipped samples -> abstain

SNR_ABSTAIN_DB = 8.0  # gap SNR below this is suspicious ...
HNR_MIN_DB = 6.0  # ... and in-vowel harmonicity below this abstains outright
HNR_AGC_TRUST_DB = 9.0  # low gap SNR is forgiven (AGC lifted the pauses) if HNR is this high
SHIMMER_HNR_MIN_DB = 12.0  # withhold shimmer below this HNR (noise inflates it)
NOISE_POWER_FLOOR = 1e-10  # -100 dBFS: keeps SNR finite over digital silence

# D26 accented-vowel accommodation. Voicing is now gated on voiced *duration*
# (>= MIN_VOICED_S of periodic runs), which already accepts short or onset-heavy
# vowels, so the voiced-fraction thresholds no longer gate measurement. They are kept
# for compatibility: ``accented_vowel_accommodated`` is still reported when a clean
# clip (SNR >= 20 dB) is measured with only 35-50 % of the clip voiced.
MIN_VOICED_FRACTION = 0.5
MIN_VOICED_FRACTION_ACCOMMODATED = 0.35
SNR_THRESHOLD_FOR_ACCOMMODATION_DB = 20.0

# Abstention reasons (also emitted as flags)
REASON_INSUFFICIENT_SAMPLES = "insufficient_samples"
REASON_CLIPPING = "clipping_detected"
REASON_NO_VOICE = "no_voice_detected"
REASON_SHORT_VOICE = "insufficient_voiced_duration"
REASON_HIGH_NOISE = "high_noise"
REASON_FEW_CYCLES = "insufficient_glottal_cycles"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class VoiceResult:
    """Voice DSP-derived wellness indicator values (None = not measured)."""

    jitter_pct: float | None  # Praat local jitter (%)
    shimmer_pct: float | None  # Praat local shimmer (%)
    snr_db: float | None  # voiced vs unvoiced power; None when there is no noise reference
    voiced_fraction: float  # fraction of analysis frames inside accepted voiced runs
    flags: list[str] = field(default_factory=list)
    hnr_db: float | None = None  # harmonics-to-noise estimate from YIN aperiodicity
    f0_hz: float | None = None  # median F0 of accepted runs
    voiced_duration_s: float = 0.0  # total duration of accepted voiced runs
    abstention_reason: str | None = None  # set whenever jitter_pct is None

    @property
    def abstained(self) -> bool:
        return self.jitter_pct is None


@dataclass(frozen=True)
class _VoicedRun:
    start_frame: int
    end_frame: int  # exclusive
    f0_hz: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_audio(samples: Sequence[float]) -> VoiceResult:
    """
    Process normalised audio samples (4410 Hz) into voice wellness indicators.

    Returns a VoiceResult whose ``jitter_pct`` is None whenever the clip does not
    contain enough clean, periodic voice; ``abstention_reason`` and ``flags`` say why.
    """
    flags: list[str] = []
    x = np.asarray(samples, dtype=np.float64)

    if len(x) < MIN_SAMPLES or not np.all(np.isfinite(x)):
        flags.append(REASON_INSUFFICIENT_SAMPLES)
        return VoiceResult(
            jitter_pct=None,
            shimmer_pct=None,
            snr_db=None,
            voiced_fraction=0.0,
            flags=flags,
            abstention_reason=REASON_INSUFFICIENT_SAMPLES,
        )

    clip_fraction = float(np.mean(np.abs(x) >= CLIP_LEVEL))

    x = x - float(np.mean(x))
    high_pass = signal.butter(2, HIGH_PASS_HZ, btype="high", fs=SAMPLE_RATE, output="sos")
    x = signal.sosfiltfilt(high_pass, x)
    x = _notch_mains(x, flags)

    f0, aperiodicity, power = _yin(x)
    voiced_mask = _voiced_mask(aperiodicity, power)
    runs = _accepted_runs(voiced_mask, f0, flags)

    n_frames = len(power)
    run_frames = sum(run.end_frame - run.start_frame for run in runs)
    voiced_fraction = round(run_frames / n_frames, 3) if n_frames else 0.0
    voiced_s = round(run_frames * HOP_SAMPLES / SAMPLE_RATE, 2)

    snr_db = _snr_db(voiced_mask, power, runs, flags)
    hnr_db = _hnr_db(aperiodicity, runs)
    f0_hz = round(float(np.median([run.f0_hz for run in runs])), 1) if runs else None

    def abstain(reason: str) -> VoiceResult:
        flags.append(reason)
        return VoiceResult(
            jitter_pct=None,
            shimmer_pct=None,
            snr_db=snr_db,
            voiced_fraction=voiced_fraction,
            flags=flags,
            hnr_db=hnr_db,
            f0_hz=f0_hz,
            voiced_duration_s=voiced_s,
            abstention_reason=reason,
        )

    if clip_fraction > CLIP_ABSTAIN_FRACTION:
        flags.append(f"clip_fraction:{clip_fraction:.3f}")
        return abstain(REASON_CLIPPING)
    if voiced_s < MIN_DETECTED_VOICE_S:
        return abstain(REASON_NO_VOICE)
    if voiced_s < MIN_VOICED_S:
        return abstain(REASON_SHORT_VOICE)
    if hnr_db is not None:
        low_gap_snr = snr_db is not None and snr_db < SNR_ABSTAIN_DB
        if hnr_db < HNR_MIN_DB or (low_gap_snr and hnr_db < HNR_AGC_TRUST_DB):
            return abstain(REASON_HIGH_NOISE)
        if low_gap_snr:
            flags.append("agc_noise_lift_suspected")

    periods: list[np.ndarray] = []
    amplitudes: list[np.ndarray] = []
    for run in runs:
        start = run.start_frame * HOP_SAMPLES
        end = run.end_frame * HOP_SAMPLES + FRAME_SAMPLES
        run_periods, run_amps = _track_cycles(x[start:end], run.f0_hz)
        # A NaN separator keeps consecutive-difference measures inside each run.
        periods.append(np.r_[run_periods, np.nan])
        amplitudes.append(np.r_[run_amps, np.nan])

    jitter, n_pairs = _local_perturbation(np.concatenate(periods))
    shimmer, _ = _local_perturbation(np.concatenate(amplitudes))
    if jitter is None or n_pairs < MIN_CYCLES:
        return abstain(REASON_FEW_CYCLES)

    if shimmer is not None and hnr_db is not None and hnr_db < SHIMMER_HNR_MIN_DB:
        shimmer = None
        flags.append("shimmer_withheld_low_hnr")

    if (
        MIN_VOICED_FRACTION_ACCOMMODATED <= voiced_fraction < MIN_VOICED_FRACTION
        and snr_db is not None
        and snr_db >= SNR_THRESHOLD_FOR_ACCOMMODATION_DB
    ):
        flags.append("accented_vowel_accommodated")

    return VoiceResult(
        jitter_pct=round(jitter, 3),
        shimmer_pct=round(shimmer, 3) if shimmer is not None else None,
        snr_db=snr_db,
        voiced_fraction=voiced_fraction,
        flags=flags,
        hnr_db=hnr_db,
        f0_hz=f0_hz,
        voiced_duration_s=voiced_s,
        abstention_reason=None,
    )


# ---------------------------------------------------------------------------
# DSP stages
# ---------------------------------------------------------------------------


def _notch_mains(x: np.ndarray, flags: list[str]) -> np.ndarray:
    """Notch 50 Hz harmonics that are both strong and spectrally narrow.

    A mains or motor-hum line is a near-perfect sinusoid: in a 5 s periodogram its power
    sits within a fraction of a hertz of 50*k Hz. A voice harmonic that happens to fall
    near 50*k Hz (an F0 of 150 Hz, say) is spread over several hertz by intonation and
    jitter. Requiring concentration as well as prominence keeps the notch, and its
    ringing, off the voice itself.
    """
    freqs, psd = signal.periodogram(x, fs=SAMPLE_RATE, window="hann")
    df = float(freqs[1] - freqs[0])
    y = x
    notched = 0
    for k in range(1, MAINS_HARMONICS + 1):
        fk = MAINS_HZ * k
        offset = np.abs(freqs - fk)
        core = psd[offset <= MAINS_LINE_HALF_WIDTH_HZ + df / 2]
        local = psd[offset <= MAINS_SPREAD_HALF_WIDTH_HZ]
        neighbourhood = psd[(offset >= 2.0) & (offset <= 15.0)]
        if not len(core) or not len(neighbourhood):
            continue
        prominent = float(core.max()) > MAINS_PROMINENCE * float(np.median(neighbourhood))
        concentrated = float(core.sum()) >= MAINS_CONCENTRATION * float(local.sum())
        if prominent and concentrated:
            b, a = signal.iirnotch(fk, Q=fk / 2.0, fs=SAMPLE_RATE)
            y = signal.sosfiltfilt(signal.tf2sos(b, a), y)
            notched += 1
    if notched:
        flags.append(f"mains_hum_notched:{notched}")
    return y


def _yin(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-frame (f0_hz, aperiodicity, power) with the YIN CMNDF."""
    window = FRAME_SAMPLES
    need = window + _TAU_MAX + 1
    n_frames = 1 + max(0, (len(x) - need) // HOP_SAMPLES)
    frames = np.lib.stride_tricks.sliding_window_view(x, need)[::HOP_SAMPLES][:n_frames]
    base = frames[:, :window]

    diff = np.zeros((n_frames, _TAU_MAX + 1))
    for tau in range(1, _TAU_MAX + 1):
        diff[:, tau] = np.sum((base - frames[:, tau : tau + window]) ** 2, axis=1)
    cumulative = np.cumsum(diff[:, 1:], axis=1)
    cmnd = np.ones_like(diff)
    cmnd[:, 1:] = diff[:, 1:] * np.arange(1, _TAU_MAX + 1) / np.maximum(cumulative, 1e-12)

    f0 = np.full(n_frames, np.nan)
    aperiodicity = np.ones(n_frames)
    for i in range(n_frames):
        curve = cmnd[i]
        search = curve[_TAU_MIN : _TAU_MAX + 1]
        below = np.where(search < YIN_THRESHOLD)[0]
        if len(below):
            j = int(below[0])
            while j + 1 < len(search) and search[j + 1] < search[j]:
                j += 1
        else:
            j = int(np.argmin(search))
        tau = j + _TAU_MIN
        aperiodicity[i] = curve[tau]
        tau_f = float(tau)
        if 1 <= tau < _TAU_MAX:
            a, b, c = curve[tau - 1], curve[tau], curve[tau + 1]
            den = a - 2.0 * b + c
            if abs(den) > 1e-12:
                tau_f += float(np.clip(0.5 * (a - c) / den, -0.5, 0.5))
        f0[i] = SAMPLE_RATE / tau_f

    power = np.mean(base**2, axis=1)
    return f0, aperiodicity, power


def _voiced_mask(aperiodicity: np.ndarray, power: np.ndarray) -> np.ndarray:
    """Periodic frames above an adaptive energy floor.

    The floor is 4x the 10th-percentile frame power (the pauses), capped at 10 % of the
    90th-percentile power so that a clip that is voiced from end to end, with no pause to
    estimate the floor from, is not rejected for lacking quiet frames. Noise-only clips
    are still rejected by the periodicity test, not by loudness.
    """
    if len(power) == 0:
        return np.zeros(0, dtype=bool)
    floor = min(
        ENERGY_FLOOR_FACTOR * float(np.percentile(power, 10)),
        ENERGY_FLOOR_CEILING * float(np.percentile(power, 90)),
    )
    return (aperiodicity < APERIODICITY_MAX) & (power > floor) & (power > MIN_FRAME_POWER)


def _accepted_runs(voiced_mask: np.ndarray, f0: np.ndarray, flags: list[str]) -> list[_VoicedRun]:
    """Contiguous voiced runs >= MIN_RUN_S that are not stationary mains-locked tones."""
    runs: list[_VoicedRun] = []
    stationary = False
    for start, end in _contiguous_runs(voiced_mask):
        if (end - start) * HOP_SAMPLES / SAMPLE_RATE < MIN_RUN_S:
            continue
        run_f0 = f0[start:end]
        median_f0 = float(np.median(run_f0))
        cv = float(np.std(run_f0) / median_f0)
        nearest_mains = min(abs(median_f0 - MAINS_HZ * k) for k in range(1, 10))
        if cv < STATIONARY_TONE_CV_MAX and nearest_mains < STATIONARY_TONE_MAINS_TOL * median_f0:
            stationary = True
            continue
        runs.append(_VoicedRun(start, end, median_f0))
    if stationary:
        flags.append("stationary_tone_suspected")
    return runs


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, value in enumerate(mask):
        if value and start is None:
            start = i
        elif not value and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _snr_db(
    voiced_mask: np.ndarray,
    power: np.ndarray,
    runs: list[_VoicedRun],
    flags: list[str],
) -> float | None:
    """Voiced-run vs unvoiced-frame power. None when no noise reference exists."""
    if not runs:
        return None
    unvoiced = ~voiced_mask
    if int(unvoiced.sum()) < 10:
        flags.append("no_noise_reference")
        return None
    noise_power = max(float(np.median(power[unvoiced])), NOISE_POWER_FLOOR)
    voiced_power = float(
        np.median(np.concatenate([power[run.start_frame : run.end_frame] for run in runs]))
    )
    return round(float(10.0 * np.log10(max(voiced_power - noise_power, 1e-12) / noise_power)), 1)


def _hnr_db(aperiodicity: np.ndarray, runs: list[_VoicedRun]) -> float | None:
    if not runs:
        return None
    in_runs = np.concatenate([aperiodicity[run.start_frame : run.end_frame] for run in runs])
    ratio = float(np.clip(1.0 - np.median(in_runs), 1e-3, 1.0 - 1e-3))
    return round(float(10.0 * np.log10(ratio / (1.0 - ratio))), 1)


def _refine_upsampled(xu: np.ndarray, up: int, a: int, a_frac: float, b: int, length: int) -> float:
    """Sub-sample offset of cycle start ``b`` by matching on the upsampled signal.

    Parabolic interpolation on the 4.41 kHz correlation alone is biased towards integer
    lags, which compresses period differences and under-reads jitter.
    """
    s0 = int(round((a + a_frac) * up))
    template = xu[s0 : s0 + length * up]
    template = template - template.mean()
    lags = np.arange(b * up - up, b * up + up + 1)
    if len(template) == 0 or lags[0] < 1 or lags[-1] + len(template) + 1 >= len(xu):
        return 0.0
    windows = np.lib.stride_tricks.sliding_window_view(
        xu[lags[0] - 1 : lags[-1] + 2 + len(template)], len(template)
    )
    windows = windows - windows.mean(axis=1, keepdims=True)
    corr = (windows @ template) / (
        np.sqrt(np.sum(windows**2, axis=1) * np.sum(template**2)) + 1e-12
    )
    j = int(np.argmax(corr[1:-1])) + 1
    den = corr[j - 1] - 2.0 * corr[j] + corr[j + 1]
    offset = 0.5 * (corr[j - 1] - corr[j + 1]) / den if abs(den) > 1e-12 else 0.0
    lag = lags[0] - 1 + j + float(np.clip(offset, -0.5, 0.5))
    return float(lag / up - b)


def _track_cycles(x: np.ndarray, f0_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Waveform-matching cycle tracker: per-cycle period (samples) and peak-to-peak amp."""
    up = 8
    xu = signal.resample_poly(x, up, 1)
    period = SAMPLE_RATE / f0_hz
    a = int(np.argmax(x[: int(period) + 1]))
    a_frac = 0.0
    periods: list[float] = []
    amps: list[float] = []
    while True:
        length = int(round(period))
        lo, hi = a + int(0.8 * period), a + int(np.ceil(1.2 * period))
        if hi + length + 1 >= len(x):
            break
        template = x[a : a + length]
        template = template - template.mean()
        candidates = np.lib.stride_tricks.sliding_window_view(x[lo - 1 : hi + 1 + length], length)
        candidates = candidates - candidates.mean(axis=1, keepdims=True)
        corr = (candidates @ template) / (
            np.sqrt(np.sum(candidates**2, axis=1) * np.sum(template**2)) + 1e-12
        )
        j = int(np.argmax(corr[1:-1])) + 1
        if corr[j] < 0.5:
            # Lost lock: skip ahead one period and break the consecutive chain.
            a += int(period)
            a_frac = 0.0
            periods.append(np.nan)
            amps.append(np.nan)
            continue
        b = lo - 1 + j
        offset = _refine_upsampled(xu, up, a, a_frac, b, length)
        cycle_period = (b + offset) - (a + a_frac)
        segment = xu[a * up : b * up]
        periods.append(cycle_period)
        amps.append(float(segment.max() - segment.min()) if len(segment) else np.nan)
        period = 0.7 * period + 0.3 * cycle_period
        start = b + offset
        a = int(np.floor(start))
        a_frac = start - a
    return np.array(periods, dtype=float), np.array(amps, dtype=float)


def _local_perturbation(values: np.ndarray) -> tuple[float | None, int]:
    """Praat-style local perturbation (%) over consecutive valid pairs.

    Pairs where either value deviates > 20 % from the median are skipped (octave or
    tracking errors), as are pairs that span a NaN run separator.
    """
    valid = ~np.isnan(values)
    if int(valid.sum()) < 3:
        return None, 0
    median = float(np.nanmedian(values))
    if median <= 0.0:
        return None, 0
    diffs: list[float] = []
    kept: list[float] = []
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if (
            valid[i]
            and valid[i - 1]
            and abs(cur - median) < 0.2 * median
            and abs(prev - median) < 0.2 * median
        ):
            diffs.append(abs(cur - prev))
            kept.append(cur)
    if len(diffs) < 3:
        return None, len(diffs)
    return float(np.mean(diffs) / np.mean(kept) * 100.0), len(diffs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_audio_samples(raw: list[float]) -> list[float]:
    """
    Validate and clamp audio sample values from API payload.
    Samples must be in [-1.0, 1.0] range.
    """
    return [max(-1.0, min(1.0, float(v))) for v in raw]
