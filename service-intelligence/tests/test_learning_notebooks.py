"""Smoke tests for the Kaggle T4 starter notebooks (structure, syntax, shootout lessons)."""

import ast
import json
from pathlib import Path

import numpy as np
import pytest

NB_DIR = Path(__file__).resolve().parents[1] / "learning" / "notebooks"
NOTEBOOKS = [
    "01_sqa_tinycnn_fastai_kaggle.ipynb",
    "02_stmap_c3_hr_fastai_kaggle.ipynb",
    "03_voice_mel_gate_fastai_kaggle.ipynb",
]
PINS = ("torch==2.15.0", "fastai==2.8.12", "timm==1.0.31", "onnx==1.23.2", "onnxruntime==1.29.0")


def _load(name):
    return json.loads((NB_DIR / name).read_text())


def _code(nb):
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def _python_only(src):
    """Drop IPython shell/magic lines, which are not Python."""
    return "\n".join(line for line in src.splitlines() if not line.lstrip().startswith(("!", "%")))


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_notebook_is_valid_nbformat_v4(name):
    nb = _load(name)
    assert nb["nbformat"] == 4 and len(nb["cells"]) >= 10
    assert nb["metadata"]["kaggle"]["accelerator"] == "nvidiaTeslaT4"
    nbformat = pytest.importorskip("nbformat")
    nbformat.validate(nbformat.reads((NB_DIR / name).read_text(), as_version=4))


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_code_cells_parse_and_have_no_outputs(name):
    nb = _load(name)
    for i, cell in enumerate(c for c in nb["cells"] if c["cell_type"] == "code"):
        ast.parse(_python_only("".join(cell["source"])), filename=f"{name}#cell{i}")
        assert cell["outputs"] == [] and cell["execution_count"] is None


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_shootout_section6_lessons_are_applied(name):
    nb = _load(name)
    text = "\n".join("".join(c["source"]) for c in nb["cells"])
    code = "\n".join(_code(nb))
    for lesson in ("L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        assert lesson in text, lesson
    for pin in PINS:  # L6
        assert pin in code, pin
    assert "num_workers=0" in code and "torch.float16" in code  # L2
    assert "vision_learner" not in code and "aug_transforms" not in code  # L3
    assert "to_fp16()" in code  # L4
    assert "pretrained=True" not in code  # L5
    assert "dynamo=False" in code and "opset_version=17" in code  # L6
    assert "QuantFormat.QDQ" in code and "quantize_dynamic" not in code  # L7
    assert "fit_one_cycle" in code and "SMOKE" in code


def test_c3_notebook_keeps_spectral_layer_fp32_and_quantizes_conv_only():
    code = "\n".join(_code(_load("02_stmap_c3_hr_fastai_kaggle.ipynb")))
    assert "torch.autocast(device_type=x.device.type, enabled=False)" in code
    assert 'op_types=["Conv", "Gemm"]' in code
    assert "0.985" in code  # tau rule: 98.5 % of val no-pulse sessions abstain


def test_voice_notebook_front_end_shape_and_scenarios():
    nb = _load("03_voice_mel_gate_fastai_kaggle.ipynb")
    code = _code(nb)
    front_end = next(c for c in code if "def logmel3" in c)
    ns = {"np": np}
    exec(compile(front_end, "logmel3", "exec"), ns)  # numpy-only cell
    t = np.arange(22_050) / 4_410
    feats = ns["logmel3"](0.1 * np.sin(2 * np.pi * 200 * t))
    assert feats.shape == (3, 64, 101) and feats.dtype == np.float16
    assert np.isfinite(feats.astype(np.float32)).all()
    assert ns["logmel3"](np.zeros(8_379)).shape == (3, 64, 101)  # 1.9 s buffer is zero-padded
    table = next(c for c in code if "def scenario_table" in c)
    ids = [
        node.args[0].value
        for node in ast.walk(ast.parse(table))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") in ("sp", "nv")
        and isinstance(node.args[0], ast.Constant)
    ]
    assert {"S0", "S2a", "S4c", "S5-buf1.9", "N1", "N4", "N6n", "N8"} <= set(ids)
    assert "MASTER_SEED = 20261126" in "\n".join(code)
