"""Tests for eval-kit metrics: parity gap, risk-coverage, ECE, bootstrap and the HR-bin decoder."""

import math

import numpy as np
import pytest

from learning.eval_kit import metrics as mx
from learning.eval_kit.estimators import N_HR_BINS, decode_hr_bins

NAN = float("nan")


# ---- parity ------------------------------------------------------------------------------ #


def _groups(errors_by_group, n=10, ref=70.0):
    pred, refs, groups = [], [], []
    for g, err in errors_by_group.items():
        pred += [ref + err] * n
        refs += [ref] * n
        groups += [g] * n
    return np.array(pred), np.array(refs), groups


def test_parity_gap_detects_worst_minus_best_group():
    pred, ref, groups = _groups({"I-II": 1.0, "IV": 1.5, "VI": 4.0})
    res = mx.parity(pred, ref, groups)
    assert res.worst_group == "VI" and res.best_group == "I-II"
    assert res.gap_bpm == pytest.approx(3.0)
    assert res.gap_bpm > 1.5  # would fail the release gate


def test_parity_gap_small_when_groups_are_equal():
    pred, ref, groups = _groups({"I-II": 1.0, "III": 1.2, "V": 1.4})
    assert mx.parity(pred, ref, groups).gap_bpm == pytest.approx(0.4)


def test_parity_ignores_unknown_and_thin_groups():
    pred, ref, groups = _groups({"I-II": 1.0, "V": 1.0})
    pred = np.r_[pred, [100.0] * 3, [100.0] * 20]
    ref = np.r_[ref, [70.0] * 3, [70.0] * 20]
    groups = groups + ["VI"] * 3 + ["unknown"] * 20
    res = mx.parity(pred, ref, groups, min_answered=5)
    assert set(res.qualifying_groups) == {"I-II", "V"}
    assert res.gap_bpm == pytest.approx(0.0)


def test_refusing_a_group_cannot_hide_a_parity_problem():
    pred, ref, groups = _groups({"I-II": 1.0, "III": 1.0, "VI": 1.0})
    pred = pred.copy()
    vi = np.array(groups) == "VI"
    pred[np.flatnonzero(vi)[:8]] = NAN  # abstain on 8 of 10 type-VI items
    res = mx.parity(pred, ref, groups, min_answered=5)
    assert "VI" in res.qualifying_groups
    assert "VI" not in res.group_mae  # too few answered for an MAE...
    assert res.group_abstention["VI"] == pytest.approx(0.8)
    assert math.isinf(res.abstention_ratio)  # ...but the ratio catches it (others abstain 0)


def test_abstention_ratio_values():
    pred, ref, groups = _groups({"A": 0.0, "B": 0.0}, n=10)
    pred = pred.copy()
    pred[0:2] = NAN  # A abstains 20%
    pred[10:13] = NAN  # B abstains 30%
    assert mx.parity(pred, ref, groups).abstention_ratio == pytest.approx(1.5)
    pred2, ref2, g2 = _groups({"A": 0.0, "B": 0.0})
    assert mx.parity(pred2, ref2, g2).abstention_ratio == 1.0
    assert math.isnan(mx.parity(pred2[:10], ref2[:10], g2[:10]).abstention_ratio)


# ---- risk-coverage ------------------------------------------------------------------------ #


def test_risk_coverage_monotone_coverage_and_oracle_order():
    rng = np.random.default_rng(0)
    ref = np.full(200, 70.0)
    err = rng.exponential(4.0, 200)
    raw = ref + err
    oracle = mx.risk_coverage(raw, ref, -err)  # most confident = smallest error
    assert np.all(np.diff(oracle.coverage) > 0)
    assert oracle.coverage[-1] == pytest.approx(1.0)
    assert np.all(np.diff(oracle.risk) >= -1e-12)  # oracle ranking: risk never falls
    reverse = mx.risk_coverage(raw, ref, err)
    random_ = mx.risk_coverage(raw, ref, rng.random(200))
    assert oracle.aurc < random_.aurc < reverse.aurc
    assert oracle.risk[-1] == pytest.approx(reverse.risk[-1])  # full coverage = overall MAE


def test_risk_coverage_counts_unusable_items_in_denominator():
    raw = np.array([71.0, 72.0, NAN, NAN])
    ref = np.array([70.0, 70.0, 70.0, NAN])  # last is no-pulse: not counted
    curve = mx.risk_coverage(raw, ref, np.array([0.9, 0.8, 0.7, 0.6]))
    np.testing.assert_allclose(curve.coverage, [1 / 3, 2 / 3])
    np.testing.assert_allclose(curve.risk, [1.0, 1.5])
    assert curve.aurc == pytest.approx(1.25)


def test_coverage_at_fixed_mae():
    raw = 70.0 + np.array([0.0, 1.0, 2.0, 8.0, 20.0])
    ref = np.full(5, 70.0)
    curve = mx.risk_coverage(raw, ref, -np.arange(5.0))
    # top-k MAE: 0, 0.5, 1, 2.75, 6.2 -> largest coverage with MAE <= 3 is 4/5
    assert mx.coverage_at_risk(curve, 3.0) == pytest.approx(0.8)


# ---- calibration -------------------------------------------------------------------------- #


def test_ece_hand_computed():
    prob = np.array([0.15, 0.15, 0.85, 0.85, 0.85, 0.85])
    correct = np.array([0, 1, 1, 1, 1, 0])
    # bin 0.1-0.2: acc 0.5 vs conf 0.15 -> |0.35| * 2/6; bin 0.8-0.9: acc 0.75 vs 0.85 -> 0.1*4/6
    expected = 0.35 * 2 / 6 + 0.10 * 4 / 6
    assert mx.calibration_error(prob, correct) == pytest.approx(expected)


def test_ece_zero_for_perfect_calibration_and_uses_tolerance():
    rng = np.random.default_rng(1)
    conf = np.repeat([0.05, 0.95], 1000)
    correct = np.r_[rng.random(1000) < 0.05, rng.random(1000) < 0.95]
    ref = np.full(2000, 70.0)
    raw = np.where(correct, ref + 1.0, ref + 20.0)
    assert mx.expected_calibration_error(raw, ref, conf) < 0.02
    overconfident = np.full(2000, 0.99)
    assert mx.expected_calibration_error(raw, ref, overconfident) == pytest.approx(
        0.99 - correct.mean(), abs=1e-9
    )


# ---- accuracy, coverage, bootstrap -------------------------------------------------------- #


def test_accuracy_metrics_skip_abstentions_and_no_pulse():
    pred = np.array([72.0, 68.0, NAN, 90.0])
    ref = np.array([70.0, 70.0, 70.0, NAN])
    assert mx.mae(pred, ref) == pytest.approx(2.0)
    assert mx.rmse(pred, ref) == pytest.approx(2.0)
    assert mx.within_pct(pred, ref) == pytest.approx(100.0)
    assert mx.coverage(pred, ref) == pytest.approx(2 / 3)
    assert mx.no_pulse_false_accept_rate(pred, ref) == pytest.approx(1.0)


def test_subject_bootstrap_resamples_whole_subjects():
    subjects = ["a"] * 50 + ["b"] * 50
    values = np.r_[np.zeros(50), np.ones(50)]
    seen = set()

    def stat(idx):
        seen.add(len(idx))
        return float(values[idx].mean())

    ci = mx.subject_bootstrap(subjects, stat, n_boot=200, seed=0)
    lo, hi = ci["value"]
    assert lo == pytest.approx(0.0) and hi == pytest.approx(1.0)
    assert seen == {100}  # always two whole subjects of 50 rows


# ---- 141/142-class HR head ---------------------------------------------------------------- #


def test_decode_hr_bins_expectation_and_abstain_class():
    logits = np.full(N_HR_BINS + 1, -10.0)
    logits[72 - 40] = 5.0
    logits[73 - 40] = 5.0
    hr, conf, p_abst = decode_hr_bins(logits)
    assert hr == pytest.approx(72.5, abs=1e-3)
    assert conf > 0.99 and p_abst < 1e-6
    logits[-1] = 8.0
    hr2, _, p_abst2 = decode_hr_bins(logits)
    assert hr2 is None and p_abst2 > 0.5
    with pytest.raises(ValueError):
        decode_hr_bins(np.zeros(10))
