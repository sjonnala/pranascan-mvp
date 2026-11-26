"""Synthetic voice and home-noise fixtures with exact ground truth (Phase 0 voice tests).

Adapted from the Cycle-1 voice budget-phone audit harness (``voice_synth.py``).
Everything is generated at 44.1 kHz with fixed seeds and brought to the 4.41 kHz
client contract with an anti-aliased decimation, like the documented client path.

Signal chain for speech:
    Rosenberg glottal pulses (controlled per-cycle jitter / shimmer, slow intonation drift)
      -> vowel /a/ formant cascade -> lip radiation -> optional noise at a target SNR
      -> optional budget-phone AGC / hard clipping -> 4.41 kHz
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

FS_HI = 44_100
FS_LO = 4_410
DECIMATION = FS_HI // FS_LO
CLIP_S = 5.0

VOWEL_A_FORMANTS = [(730.0, 90.0), (1090.0, 110.0), (2440.0, 170.0), (3400.0, 250.0)]


@dataclass(frozen=True)
class VowelTruth:
    f0_hz: float
    jitter_local_pct: float  # Praat local: mean |dT| / mean T
    shimmer_local_pct: float  # Praat local: mean |dA| / mean A
    jitter_std_over_mean_pct: float  # the old (buggy) definition, for contrast
    onset_s: float
    duration_s: float


# ---------------------------------------------------------------------------
# Speech
# ---------------------------------------------------------------------------


def _resonator(x: np.ndarray, freq: float, bandwidth: float) -> np.ndarray:
    r = np.exp(-np.pi * bandwidth / FS_HI)
    theta = 2.0 * np.pi * freq / FS_HI
    a1, a2 = 2.0 * r * np.cos(theta), -(r**2)
    return signal.lfilter([1.0 - a1 - a2], [1.0, -a1, -a2], x)


def sustained_vowel_hi(
    seed: int,
    f0_hz: float = 150.0,
    jitter_pct: float = 0.8,
    shimmer_pct: float = 3.0,
    onset_s: float = 0.5,
    duration_s: float = 3.5,
    drift_pct: float = 2.0,
    clip_s: float = CLIP_S,
) -> tuple[np.ndarray, VowelTruth]:
    """One sustained /a/ at 44.1 kHz (peak-normalised to 0.5) and its exact truth."""
    rng = np.random.default_rng(seed)
    n = int(round(clip_s * FS_HI))
    out = np.zeros(n)
    t0, t_end = onset_s, min(onset_s + duration_s, clip_s - 0.01)
    sigma_j = jitter_pct / 100.0 / 1.128  # iid normal -> local jitter = 1.128 * sigma
    sigma_s = shimmer_pct / 100.0 / 1.128
    phase = rng.uniform(0, 2 * np.pi)
    periods, amps, starts, nominal = [], [], [], []
    t = t0
    while True:
        rel = (t - t0) / max(duration_s, 1e-6)
        # Slow intonation drift and 3 % declination: these are NOT jitter.
        f_inst = (
            f0_hz
            * (1.0 + drift_pct / 100.0 * np.sin(2 * np.pi * 0.3 * (t - t0) + phase))
            * (1.0 - 0.03 * rel)
        )
        period = (1.0 / f_inst) * (1.0 + rng.normal(0.0, sigma_j))
        if t + period > t_end:
            break
        periods.append(period)
        amps.append(1.0 + rng.normal(0.0, sigma_s))
        starts.append(t)
        nominal.append(1.0 / f_inst)
        t += period

    periods_a, amps_a = np.array(periods), np.array(amps)
    for start, per, amp, nom in zip(starts, periods_a, amps_a, nominal, strict=True):
        i0, i1 = int(np.floor(start * FS_HI)), int(np.ceil((start + per) * FS_HI))
        idx = np.arange(i0, min(i1, n))
        tt = idx / FS_HI - start
        tp, tn = 0.40 * nom, 0.16 * nom
        pulse = np.where(
            tt < tp,
            0.5 * (1 - np.cos(np.pi * tt / tp)),
            np.where(tt < tp + tn, np.cos(np.pi * (tt - tp) / (2 * tn)), 0.0),
        )
        pulse[tt < 0] = 0.0
        out[idx] += amp * pulse

    env = np.zeros(n)
    i_on, i_off = int(t0 * FS_HI), int(t_end * FS_HI)
    env[i_on:i_off] = 1.0
    ramp = int(0.05 * FS_HI)
    if i_off - i_on > 2 * ramp:
        w = 0.5 * (1 - np.cos(np.linspace(0, np.pi, ramp)))
        env[i_on : i_on + ramp] = w
        env[i_off - ramp : i_off] = w[::-1]
    y = out * env
    for freq, bw in VOWEL_A_FORMANTS:
        y = _resonator(y, freq, bw)
    y = np.diff(y, prepend=0.0)  # lip radiation
    y[i_on:i_off] -= np.mean(y[i_on:i_off])
    y[:i_on] = 0.0
    y[i_off:] = 0.0
    y = 0.5 * y / (np.max(np.abs(y)) + 1e-12)

    def local(v: np.ndarray) -> float:
        return float(np.mean(np.abs(np.diff(v))) / np.mean(v) * 100.0)

    truth = VowelTruth(
        f0_hz=float(1.0 / np.mean(periods_a)),
        jitter_local_pct=local(periods_a),
        shimmer_local_pct=local(amps_a),
        jitter_std_over_mean_pct=float(np.std(periods_a) / np.mean(periods_a) * 100.0),
        onset_s=t0,
        duration_s=t_end - t0,
    )
    return y, truth


# ---------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------


def _colored(rng: np.random.Generator, n: int, exponent: float) -> np.ndarray:
    spec = np.fft.rfft(rng.normal(size=n))
    f = np.fft.rfftfreq(n, 1.0 / FS_HI)
    f[0] = f[1]
    spec /= f ** (exponent / 2.0)
    x = np.fft.irfft(spec, n)
    return x / (np.std(x) + 1e-12)


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    return signal.sosfilt(signal.butter(4, cutoff, btype="low", fs=FS_HI, output="sos"), x)


def ceiling_fan_hi(seed: int, clip_s: float = CLIP_S) -> np.ndarray:
    """50 Hz motor hum and harmonics (100 Hz dominant) + blade-pass modulated airflow."""
    rng = np.random.default_rng(seed)
    n = int(round(clip_s * FS_HI))
    t = np.arange(n) / FS_HI
    rel = [0.5, 1.0, 0.35, 0.30, 0.15, 0.12, 0.08, 0.06]
    hum = sum(
        a * np.sin(2 * np.pi * 50.0 * k * t + rng.uniform(0, 2 * np.pi))
        for k, a in enumerate(rel, start=1)
    )
    hum /= np.std(hum)
    air = _lowpass(_colored(rng, n, 1.0), 800.0)
    air *= 1.0 + 0.25 * np.sin(2 * np.pi * 3 * rng.uniform(4.0, 6.0) * t)
    air /= np.std(air)
    x = np.sqrt(0.6) * hum + np.sqrt(0.4) * air
    return x / np.std(x)


def mixer_grinder_hi(seed: int, clip_s: float = CLIP_S) -> np.ndarray:
    """Universal motor ~300 Hz with load wobble + broadband grinding."""
    rng = np.random.default_rng(seed)
    n = int(round(clip_s * FS_HI))
    t = np.arange(n) / FS_HI
    fr = rng.uniform(270.0, 330.0) * (1 + 0.01 * np.sin(2 * np.pi * rng.uniform(0.5, 2.0) * t))
    ph = 2 * np.pi * np.cumsum(fr) / FS_HI
    tonal = sum((0.75**k) * np.sin(k * ph + rng.uniform(0, 6)) for k in range(1, 9))
    tonal /= np.std(tonal)
    x = 0.6 * tonal + 0.8 * _colored(rng, n, 0.5)
    return x / np.std(x)


def room_floor_hi(seed: int, clip_s: float = CLIP_S) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return _colored(rng, int(round(clip_s * FS_HI)), 1.0)


def budget_agc_hi(
    x: np.ndarray, target_rms: float = 0.126, max_gain_db: float = 30.0
) -> np.ndarray:
    """Block AGC (10 ms attack, 300 ms release) that lifts quiet input, like budget phones."""
    block = int(0.01 * FS_HI)
    nb = len(x) // block
    rms = np.sqrt(np.mean(x[: nb * block].reshape(nb, block) ** 2, axis=1)) + 1e-6
    g_max = 10 ** (max_gain_db / 20.0)
    a_att, a_rel = 1 - np.exp(-10.0 / 10.0), 1 - np.exp(-10.0 / 300.0)
    g, gains = 1.0, np.empty(nb)
    for i in range(nb):
        desired = min(target_rms / rms[i], g_max)
        g += (a_att if desired < g else a_rel) * (desired - g)
        gains[i] = g
    return x * np.interp(np.arange(len(x)), np.arange(nb) * block + block / 2, gains)


# ---------------------------------------------------------------------------
# Mixing and client conversion
# ---------------------------------------------------------------------------


def to_client(x_hi: np.ndarray) -> list[float]:
    """Anti-aliased 44.1 kHz -> 4.41 kHz, clamped to [-1, 1] like build_audio_samples."""
    lo = signal.resample_poly(x_hi, 1, DECIMATION)
    return [float(v) for v in np.clip(lo, -1.0, 1.0)]


def _band_power(x_hi: np.ndarray, start_s: float, end_s: float) -> float:
    lo = signal.resample_poly(x_hi, 1, DECIMATION)
    seg = lo[int(start_s * FS_LO) : int(end_s * FS_LO)]
    return float(np.mean(seg**2))


def mix_at_snr(
    voice_hi: np.ndarray, noise_hi: np.ndarray, snr_db: float, truth: VowelTruth
) -> np.ndarray:
    """Add noise so that voice / noise power in the 0-2.2 kHz band equals ``snr_db``."""
    end = truth.onset_s + truth.duration_s
    p_voice = _band_power(voice_hi, truth.onset_s, end)
    p_noise = _band_power(noise_hi, truth.onset_s, end)
    return voice_hi + noise_hi * np.sqrt(p_voice / (p_noise * 10 ** (snr_db / 10.0)))


def at_dbfs(x_hi: np.ndarray, dbfs: float) -> np.ndarray:
    """Scale to a given RMS level (dB re full scale)."""
    return x_hi * (10 ** (dbfs / 20.0) / (np.sqrt(np.mean(x_hi**2)) + 1e-12))


def quiet_vowel(seed: int, **kwargs) -> tuple[list[float], VowelTruth]:
    """Sustained vowel in a quiet room (-55 dBFS pink floor), at the client rate."""
    voice, truth = sustained_vowel_hi(seed, **kwargs)
    floor = at_dbfs(room_floor_hi(seed + 1000), -55.0)
    return to_client(voice + floor), truth


def harmonic_tone(f0_hz: float, clip_s: float = CLIP_S, amplitude: float = 0.3) -> list[float]:
    """Perfectly stationary harmonic tone at the client rate (machinery / hum stand-in)."""
    t = np.arange(int(clip_s * FS_LO)) / FS_LO
    x = sum((0.6**k) * np.sin(2 * np.pi * f0_hz * (k + 1) * t) for k in range(4))
    return [float(v) for v in amplitude * x / np.max(np.abs(x))]
