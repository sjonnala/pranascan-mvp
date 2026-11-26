"""Cycle-1 DSP-autoresearch winner I30: windowed PBV with exposure-step repair and abstention.

Ported from ``AI-CV-Mastery/Cycle-1/DSP-Autoresearch/winning_dsp_pipeline.py`` so the eval kit
can score it next to the classical baselines. The algorithm and every frozen parameter are
unchanged; only names were adjusted for this repo's lint rules and the embedded tests moved to
``tests/test_eval_kit_pbv_i30.py``.

Everything here was selected on SYNTHETIC data (``benchmark_budget_phones.py``, dev split) and
re-checked on a held-out synthetic split. It has not been validated on real recordings.

Pipeline (input: capture timestamps in seconds and per-frame ROI mean RGB in 8-bit DN):

1. Resample to a uniform 30 Hz grid with linear interpolation (handles 12-20 fps, jitter, drops).
2. Repair auto-exposure steps: log-luma jumps > 0.03 between the 0.4 s before and after a point
   (0.15 s guard, >= 1 s between steps), each removed per channel as a 0.3 s ramp in log space.
3. PBV projection (de Haan & van Leest 2014), 1.6 s sliding windows, signature
   ``[0.18, 0.78, 0.60]``, overlap-add.
4. Linear detrend, unit-variance normalise, Butterworth order-4 band-pass 0.7-4.0 Hz.
5. HR = 60 * f0 from a Hann periodogram zero-padded to 8192 points, sub-harmonic summation
   (3 harmonics) and parabolic refinement on log power.
6. Confidence = logistic model over five features (``pmr_db``, ``prom_db``, ``entropy``,
   ``win_agree``, ``win_mad``); answer only when confidence >= ``TAU``, else abstain.

The logistic weights and ``TAU`` were fitted on the benchmark's calib split so that 98.5% of
calib no-pulse sessions abstain. Refit with ``fit_confidence`` on real labelled data before
trusting ``TAU`` on real phones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import signal

FS_GRID_HZ = 30.0
STEP_THR_LOG = 0.03
STEP_HALF_S = 0.4
STEP_GUARD_S = 0.15
STEP_MIN_SEP_S = 1.0
PBV_WIN_S = 1.6
PBV_SIGNATURE = np.array([0.18, 0.78, 0.60])
BAND_HZ = (0.7, 4.0)
BUTTER_ORDER = 4
NFFT = 8192
SHS_HARMONICS = 3
SHS_FLOOR = 0.05
WIN_S, WIN_HOP_S, WIN_NFFT = 10.0, 2.0, 2048
FLAT_STD_DN = 1e-3

FEATURES = ("pmr_db", "prom_db", "entropy", "win_agree", "win_mad")
CONF_MU = np.array(
    [18.843553466592066, 9.412839992253781, 0.7918723687979706, 0.7748636363636362, 6.51416015625]
)
CONF_SD = np.array(
    [
        6.500448803000288,
        6.380403539998586,
        0.11182704429501789,
        0.33088908318728477,
        11.177140912531112,
    ]
)
# Intercept first, then FEATURES order.
CONF_W = np.array(
    [
        9.415903074336864,
        1.254178967742779,
        1.2707263814692695,
        -6.296118952314572,
        0.3507367955195184,
        -0.5366809785629335,
    ]
)
TAU = 0.5843589329637333


@dataclass
class HRResult:
    hr_bpm: float | None  # None = abstain
    confidence: float  # logistic confidence in [0, 1]; nan if no HR could be formed
    raw_hr_bpm: float | None  # HR before the abstention decision
    features: dict = field(default_factory=dict)
    n_exposure_steps: int = 0

    @property
    def accepted(self) -> bool:
        return self.hr_bpm is not None


def resample_uniform(t_s: np.ndarray, rgb: np.ndarray, fs: float = FS_GRID_HZ):
    grid = np.arange(t_s[0], t_s[-1], 1.0 / fs)
    x = np.column_stack([np.interp(grid, t_s, rgb[:, c]) for c in range(3)])
    return grid, x


def repair_exposure_steps(
    x: np.ndarray,
    fs: float,
    thr: float = STEP_THR_LOG,
    half_s: float = STEP_HALF_S,
    guard_s: float = STEP_GUARD_S,
    min_sep_s: float = STEP_MIN_SEP_S,
):
    """Remove auto-exposure / AWB steps. Returns ``(repaired rgb, number of steps removed)``."""
    lx = np.log(np.maximum(x, 1e-6))
    luma = lx.mean(1)
    h, g = max(2, int(half_s * fs)), max(1, int(guard_s * fs))
    n = luma.size
    k = np.arange(h + g, n - h - g)
    if k.size == 0:
        return x, 0
    c = np.r_[0.0, np.cumsum(luma)]
    d = np.abs((c[k + g + h] - c[k + g]) / h - (c[k - g] - c[k - g - h]) / h)
    steps: list[int] = []
    for j in np.argsort(-d):
        if d[j] < thr:
            break
        if all(abs(k[j] - s0) > int(min_sep_s * fs) for s0 in steps):
            steps.append(int(k[j]))
    if not steps:
        return x, 0
    corr = np.zeros_like(lx)
    ramp_t = np.arange(n)
    for s0 in steps:
        jump = lx[s0 + g : s0 + g + h].mean(0) - lx[s0 - g - h : s0 - g].mean(0)
        corr += np.clip((ramp_t - (s0 - g)) / (2.0 * g), 0.0, 1.0)[:, None] * jump[None, :]
    return np.exp(lx - corr), len(steps)


def pbv_windowed(
    rgb: np.ndarray, fs: float, win_s: float = PBV_WIN_S, pbv: np.ndarray = PBV_SIGNATURE
) -> np.ndarray:
    """PBV pulse extraction: per window ``w = Pbv Q^-1`` on mean-normalised channels, overlap-add."""
    n = rgb.shape[0]
    win = min(max(4, int(math.ceil(win_s * fs))), n)
    w = sliding_window_view(rgb, win, axis=0)  # (nw, 3, win)
    cn = w / np.maximum(np.mean(w, axis=2, keepdims=True), 1e-9) - 1.0
    cov = np.einsum("wcl,wdl->wcd", cn, cn) / win + 1e-10 * np.eye(3)[None]
    weights = np.linalg.solve(cov, np.broadcast_to(pbv, (cov.shape[0], 3))[..., None])[..., 0]
    hseg = np.einsum("wc,wcl->wl", weights, cn)
    hseg = hseg / (hseg.std(1, keepdims=True) + 1e-12)
    hseg -= hseg.mean(1, keepdims=True)
    idx = np.arange(hseg.shape[0])[:, None] + np.arange(win)[None, :]
    out = np.zeros(n)
    np.add.at(out, idx.ravel(), hseg.ravel())
    return out


def detrend_linear(x: np.ndarray) -> np.ndarray:
    n = x.size
    xc = np.arange(n, dtype=float) - (n - 1) / 2.0
    return x - (np.sum(xc * x) / np.sum(xc**2) * xc + x.mean())


def bandpass(
    x: np.ndarray,
    fs: float,
    lo: float = BAND_HZ[0],
    hi: float = BAND_HZ[1],
    order: int = BUTTER_ORDER,
):
    nyq = fs / 2.0
    lo_n, hi_n = lo / nyq, min(hi / nyq, 0.99)
    if not 0 < lo_n < hi_n < 1:
        return None
    b, a = signal.butter(order, [lo_n, hi_n], btype="bandpass")
    return signal.filtfilt(b, a, x)


def periodogram(x: np.ndarray, fs: float, nfft: int = NFFT):
    return signal.periodogram(x, fs=fs, window="hann", nfft=max(nfft, x.size))


def shs_peak(
    f: np.ndarray,
    p: np.ndarray,
    lo: float = BAND_HZ[0],
    hi: float = BAND_HZ[1],
    n_harm: int = SHS_HARMONICS,
    floor: float = SHS_FLOOR,
) -> float | None:
    """Dominant pulse frequency (Hz) by sub-harmonic summation + parabolic refinement."""
    idx = np.where((f >= lo) & (f <= hi))[0]
    if idx.size == 0:
        return None
    pmax = p[idx].max()
    if pmax <= 0:
        return None
    df = f[1] - f[0]
    score = np.zeros(idx.size)
    for j, i in enumerate(idx):
        if p[i] < floor * pmax:
            continue
        total = 0.0
        for hh in range(1, n_harm + 1):
            b = int(round(f[i] * hh / df))
            if b < p.size:
                total += p[b] / hh
        score[j] = total
    i = idx[int(np.argmax(score))]
    if 0 < i < p.size - 1 and p[i - 1] > 0 and p[i + 1] > 0:
        a, b, c = np.log(p[i - 1]), np.log(p[i]), np.log(p[i + 1])
        den = a - 2 * b + c
        delta = 0.5 * (a - c) / den if den != 0 else 0.0
        return float(f[i] + np.clip(delta, -0.5, 0.5) * df)
    return float(f[i])


def quality_features(
    bvp: np.ndarray, fs: float, f: np.ndarray, p: np.ndarray, hr_bpm: float
) -> dict[str, float]:
    """The five abstention features (nan where undefined)."""
    lo, hi = BAND_HZ
    f_hr = hr_bpm / 60.0
    band = (f >= lo) & (f <= hi)
    pb = p[band] / (p[band].sum() + 1e-30)
    out = {"entropy": float(-(pb * np.log(pb + 1e-30)).sum() / math.log(pb.size))}
    excl = (
        band
        & (np.abs(f - f_hr) > 0.2)
        & (np.abs(f - 2 * f_hr) > 0.2)
        & (np.abs(f - f_hr / 2) > 0.1)
    )
    p_peak = p[band & (np.abs(f - f_hr) <= 0.05)].max(initial=1e-30)
    p_2nd = p[excl].max(initial=1e-30)
    out["prom_db"] = float(10 * math.log10(p_peak / p_2nd))
    floor_ = np.median(p[band & (np.abs(f - f_hr) > 0.15) & (np.abs(f - 2 * f_hr) > 0.15)])
    out["pmr_db"] = float(10 * math.log10(p_peak / max(floor_, 1e-30)))
    win_len, hop = int(WIN_S * fs), int(WIN_HOP_S * fs)
    whr = []
    for s in range(0, bvp.size - win_len + 1, hop):
        fw, pw = periodogram(bvp[s : s + win_len], fs, WIN_NFFT)
        mw = (fw >= lo) & (fw <= hi)
        if np.any(mw):
            whr.append(60.0 * fw[mw][np.argmax(pw[mw])])
    whr_arr = np.asarray(whr)
    out["win_agree"] = (
        float(np.mean(np.abs(whr_arr - hr_bpm) <= 5.0)) if whr_arr.size else float("nan")
    )
    out["win_mad"] = (
        float(np.median(np.abs(whr_arr - np.median(whr_arr)))) if whr_arr.size else float("nan")
    )
    return out


def _feature_vector(feats: dict) -> np.ndarray:
    x = np.array([feats.get(k, float("nan")) for k in FEATURES], dtype=float)
    return np.nan_to_num(x, nan=0.0, posinf=60.0, neginf=-60.0)


def confidence(feats: dict, mu=CONF_MU, sd=CONF_SD, w=CONF_W) -> float:
    z = np.r_[1.0, (_feature_vector(feats) - mu) / sd]
    return float(1.0 / (1.0 + np.exp(-z @ w)))


def fit_confidence(
    feature_dicts, correct, target_recall: float = 0.985, is_nopulse=None, l2: float = 1e-2
):
    """Refit the logistic confidence on labelled data (for example real recordings).

    ``feature_dicts``: ``HRResult.features`` of sessions that produced an HR.
    ``correct``: 1 where the HR was within 5 BPM of the reference, else 0.
    ``is_nopulse``: optional bool array; ``tau`` is then the smallest cut at which
    ``target_recall`` of the no-pulse sessions abstain. Returns ``(mu, sd, w, tau)``.
    """
    x = np.array([_feature_vector(d) for d in feature_dicts])
    y = np.asarray(correct, dtype=float)
    mu, sd = x.mean(0), x.std(0) + 1e-9
    z = np.column_stack([np.ones(len(x)), (x - mu) / sd])
    w = np.zeros(z.shape[1])
    reg = l2 * np.diag(np.r_[0.0, np.ones(len(w) - 1)])
    for _ in range(50):
        pr = 1 / (1 + np.exp(-z @ w))
        hess = z.T @ (z * (pr * (1 - pr) + 1e-9)[:, None]) + reg
        step = np.linalg.solve(hess, z.T @ (pr - y) + reg @ w)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    tau = 0.5
    if is_nopulse is not None and np.any(is_nopulse):
        conf = 1 / (1 + np.exp(-z @ w))
        cn = np.sort(conf[np.asarray(is_nopulse, bool)])
        for cand in np.r_[0.0, cn]:
            if np.mean(cn < cand + 1e-12) >= target_recall:
                tau = float(cand + 1e-12)
                break
    return mu, sd, w, tau


def estimate_hr(t_s, rgb, tau: float = TAU) -> HRResult:
    """Estimate heart rate (BPM) from ROI-mean RGB, or abstain.

    ``t_s``: ``(n,)`` capture timestamps in seconds, strictly increasing (irregular is fine).
    ``rgb``: ``(n, 3)`` per-frame ROI means, 8-bit DN scale. Use >= ~20 s for the window features.
    """
    t_s = np.asarray(t_s, dtype=float)
    rgb = np.asarray(rgb, dtype=float)
    none = HRResult(None, float("nan"), None)
    if t_s.ndim != 1 or rgb.shape != (t_s.size, 3) or t_s.size < 32 or not np.all(np.isfinite(rgb)):
        return none
    if np.any(np.diff(t_s) <= 0) or t_s[-1] - t_s[0] < 4.0:
        return none
    try:
        fs = FS_GRID_HZ
        _, x = resample_uniform(t_s, rgb, fs)
        x, n_steps = repair_exposure_steps(x, fs)
        none.n_exposure_steps = n_steps
        raw = detrend_linear(pbv_windowed(x, fs))
        if float(np.max(np.std(x, axis=0))) < FLAT_STD_DN or raw.std() < 1e-9:
            return none
        bvp = bandpass(raw / raw.std(), fs)
        if bvp is None:
            return none
        f, p = periodogram(bvp, fs)
        f0 = shs_peak(f, p)
        if f0 is None:
            return none
        hr = 60.0 * f0
        feats = quality_features(bvp, fs, f, p, hr)
        c = confidence(feats)
        return HRResult(hr if c >= tau else None, c, hr, feats, n_steps)
    except (ValueError, np.linalg.LinAlgError, FloatingPointError):
        return none


def pulse_signal(t_s, rgb) -> tuple[np.ndarray, float] | None:
    """Band-passed PBV pulse on the 30 Hz grid, for plots in error analysis."""
    t_s = np.asarray(t_s, dtype=float)
    rgb = np.asarray(rgb, dtype=float)
    if t_s.size < 32 or np.any(np.diff(t_s) <= 0):
        return None
    _, x = resample_uniform(t_s, rgb, FS_GRID_HZ)
    x, _ = repair_exposure_steps(x, FS_GRID_HZ)
    raw = detrend_linear(pbv_windowed(x, FS_GRID_HZ))
    if raw.std() < 1e-9:
        return None
    bvp = bandpass(raw / raw.std(), FS_GRID_HZ)
    return (bvp, FS_GRID_HZ) if bvp is not None else None
