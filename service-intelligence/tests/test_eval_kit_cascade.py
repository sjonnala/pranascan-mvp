"""Tests for the alias-aware A1 -> C3 -> I30 cascade (T-203 rule, T-304 port)."""

from dataclasses import dataclass, field

import numpy as np
import pytest

from learning.eval_kit.estimators import (
    ALIAS_GUARD_FLAG,
    CASCADE_METHOD,
    TAU_C3_DEFAULT,
    THETA_EXPOSURE_DEFAULT,
    AliasAwareCascadeEstimator,
    Estimate,
    EstimatorSpec,
    PbvI30Estimator,
    QualityGateClassifier,
)

T = np.arange(0.0, 20.0, 1.0 / 30.0)
RGB = np.tile([176.0, 126.0, 101.0], (T.size, 1))


@dataclass
class FixedEstimator:
    """Test double: always returns the same estimate and counts calls."""

    name: str
    hr: float | None
    conf: float
    raw: float | None = None
    calls: int = 0
    methods: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.methods = (self.name,)

    def estimate(self, t_s, rgb):
        self.calls += 1
        raw = self.raw if self.raw is not None else self.hr
        return {self.name: Estimate(self.name, self.hr, self.conf, raw, ())}


class CountingGate:
    def __init__(self, p: float) -> None:
        self.p = p
        self.calls = 0

    def __call__(self, t_s, rgb) -> float:
        self.calls += 1
        return self.p


def _cascade(c3, i30, gate, theta=THETA_EXPOSURE_DEFAULT):
    return AliasAwareCascadeEstimator(primary=c3, fallback=i30, exposure_gate=gate, theta=theta)


def test_is_an_estimator_spec_with_one_method():
    spec = _cascade(FixedEstimator("c3", 72, 0.95), FixedEstimator("i30", 70, 0.9), CountingGate(0))
    assert isinstance(spec, EstimatorSpec)
    assert spec.methods == (CASCADE_METHOD,)


def test_confident_primary_answers_and_skips_fallback_and_gate():
    c3, i30, gate = (
        FixedEstimator("c3", 72.0, 0.95),
        FixedEstimator("i30", 70.0, 0.9),
        CountingGate(0.99),
    )
    est = _cascade(c3, i30, gate).estimate(T, RGB)[CASCADE_METHOD]
    assert est.hr_bpm == 72.0 and est.confidence == 0.95
    assert "stage:primary" in est.flags
    assert i30.calls == 0 and gate.calls == 0


def test_primary_raw_hr_is_used_when_primary_self_abstained_but_clears_tau():
    c3 = FixedEstimator("c3", None, 0.95, raw=81.0)
    est = _cascade(c3, FixedEstimator("i30", 70.0, 0.9), CountingGate(0.0)).estimate(T, RGB)
    assert est[CASCADE_METHOD].hr_bpm == 81.0


def test_s7_flicker_abstains_when_a1_detects_exposure_event():
    """C3 unsure + A1 p(exposure_event) >= theta: I30 is blocked (the S7 alias-lock case)."""
    c3 = FixedEstimator("c3", 72.0, 0.40)
    i30 = FixedEstimator("i30", 136.0, 0.80)  # aliased onto the flicker line
    gate = CountingGate(0.30)
    est = _cascade(c3, i30, gate).estimate(T, RGB)[CASCADE_METHOD]
    assert est.abstained
    assert ALIAS_GUARD_FLAG in est.flags
    assert est.raw_hr_bpm == 136.0  # kept for risk-coverage analysis
    assert gate.calls == 1


def test_no_exposure_event_lets_fallback_answer_with_rescaled_confidence():
    c3, i30 = FixedEstimator("c3", 72.0, 0.40), FixedEstimator("i30", 71.0, 0.80)
    est = _cascade(c3, i30, CountingGate(0.01)).estimate(T, RGB)[CASCADE_METHOD]
    assert est.hr_bpm == 71.0
    assert "stage:fallback" in est.flags
    assert est.confidence == pytest.approx(0.80 * TAU_C3_DEFAULT * 0.999)
    assert est.confidence < TAU_C3_DEFAULT  # ranks below every C3 answer


def test_theta_is_inclusive():
    c3, i30 = FixedEstimator("c3", 72.0, 0.4), FixedEstimator("i30", 71.0, 0.8)
    est = _cascade(c3, i30, CountingGate(THETA_EXPOSURE_DEFAULT)).estimate(T, RGB)
    assert est[CASCADE_METHOD].abstained


def test_gate_not_called_when_fallback_abstains():
    gate = CountingGate(0.99)
    est = _cascade(FixedEstimator("c3", 72, 0.4), FixedEstimator("i30", None, 0.3, raw=90.0), gate)
    out = est.estimate(T, RGB)[CASCADE_METHOD]
    assert out.abstained and "fallback_abstain" in out.flags
    assert ALIAS_GUARD_FLAG not in out.flags
    assert gate.calls == 0


def test_theta_none_reproduces_cycle1_cascade():
    c3, i30 = FixedEstimator("c3", 72.0, 0.4), FixedEstimator("i30", 136.0, 0.8)
    spec = AliasAwareCascadeEstimator(primary=c3, fallback=i30, exposure_gate=None, theta=None)
    assert spec.estimate(T, RGB)[CASCADE_METHOD].hr_bpm == 136.0


def test_nan_primary_confidence_falls_through():
    c3, i30 = FixedEstimator("c3", 72.0, float("nan")), FixedEstimator("i30", 70.0, 0.8)
    est = _cascade(c3, i30, CountingGate(0.0)).estimate(T, RGB)[CASCADE_METHOD]
    assert est.hr_bpm == 70.0


def test_config_validation():
    c3 = FixedEstimator("c3", 72, 0.9)
    with pytest.raises(ValueError, match="exposure_gate"):
        AliasAwareCascadeEstimator(primary=c3, exposure_gate=None)
    with pytest.raises(ValueError, match="theta"):
        AliasAwareCascadeEstimator(primary=c3, exposure_gate=CountingGate(0), theta=1.5)


def test_multi_method_stage_is_rejected():
    from learning.eval_kit.estimators import ClassicalEstimator

    spec = _cascade(ClassicalEstimator(), FixedEstimator("i30", 70, 0.8), CountingGate(0))
    with pytest.raises(ValueError, match="exactly one method"):
        spec.estimate(T, RGB)


def _flicker_alias_trace(alias_hz=2.2, seed=7):
    """No pulse, plus a strong in-band luminance oscillation standing in for an aliased 100 Hz
    tube-light flicker (S7). I30 sees a clean periodic signal and answers ~132 BPM."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, 30.0, 1.0 / 30.0)
    flicker = 0.006 * np.sin(2 * np.pi * alias_hz * t)
    rgb = np.array([176.0, 126.0, 101.0])[None, :] * (1.0 + flicker[:, None] * [0.5, 0.9, 0.7])
    return t, rgb + 0.05 * rng.standard_normal(rgb.shape)


def test_real_i30_alias_is_blocked_by_exposure_gate():
    t, rgb = _flicker_alias_trace()
    i30 = PbvI30Estimator()
    alone = i30.estimate(t, rgb)["pbv_i30"]
    assert alone.hr_bpm is not None and abs(alone.hr_bpm - 132.0) < 3.0  # I30 locks on the alias

    c3_unsure = FixedEstimator("c3", None, 0.2, raw=74.0)
    before = AliasAwareCascadeEstimator(primary=c3_unsure, fallback=i30, theta=None)
    after = AliasAwareCascadeEstimator(
        primary=c3_unsure, fallback=i30, exposure_gate=CountingGate(0.9)
    )
    assert before.estimate(t, rgb)[CASCADE_METHOD].hr_bpm == pytest.approx(alone.hr_bpm)
    blocked = after.estimate(t, rgb)[CASCADE_METHOD]
    assert blocked.abstained and ALIAS_GUARD_FLAG in blocked.flags


def test_quality_gate_classifier_reads_exposure_probability():
    classes = ("good", "motion", "exposure_event", "no_face")
    logits = np.log(np.array([0.1, 0.1, 0.7, 0.1]))
    gate = QualityGateClassifier(lambda x: logits, lambda t, rgb: np.zeros((1, 3)), classes)
    assert gate(T, RGB) == pytest.approx(0.7)
    probs = QualityGateClassifier(
        lambda x: [0.2, 0.2, 0.4, 0.2], lambda t, rgb: None, classes, from_logits=False
    )
    assert probs(T, RGB) == pytest.approx(0.4)


def test_quality_gate_classifier_validates_contract():
    with pytest.raises(ValueError, match="exposure_class"):
        QualityGateClassifier(lambda x: [0, 0], lambda t, r: None, ("good", "bad"))
    gate = QualityGateClassifier(lambda x: [0, 0], lambda t, r: None, ("a", "exposure_event", "c"))
    with pytest.raises(ValueError, match="3 class scores"):
        gate(T, RGB)


def test_quality_gate_from_onnx_uses_mock_session(monkeypatch):
    import sys
    import types

    class _Input:
        name = "x"

    class _Session:
        def __init__(self, path, providers=None):
            self.path = path

        def get_inputs(self):
            return [_Input()]

        def run(self, outputs, feeds):
            assert feeds["x"].dtype == np.float32
            return [np.array([[0.0, 0.0, 5.0]])]

    monkeypatch.setitem(
        sys.modules, "onnxruntime", types.SimpleNamespace(InferenceSession=_Session)
    )
    gate = QualityGateClassifier.from_onnx(
        "a1.onnx", lambda t, r: np.zeros((1, 2)), ("good", "motion", "exposure_event")
    )
    assert gate(T, RGB) > 0.98
