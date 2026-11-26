"""Metrics for stratified rPPG evaluation: accuracy, risk-coverage, calibration and parity.

All functions take plain arrays so they are easy to test and reuse.

Conventions
-----------
- ``hr_pred`` is ``nan`` where the method abstained; ``hr_raw`` is the pre-abstention estimate
  (``nan`` if the method could not form one). ``hr_ref`` is ``nan`` for no-pulse items.
- Accuracy metrics (MAE, RMSE, Pearson r, % within 5 BPM) use answered items that have a
  reference. Coverage and abstention rates are over items that have a reference.
- Risk-coverage ranks items by confidence (highest first) and reports the MAE of the top-k at
  coverage ``k / n``. Items without a raw estimate can never be covered. AURC is the mean risk
  over the curve's points (lower is better).
- ECE treats confidence as the probability that the raw estimate is within ``tol_bpm`` of the
  reference (equal-width bins). A score that is not a probability (the classical spectral
  quality) gets an ECE too, which is the point: it shows it is not calibrated.
- Parity gap = worst-group MAE minus best-group MAE over Fitzpatrick groups with enough answered
  items. Abstention-rate ratio = max / min abstention rate over the same groups (``inf`` when
  the minimum is 0 and the maximum is not; 1.0 when every group abstains at the same rate).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

WITHIN_TOL_BPM = 5.0
FIXED_ERROR_MAE_BPM = 3.0


def _f(x: Sequence[float] | np.ndarray) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


def answered_mask(hr_pred, hr_ref) -> np.ndarray:
    return np.isfinite(_f(hr_pred)) & np.isfinite(_f(hr_ref))


def mae(hr_pred, hr_ref) -> float:
    m = answered_mask(hr_pred, hr_ref)
    return float(np.mean(np.abs(_f(hr_pred)[m] - _f(hr_ref)[m]))) if m.any() else float("nan")


def rmse(hr_pred, hr_ref) -> float:
    m = answered_mask(hr_pred, hr_ref)
    if not m.any():
        return float("nan")
    return float(np.sqrt(np.mean((_f(hr_pred)[m] - _f(hr_ref)[m]) ** 2)))


def pearson_r(hr_pred, hr_ref) -> float:
    m = answered_mask(hr_pred, hr_ref)
    if m.sum() < 3:
        return float("nan")
    a, b = _f(hr_pred)[m], _f(hr_ref)[m]
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def within_pct(hr_pred, hr_ref, tol_bpm: float = WITHIN_TOL_BPM) -> float:
    m = answered_mask(hr_pred, hr_ref)
    if not m.any():
        return float("nan")
    return float(100.0 * np.mean(np.abs(_f(hr_pred)[m] - _f(hr_ref)[m]) <= tol_bpm))


def coverage(hr_pred, hr_ref) -> float:
    """Share of items with a reference that the method answered."""
    has_ref = np.isfinite(_f(hr_ref))
    if not has_ref.any():
        return float("nan")
    return float(np.mean(np.isfinite(_f(hr_pred))[has_ref]))


def abstention_rate(hr_pred, hr_ref) -> float:
    c = coverage(hr_pred, hr_ref)
    return 1.0 - c if math.isfinite(c) else float("nan")


def no_pulse_false_accept_rate(hr_pred, hr_ref) -> float:
    """Share of no-pulse items (no reference) that still got an answer."""
    no_ref = ~np.isfinite(_f(hr_ref))
    if not no_ref.any():
        return float("nan")
    return float(np.mean(np.isfinite(_f(hr_pred))[no_ref]))


@dataclass(frozen=True)
class RiskCoverage:
    coverage: np.ndarray  # (k,) strictly increasing in (0, 1]
    risk: np.ndarray  # (k,) MAE of the k most confident items
    thresholds: np.ndarray  # (k,) confidence of the k-th item
    aurc: float

    def to_dict(self, max_points: int = 101) -> dict:
        n = self.coverage.size
        if n == 0:
            return {"coverage": [], "risk": [], "threshold": [], "aurc": self.aurc}
        idx = np.unique(np.linspace(0, n - 1, min(max_points, n)).round().astype(int))
        return {
            "coverage": [round(float(v), 5) for v in self.coverage[idx]],
            "risk": [round(float(v), 5) for v in self.risk[idx]],
            "threshold": [round(float(v), 6) for v in self.thresholds[idx]],
            "aurc": self.aurc,
        }


def risk_coverage(hr_raw, hr_ref, conf) -> RiskCoverage:
    """Risk (MAE) vs coverage when answering only the most confident items."""
    raw, ref, c = _f(hr_raw), _f(hr_ref), _f(conf)
    has_ref = np.isfinite(ref)
    n_total = int(has_ref.sum())
    usable = has_ref & np.isfinite(raw)
    if n_total == 0 or not usable.any():
        empty = np.zeros(0)
        return RiskCoverage(empty, empty, empty, float("nan"))
    err = np.abs(raw[usable] - ref[usable])
    score = np.where(np.isfinite(c[usable]), c[usable], -np.inf)
    # Highest confidence first; ties broken by input order (stable).
    order = np.argsort(-score, kind="stable")
    err_sorted = err[order]
    k = np.arange(1, err_sorted.size + 1, dtype=np.float64)
    risk = np.cumsum(err_sorted) / k
    cov = k / n_total
    return RiskCoverage(cov, risk, score[order], float(np.mean(risk)))


def coverage_at_risk(curve: RiskCoverage, max_mae_bpm: float = FIXED_ERROR_MAE_BPM) -> float:
    """Largest coverage whose top-k MAE stays <= ``max_mae_bpm`` (0 if none)."""
    if curve.coverage.size == 0:
        return float("nan")
    ok = curve.risk <= max_mae_bpm
    return float(curve.coverage[ok].max()) if ok.any() else 0.0


def expected_calibration_error(
    hr_raw, hr_ref, conf, tol_bpm: float = WITHIN_TOL_BPM, n_bins: int = 10
) -> float:
    """ECE of ``conf`` as P(|raw - ref| <= tol). Equal-width bins on [0, 1]."""
    raw, ref, c = _f(hr_raw), _f(hr_ref), _f(conf)
    m = np.isfinite(raw) & np.isfinite(ref) & np.isfinite(c)
    if not m.any():
        return float("nan")
    p = np.clip(c[m], 0.0, 1.0)
    correct = (np.abs(raw[m] - ref[m]) <= tol_bpm).astype(np.float64)
    return calibration_error(p, correct, n_bins)


def calibration_error(prob, correct, n_bins: int = 10) -> float:
    """Plain binary ECE: sum over bins of |accuracy - mean confidence| weighted by bin share."""
    p, y = _f(prob), _f(correct)
    if p.size == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=True), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        in_bin = idx == b
        if in_bin.any():
            ece += in_bin.mean() * abs(float(y[in_bin].mean()) - float(p[in_bin].mean()))
    return float(ece)


def reliability_table(hr_raw, hr_ref, conf, tol_bpm: float = WITHIN_TOL_BPM, n_bins: int = 10):
    raw, ref, c = _f(hr_raw), _f(hr_ref), _f(conf)
    m = np.isfinite(raw) & np.isfinite(ref) & np.isfinite(c)
    p = np.clip(c[m], 0.0, 1.0)
    y = (np.abs(raw[m] - ref[m]) <= tol_bpm).astype(np.float64)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=True), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        in_bin = idx == b
        rows.append(
            {
                "bin_low": round(float(edges[b]), 2),
                "bin_high": round(float(edges[b + 1]), 2),
                "n": int(in_bin.sum()),
                "mean_conf": float(p[in_bin].mean()) if in_bin.any() else None,
                "accuracy": float(y[in_bin].mean()) if in_bin.any() else None,
            }
        )
    return rows


@dataclass(frozen=True)
class ParityResult:
    gap_bpm: float
    worst_group: str | None
    best_group: str | None
    group_mae: dict[str, float]
    abstention_ratio: float
    group_abstention: dict[str, float]
    qualifying_groups: tuple[str, ...]


def parity(
    hr_pred,
    hr_ref,
    groups: Sequence[str],
    min_answered: int = 5,
    exclude: Sequence[str] = ("unknown",),
) -> ParityResult:
    """Fitzpatrick parity gap and abstention-rate ratio over groups with enough data."""
    pred, ref = _f(hr_pred), _f(hr_ref)
    g = np.asarray(groups, dtype=object)
    group_mae: dict[str, float] = {}
    group_abst: dict[str, float] = {}
    qualifying: list[str] = []
    for name in sorted({str(x) for x in g} - set(exclude)):
        sel = g == name
        has_ref = sel & np.isfinite(ref)
        if not has_ref.any():
            continue
        answered = has_ref & np.isfinite(pred)
        group_abst[name] = float(1.0 - answered.sum() / has_ref.sum())
        if answered.sum() >= min_answered:
            group_mae[name] = float(np.mean(np.abs(pred[answered] - ref[answered])))
        # A group qualifies for both numbers once it has enough reference items; MAE also
        # needs enough answered ones. A group that abstains on everything still counts for the
        # abstention ratio, so a model cannot pass parity by refusing a whole group.
        if has_ref.sum() >= min_answered:
            qualifying.append(name)

    mae_groups = {k: v for k, v in group_mae.items() if k in qualifying}
    if len(mae_groups) >= 2:
        worst = max(mae_groups, key=mae_groups.__getitem__)
        best = min(mae_groups, key=mae_groups.__getitem__)
        gap = mae_groups[worst] - mae_groups[best]
    else:
        worst = best = None
        gap = float("nan")

    abst = [group_abst[k] for k in qualifying]
    if len(abst) >= 2:
        hi, lo = max(abst), min(abst)
        # 1.0 when no group abstains; inf when one never abstains and another does.
        flat = 1.0 if hi <= 0.0 else float("inf")
        ratio = flat if lo <= 0.0 else hi / lo
    else:
        ratio = float("nan")
    return ParityResult(gap, worst, best, group_mae, ratio, group_abst, tuple(qualifying))


def subject_bootstrap(
    subjects: Sequence[str],
    statistic: Callable[[np.ndarray], float | Mapping[str, float]],
    n_boot: int = 1000,
    seed: int = 2026,
    alpha: float = 0.05,
) -> dict[str, tuple[float, float]]:
    """Percentile CIs from resampling whole subjects with replacement.

    ``statistic`` receives an index array into the original rows (with repeats) and returns a
    float or a mapping of named floats. NaN draws are ignored.
    """
    subj = np.asarray(subjects, dtype=object)
    unique = np.array(sorted({str(s) for s in subj}), dtype=object)
    rows_by_subject = [np.flatnonzero(subj == s) for s in unique]
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {}
    for _ in range(n_boot):
        pick = rng.integers(0, unique.size, unique.size)
        idx = np.concatenate([rows_by_subject[i] for i in pick]) if pick.size else np.zeros(0, int)
        value = statistic(idx)
        items = value.items() if isinstance(value, Mapping) else [("value", value)]
        for name, v in items:
            draws.setdefault(name, []).append(float(v))
    out: dict[str, tuple[float, float]] = {}
    for name, values in draws.items():
        arr = np.asarray(values, dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            out[name] = (float("nan"), float("nan"))
        else:
            lo, hi = np.percentile(arr, [100 * alpha / 2, 100 * (1 - alpha / 2)])
            out[name] = (float(lo), float(hi))
    return out
