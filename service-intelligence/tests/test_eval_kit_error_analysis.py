"""Tests for the error-analysis export and the notebook template."""

import csv
import json
from pathlib import Path

import pytest

from learning.eval_kit import eval_runner as er
from learning.eval_kit.error_analysis import CODING_FIELDS, classify, export, rank_failures
from learning.eval_kit.estimators import build_estimators
from learning.eval_kit.manifest import load_manifest
from learning.eval_kit.synthetic import write_synthetic_manifest


def _row(**kw):
    base = {
        "session_id": "s",
        "window_id": "session",
        "method": "m",
        "hr_pred": 70.0,
        "hr_ref": 70.0,
        "conf": 0.9,
        "abstained": False,
        "fitz_group": "I-II",
        "fps_bin": ">=25",
        "lighting": "bright",
        "motion": "still",
        "device": "d",
        "dataset": "x",
        "level": "session",
        "subject_id": "u",
        "hr_raw": 70.0,
        "has_pulse": True,
        "t_start_s": 0.0,
        "t_end_s": 30.0,
        "delivered_fps": 30.0,
    }
    base.update(kw)
    return er.EvalRow(**base)


def test_classify_failure_kinds():
    assert classify(_row()) is None
    assert classify(_row(hr_pred=80.0, hr_raw=80.0)) == "answered_miss"
    assert classify(_row(hr_pred=None, abstained=True)) == "abstained_with_pulse"
    assert classify(_row(hr_ref=None, has_pulse=False)) == "false_accept_no_pulse"
    assert classify(_row(hr_ref=None, has_pulse=False, hr_pred=None, abstained=True)) is None


def test_rank_puts_false_accepts_first_then_biggest_misses():
    rows = [
        _row(session_id="miss_small", hr_pred=76.0),
        _row(session_id="miss_big", hr_pred=95.0),
        _row(session_id="false_accept", hr_ref=None, has_pulse=False),
        _row(session_id="ok"),
        _row(session_id="abstain", hr_pred=None, abstained=True),
    ]
    ranked = [f.session.session_id for f in rank_failures(rows, [], "m", top=10)]
    assert ranked == ["false_accept", "miss_big", "miss_small", "abstain"]
    assert len(rank_failures(rows, [], "m", top=2)) == 2


def test_export_writes_open_coding_csv(tmp_path):
    manifest = write_synthetic_manifest(
        tmp_path / "data",
        n_subjects_per_type=2,
        captures=("dim",),
        fitzpatrick_types=(5, 6),
        duration_s=20.0,
    )
    er.run(
        load_manifest(manifest),
        build_estimators(["green"]),
        "green",
        tmp_path / "eval",
        er.RunConfig(n_boot=0),
    )
    path = export(tmp_path / "eval", "green", tmp_path / "ea", manifest=manifest, top=20)
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "green should fail on at least one dim, darker-skin synthetic session"
    assert set(CODING_FIELDS) <= set(rows[0])
    assert all(r[k] == "" for r in rows for k in CODING_FIELDS)
    assert [int(r["rank"]) for r in rows] == list(range(1, len(rows) + 1))
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        assert all(r["plot"] == "" for r in rows)
    else:
        assert (tmp_path / "ea" / rows[0]["plot"]).exists()


def test_notebook_template_is_valid():
    nb_path = (
        Path(__file__).resolve().parents[1]
        / "learning"
        / "eval_kit"
        / "error_analysis_template.ipynb"
    )
    nb = json.loads(nb_path.read_text())
    assert nb["nbformat"] == 4 and nb["cells"]
    code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    compile(code.replace("%matplotlib inline", ""), "notebook", "exec")
    for field in CODING_FIELDS:
        assert field in code
    pytest.importorskip("nbformat").validate(
        pytest.importorskip("nbformat").reads(nb_path.read_text(), as_version=4)
    )
