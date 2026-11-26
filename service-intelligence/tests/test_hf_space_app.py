"""Smoke tests for the CPU Hugging Face Space app, with Gradio mocked."""

import csv
import sys
import types

import numpy as np
import pytest

from learning.eval_kit import pbv_i30
from learning.eval_kit.estimators import Estimate
from learning.hf_space import app_gradio_space as app

SCENARIO = "Budget phone, Indian indoor light"


def _peaked_logits(hr_bpm, peak=12.0):
    z = np.zeros(142)
    z[int(round(hr_bpm)) - 40] = peak
    return z


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PRANASCAN_FEEDBACK_CSV", str(tmp_path / "fb.csv"))
    monkeypatch.setenv("PRANASCAN_C3_ONNX", str(tmp_path / "missing.onnx"))
    app._C3_CACHE.clear()
    yield
    app._C3_CACHE.clear()


def test_simulated_session_has_16_patches_and_30s():
    t_s, rgb, info = app.simulate_patch_session(75.0, SCENARIO, seed=1)
    assert rgb.ndim == 3 and rgb.shape[1:] == (16, 3) and rgb.shape[0] == t_s.size
    assert t_s[-1] - t_s[0] > 25 and np.all(np.diff(t_s) > 0)
    assert info["true_hr_bpm"] == pytest.approx(75.0, abs=2.0)
    with pytest.raises(ValueError):
        app.simulate_patch_session(75.0, "nope")


def test_make_stmap_matches_c3_input_contract():
    t_s, rgb, _ = app.simulate_patch_session(80.0, SCENARIO, seed=2)
    x = app.make_stmap(t_s, rgb)
    assert x.shape == (6, 16, 300) and x.dtype == np.float32
    assert np.isfinite(x).all() and np.abs(x).max() <= 6.0


def test_run_comparison_without_c3_model_marks_it_not_loaded():
    rows, md, state = app.run_comparison(SCENARIO, 72, seed=0)
    by_method = {r[0]: r for r in rows}
    assert set(by_method) == {"pos", "pbv_i30", "c3_onnx", "cascade"}
    assert by_method["c3_onnx"][3] == "not loaded"
    assert by_method["pbv_i30"][1] == pytest.approx(72, abs=3)
    assert by_method["cascade"][1] == by_method["pbv_i30"][1]  # falls back to I30
    assert app.DISCLAIMER in md and state["rung"] in (1, 2)


def test_c3_path_with_injected_model_and_tau():
    rows, _, state = app.run_comparison(SCENARIO, 90, seed=0, model=lambda x: _peaked_logits(90))
    c3 = {r[0]: r for r in rows}["c3_onnx"]
    assert c3[3] == "answer" and c3[1] == pytest.approx(90, abs=0.6)
    assert state["estimates"]["cascade"][0] == pytest.approx(90, abs=0.6)

    def weak(x):  # spread-out mass: conf ~0.06 < tau
        return _peaked_logits(90, peak=1.0)

    est = app.c3_estimate(*app.simulate_patch_session(90, SCENARIO)[:2], model=weak)
    assert est.hr_bpm is None and "low_confidence_abstain" in est.flags
    abst = np.zeros(142)
    abst[-1] = 20.0
    est = app.c3_estimate(*app.simulate_patch_session(90, SCENARIO)[:2], model=lambda x: abst)
    assert est.hr_bpm is None and "abstain_class" in est.flags


def test_c3_refuses_single_roi_input():
    t = np.arange(0, 30, 1 / 30)
    est = app.c3_estimate(t, np.ones((t.size, 3)), model=lambda x: _peaked_logits(70))
    assert est.hr_bpm is None and est.flags == ("needs_16_patches",)


def test_onnx_model_loads_and_runs(tmp_path, monkeypatch):
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper

    # x (B,6,16,300) -> ReduceMean over (1,2) -> MatMul (300x142): a stand-in with C3's I/O.
    w = np.zeros((300, 142), np.float32)
    w[:, 30] = 1.0
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["x", "axes"], ["m"], keepdims=0),
            helper.make_node("MatMul", ["m", "w"], ["logits"]),
        ],
        "c3_stub",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, ["batch", 6, 16, 300])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", 142])],
        [
            helper.make_tensor("axes", TensorProto.INT64, [2], [1, 2]),
            helper.make_tensor("w", TensorProto.FLOAT, w.shape, w.ravel()),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 9
    path = tmp_path / "c3_stub.onnx"
    onnx.save(model, path)
    monkeypatch.setenv("PRANASCAN_C3_ONNX", str(path))
    app._C3_CACHE.clear()
    loaded = app.get_c3_model()
    assert loaded is not None
    logits = loaded.predict(np.zeros((6, 16, 300), np.float32))
    assert logits.shape == (142,)
    rows, _, _ = app.run_comparison(SCENARIO, 72, seed=0, c3_tau=0.0)
    assert {r[0]: r for r in rows}["c3_onnx"][3] in ("answer", "abstain")


def _result(hr=72.0, conf=0.9, agree=1.0, mad=0.0, pmr=12.0, prom=8.0, steps=0):
    feats = {"win_agree": agree, "win_mad": mad, "pmr_db": pmr, "prom_db": prom, "entropy": 0.5}
    return pbv_i30.HRResult(hr if conf >= pbv_i30.TAU else None, conf, hr, feats, steps)


def test_coaching_ladder_rungs_and_causes():
    assert app.coaching_rung(_result()).rung == 1
    flagged = app.coaching_rung(_result(agree=0.8))
    assert flagged.rung == 2 and flagged.show_hr and not flagged.show_hrv
    assert app.coaching_rung(_result(conf=0.2, steps=2)).cause == "flicker"
    assert app.coaching_rung(_result(conf=0.2, mad=8.0)).cause == "motion"
    assert app.coaching_rung(_result(conf=0.2, pmr=3.0)).cause == "light"
    assert app.coaching_rung(_result(conf=0.2)).cause == "occlusion"
    retry = app.coaching_rung(_result(conf=0.2, pmr=3.0), retries=1)
    assert retry.rung == 3 and "1 left" in retry.message and not retry.show_hr
    final = app.coaching_rung(_result(conf=0.2), retries=2)
    assert final.rung == 4 and not final.show_hr and "glow" in final.message
    no_pulse = pbv_i30.HRResult(None, float("nan"), None, {}, 0)
    assert app.coaching_rung(no_pulse).cause == "no_pulse"
    assert app.coaching_rung(no_pulse, retries=1).rung == 4


def test_feedback_logger_appends_open_coding_rows(tmp_path):
    _, _, state = app.run_comparison(SCENARIO, 72, seed=0)
    assert "Run a comparison" in app.log_feedback(None, "pass", "")
    assert "Pick a verdict" in app.log_feedback(state, "maybe", "")
    assert "Unknown tag" in app.log_feedback(state, "fail", "bogus")
    assert "Logged" in app.log_feedback(state, "fail", "wrong_hr", "  off by\n10 BPM ")
    assert "Logged" in app.log_feedback(state, "pass", "", "")
    with open(tmp_path / "fb.csv") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2 and list(rows[0]) == app.FEEDBACK_FIELDS
    assert rows[0]["tag"] == "wrong_hr" and rows[0]["note"] == "off by 10 BPM"
    assert rows[0]["scenario"] == SCENARIO and rows[0]["c3_hr"] == ""


def test_analyze_csv_single_roi_upload(tmp_path):
    t = np.arange(0, 30, 1 / 30)
    ph = 2 * np.pi * 66 / 60 * t
    g = 126 * (1 + 0.004 * (np.sin(ph) + 0.35 * np.sin(2 * ph)))
    lines = ["t_s,r,g,b"] + [
        f"{a:.4f},{176.0:.3f},{b:.4f},{101.0:.3f}" for a, b in zip(t, g, strict=False)
    ]
    path = tmp_path / "trace.csv"
    path.write_text("\n".join(lines))
    rows, md, state = app.analyze_csv(str(path))
    by_method = {r[0]: r for r in rows}
    assert by_method["c3_onnx"][3] in ("n/a", "not loaded")
    assert by_method["pbv_i30"][1] == pytest.approx(66, abs=2)
    assert state["source"] == "csv_upload" and app.DISCLAIMER in md
    with pytest.raises(ValueError):
        app.parse_trace_csv("t_s,r,g,b\n0,1,2,3\n")


def test_cascade_order():
    c3 = Estimate("c3_onnx", 80.0, 0.9)
    i30 = Estimate("pbv_i30", 82.0, 0.95)
    none = Estimate("x", None, float("nan"))
    assert app.cascade(c3, i30).hr_bpm == 80.0
    assert app.cascade(none, i30).hr_bpm == 82.0
    assert app.cascade(none, none).hr_bpm is None


def test_build_demo_with_mocked_gradio(monkeypatch):
    calls = []

    class Widget:
        def __init__(self, *a, **k):
            calls.append((type(self).__name__, a, k))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def click(self, fn, inputs, outputs):
            calls.append(("click", fn.__name__, len(inputs), len(outputs)))

        def launch(self):
            pass

    names = [
        "Blocks",
        "Markdown",
        "State",
        "Tab",
        "Row",
        "Dropdown",
        "Slider",
        "Number",
        "Button",
        "File",
        "Dataframe",
        "Accordion",
        "Radio",
        "Textbox",
    ]
    fake = types.ModuleType("gradio")
    for n in names:
        setattr(fake, n, type(n, (Widget,), {}))
    monkeypatch.setitem(sys.modules, "gradio", fake)
    demo = app.build_demo()
    assert type(demo).__name__ == "Blocks"
    clicks = {c[1]: c for c in calls if c[0] == "click"}
    assert set(clicks) == {"run_comparison", "analyze_csv", "log_feedback"}
    assert clicks["run_comparison"][2:] == (5, 3)
    assert clicks["log_feedback"][2:] == (4, 1)
