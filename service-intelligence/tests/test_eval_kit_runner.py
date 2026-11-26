"""End-to-end tests for the eval runner on synthetic data, plus release-gate logic."""

import csv
import json

import numpy as np
import pytest

from learning.eval_kit import eval_runner as er
from learning.eval_kit.estimators import Estimate, ModelEstimator, build_estimators
from learning.eval_kit.manifest import EvalSession, constant_reference, load_manifest
from learning.eval_kit.synthetic import clean_trace, write_synthetic_manifest

REQUIRED = [
    "session_id",
    "window_id",
    "method",
    "hr_pred",
    "hr_ref",
    "conf",
    "abstained",
    "fitz_group",
    "fps_bin",
    "lighting",
    "motion",
    "device",
    "dataset",
]


@pytest.fixture(scope="module")
def synthetic_manifest(tmp_path_factory):
    out = tmp_path_factory.mktemp("syn")
    return write_synthetic_manifest(
        out,
        n_subjects_per_type=2,
        captures=("bright",),
        fitzpatrick_types=(1, 3, 5),
        duration_s=20.0,
    )


def test_synthetic_manifest_loads_with_strata(synthetic_manifest):
    sessions = load_manifest(synthetic_manifest)
    assert {s.fitzpatrick for s in sessions} == {1, 3, 5}
    assert any(not s.has_pulse for s in sessions)
    s = next(x for x in sessions if x.has_pulse)
    assert s.reference_hr(0.0, 10.0) is not None
    assert s.lighting == "bright" and s.dataset == "PranaScan-Synthetic"


def test_end_to_end_writes_outputs_and_exit_code(synthetic_manifest, tmp_path):
    sessions = load_manifest(synthetic_manifest)
    specs = build_estimators(["green", "pos", "pbv_i30"])
    cfg = er.RunConfig(n_boot=20, gates=er.GateConfig(min_group_n=2))
    code, card = er.run(sessions, specs, "pbv_i30", tmp_path, cfg)

    assert code in (0, 1)
    assert code == (0 if card["release_gate"]["passed"] else 1)
    for name in ("per_window.csv", "per_session.csv", "scorecard.json", "scorecard.md"):
        assert (tmp_path / name).exists(), name

    with (tmp_path / "per_session.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert set(REQUIRED) <= set(rows[0])
    assert {r["method"] for r in rows} == {"green", "pos", "pbv_i30"}
    assert all(r["window_id"] == "session" for r in rows)
    assert len(rows) == 3 * len(sessions)
    with (tmp_path / "per_window.csv").open() as handle:
        windows = list(csv.DictReader(handle))
    assert len(windows) > len(rows) and windows[0]["window_id"].startswith("w")

    loaded = json.loads((tmp_path / "scorecard.json").read_text())
    m = loaded["methods"]["pbv_i30"]["session"]["metrics"]
    for key in (
        "mae",
        "rmse",
        "pearson_r",
        "within5_pct",
        "aurc",
        "ece",
        "parity_gap_bpm",
        "abstention_ratio",
        "coverage_at_mae3",
        "no_pulse_false_accept",
    ):
        assert key in m and len(m[key]["ci95"]) == 2
    assert {g["gate"] for g in loaded["release_gate"]["checks"]} == {
        "fitzpatrick_parity_gap_bpm",
        "abstention_rate_ratio",
    }
    assert "Release gate" in (tmp_path / "scorecard.md").read_text()


def test_cli_synthetic_returns_gate_exit_code(tmp_path):
    code = er.main(
        ["--synthetic", "--output-dir", str(tmp_path), "--methods", "pbv_i30", "--bootstrap", "0"]
    )
    card = json.loads((tmp_path / "scorecard.json").read_text())
    assert code == (0 if card["release_gate"]["passed"] else 1)


# ---- gates with controlled estimators ----------------------------------------------------- #


class _Oracle:
    """Answers the true HR plus a per-Fitzpatrick bias; abstains on chosen types."""

    methods = ("oracle",)

    def __init__(self, bias_by_level, abstain_types=()):
        self.bias = bias_by_level
        self.abstain = abstain_types
        self.current = None

    def estimate(self, t_s, rgb):
        s = self.current
        if s.fitzpatrick in self.abstain:
            return {"oracle": Estimate("oracle", None, 0.1, 70.0)}
        ref = s.reference_hr(float(t_s[0]), float(t_s[-1])) or 70.0
        hr = ref + self.bias.get(s.fitzpatrick, 0.0)
        return {"oracle": Estimate("oracle", hr, 0.9, hr)}


def _sessions(n_per_type=6):
    out = []
    for fitz in (1, 3, 5):
        for i in range(n_per_type):
            frames, t, _ = clean_trace(70.0, duration_s=12.0, seed=i)
            rgb = np.array([[f.r_mean, f.g_mean, f.b_mean] for f in frames])
            out.append(
                EvalSession(
                    f"f{fitz}_{i}",
                    f"subj_f{fitz}_{i}",
                    t,
                    rgb,
                    constant_reference(70.0),
                    fitzpatrick=fitz,
                )
            )
    return out


def _run_with(oracle, sessions):
    rows = []
    cfg = er.RunConfig(n_boot=0)
    for s in sessions:
        oracle.current = s
        rows += er.evaluate_sessions([s], [oracle], cfg)
    return er.build_scorecard(rows, "oracle", cfg)


def test_gate_passes_when_groups_are_equal():
    card = _run_with(_Oracle({1: 1.0, 3: 1.0, 5: 1.0}), _sessions())
    assert card["release_gate"]["passed"]


def test_gate_fails_on_parity_gap():
    card = _run_with(_Oracle({1: 0.5, 3: 0.5, 5: 3.0}), _sessions())
    checks = {c["gate"]: c for c in card["release_gate"]["checks"]}
    assert not checks["fitzpatrick_parity_gap_bpm"]["passed"]
    assert checks["fitzpatrick_parity_gap_bpm"]["value"] == pytest.approx(2.5)
    assert not card["release_gate"]["passed"]


def test_gate_fails_when_a_group_is_refused():
    card = _run_with(_Oracle({}, abstain_types=(5,)), _sessions())
    checks = {c["gate"]: c for c in card["release_gate"]["checks"]}
    assert checks["fitzpatrick_parity_gap_bpm"]["passed"]  # answered groups look fine...
    assert not checks["abstention_rate_ratio"]["passed"]  # ...but refusing type V fails


def test_gate_fails_closed_without_two_groups():
    sessions = [s for s in _sessions() if s.fitzpatrick == 1]
    card = _run_with(_Oracle({}), sessions)
    assert not card["release_gate"]["passed"]
    assert all(
        c["reason"] == "insufficient_data" or "needs" in c["reason"]
        for c in card["release_gate"]["checks"]
    )


def test_model_estimator_two_vector_and_threshold():
    est = ModelEstimator("m", predict=lambda x: [75.0, 0.4], preprocess=lambda t, c: None, tau=0.5)
    out = est.estimate(np.arange(10.0), np.ones((10, 3)))["m"]
    assert out.abstained and out.raw_hr_bpm == 75.0
    assert "low_confidence_abstain" in out.flags


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        build_estimators(["not_a_method"])
