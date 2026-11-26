"""CPU Hugging Face Space: POS vs I30 PBV vs the C3 ONNX net, with the 4-rung coaching UX.

What the demo does
------------------
* Simulates a 30 s, 16-patch face capture (``learning.phase2_fastai.phone_degradation``
  presets, plus a no-pulse negative) or reads an uploaded single-ROI ``t_s,r,g,b`` CSV.
* Runs three estimators side by side: classical **POS**, the Cycle-1 winner **I30 PBV**
  (windowed PBV + exposure repair + logistic abstention) and the Cycle-2 **C3 PatchAttnSpec**
  ONNX net (16x300 STMap at 10 Hz, 141 HR bins + abstain), plus the C3 -> I30 cascade.
* Maps I30's quality features onto the PRD's 4-rung coaching ladder (answer / answer-flagged /
  coach-and-retry / abstain) so reviewers see the exact copy a user would see.
* Logs Hamel-style open-coding feedback (verdict, failure tag, free-text note) to a CSV. Rows
  hold estimator outputs and scenario names only: no raw signal, no image, no personal data.

Everything is CPU-only and imports Gradio lazily, so the callbacks can be unit-tested without
Gradio installed. Not a medical device; not for diagnosis.
"""

from __future__ import annotations

import csv
import io
import math
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal


def _ensure_import_root() -> None:
    """Make ``learning`` and ``app`` importable from the repo and from a flat Space bundle."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[2], here.parent):
        if (candidate / "learning").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return


_ensure_import_root()

from app.services.rppg_processor import FrameSample  # noqa: E402
from learning.eval_kit import pbv_i30  # noqa: E402
from learning.eval_kit.estimators import (  # noqa: E402
    N_CLASSES_WITH_ABSTAIN,
    ClassicalEstimator,
    Estimate,
    PbvI30Estimator,
    decode_hr_bins,
)
from learning.eval_kit.synthetic import DC_RGB, PULSE_SIGNATURE  # noqa: E402
from learning.phase2_fastai.phone_degradation import (  # noqa: E402
    degrade_patch_traces,
    frames_to_arrays,
)

DISCLAIMER = "Not a medical device. Not for diagnosis."

# --------------------------------------------------------------------------- #
# C3 input contract (vendored from the Cycle-2 shootout's mp_data.make_stmap)
# --------------------------------------------------------------------------- #

N_PATCHES = 16
FS_STMAP = 10.0
T_STMAP = 300
C3_INPUT_SHAPE = (1, 6, N_PATCHES, T_STMAP)
# Val-tuned tau from the shootout (98.5 % of val no-pulse sessions abstain at this cut).
C3_TAU_VAL_TUNED = 0.686
# A 30 s capture rarely spans a full 29.9 s after drops; make_stmap holds the edge sample.
MIN_C3_SPAN_S = 25.0
C3_DEFAULT_MODEL = (
    Path(__file__).resolve().parent / "models" / "C3_patch_attn_spec_int8_static_convonly.onnx"
)
_BP_STMAP = signal.butter(2, [0.6 / (FS_STMAP / 2), 4.0 / (FS_STMAP / 2)], btype="bandpass")


def _resample(t_s: np.ndarray, x: np.ndarray, fs: float = FS_STMAP, n_out: int = T_STMAP):
    tg = t_s[0] + np.arange(n_out) / fs
    flat = x.reshape(x.shape[0], -1)
    out = np.stack([np.interp(tg, t_s, flat[:, j]) for j in range(flat.shape[1])], axis=1)
    return out.reshape((n_out,) + x.shape[1:])


def make_stmap(t_s: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """``rgb`` (n, P, 3) -> (6, P, 300) float32: RGB/mean-1, YUV, band-passed, robust-scaled."""
    x = _resample(np.asarray(t_s, dtype=float), np.asarray(rgb, dtype=float))
    rn = x / np.maximum(x.mean(0, keepdims=True), 1e-6) - 1.0
    y = 0.299 * rn[..., 0] + 0.587 * rn[..., 1] + 0.114 * rn[..., 2]
    u = rn[..., 2] - y
    v = rn[..., 0] - y
    ch = np.concatenate([rn, y[..., None], u[..., None], v[..., None]], axis=-1)
    b, a = _BP_STMAP
    ch = signal.filtfilt(b, a, ch, axis=0)
    sc = np.median(ch[..., :3].std(0), axis=-1, keepdims=True)
    ch = np.clip(ch / (sc[None] + 1e-9), -6, 6)
    return ch.transpose(2, 1, 0).astype(np.float32)


# --------------------------------------------------------------------------- #
# Synthetic 16-patch sessions
# --------------------------------------------------------------------------- #

# name -> (phone_degradation preset, has_pulse). HR comes from the slider.
SCENARIOS: dict[str, tuple[str, bool]] = {
    "Flagship phone, good light": ("flagship_reference", True),
    "Budget phone, bright room": ("budget_bright", True),
    "Budget phone, Indian indoor light": ("budget_india_indoor", True),
    "Budget phone, dim light + darker skin": ("budget_dim_darker_skin", True),
    "Budget phone, tube-light flicker": ("budget_tubelight_flicker", True),
    "Budget phone, head motion": ("budget_motion", True),
    "Budget phone, worst case": ("budget_worst_case", True),
    "No pulse (photo / mask)": ("budget_india_indoor", False),
}


def simulate_patch_session(
    hr_bpm: float,
    scenario: str,
    seed: int = 0,
    duration_s: float = 30.0,
    n_patches: int = N_PATCHES,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """A 16-patch capture: per-patch DC (+-8 %), lognormal perfusion (sigma 0.25), 0-40 ms delay.

    Returns ``(t_s, rgb (n, P, 3), info)``. This approximates the shootout's ``mp_data``
    sessions; it is a demo signal, not the benchmark.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario!r}")
    preset, has_pulse = SCENARIOS[scenario]
    rng = np.random.default_rng(seed)
    fs = 30.0
    t = np.arange(0.0, duration_s, 1.0 / fs)
    hr_t = hr_bpm + 3.0 * np.sin(2 * math.pi * t / 40.0 + rng.uniform(0, 2 * math.pi))
    phase_rate = 2 * math.pi * hr_t / 60.0
    traces: dict[str, list[FrameSample]] = {}
    for p in range(n_patches):
        dc = DC_RGB * (1.0 + rng.uniform(-0.08, 0.08))
        perfusion = float(rng.lognormal(0.0, 0.25))
        delay_s = float(rng.uniform(0.0, 0.040))
        phase = np.cumsum(phase_rate) / fs - phase_rate * delay_s
        wave = np.sin(phase) + 0.35 * np.sin(2 * phase + 0.6)
        ac = 0.006 * perfusion * PULSE_SIGNATURE * (1.0 if has_pulse else 0.0)
        rgb_p = dc[None, :] * (1.0 + ac[None, :] * wave[:, None])
        traces[f"p{p:02d}"] = [
            FrameSample(
                t_ms=float(ti * 1000.0), r_mean=float(c[0]), g_mean=float(c[1]), b_mean=float(c[2])
            )
            for ti, c in zip(t, rgb_p, strict=True)
        ]
    degraded = degrade_patch_traces(traces, preset, seed=seed)
    arrays = [frames_to_arrays(frames) for frames in degraded.patch_frames.values()]
    t_s = arrays[0][0]
    rgb = np.stack(
        [np.stack([np.interp(t_s, ti, ci[:, k]) for k in range(3)], 1) for ti, ci in arrays], 1
    )
    info = {
        "preset": preset,
        "has_pulse": has_pulse,
        "true_hr_bpm": float(np.mean(hr_t)) if has_pulse else None,
        "delivered_fps": round(degraded.delivered_fps, 1),
        "events": sorted({e.kind for e in degraded.events}) if degraded.events else [],
    }
    return t_s, rgb, info


# --------------------------------------------------------------------------- #
# C3 ONNX
# --------------------------------------------------------------------------- #


@dataclass
class C3Model:
    """Thin onnxruntime wrapper; ``predict`` returns 142 logits for one (6, 16, 300) STMap."""

    path: Path
    session: Any = field(repr=False, default=None)

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> C3Model | None:
        model_path = Path(path or os.environ.get("PRANASCAN_C3_ONNX", C3_DEFAULT_MODEL))
        if not model_path.is_file():
            return None
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
        sess = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
        return cls(model_path, sess)

    def predict(self, stmap: np.ndarray) -> np.ndarray:
        x = np.asarray(stmap, dtype=np.float32).reshape(C3_INPUT_SHAPE)
        name = self.session.get_inputs()[0].name
        return np.asarray(self.session.run(None, {name: x})[0]).ravel()


_C3_CACHE: dict[str, C3Model | None] = {}


def get_c3_model() -> C3Model | None:
    key = os.environ.get("PRANASCAN_C3_ONNX", str(C3_DEFAULT_MODEL))
    if key not in _C3_CACHE:
        _C3_CACHE[key] = C3Model.load(key)
    return _C3_CACHE[key]


def c3_estimate(
    t_s: np.ndarray,
    rgb_patches: np.ndarray,
    tau: float = C3_TAU_VAL_TUNED,
    model: C3Model | Callable[[np.ndarray], np.ndarray] | None = None,
) -> Estimate:
    """C3 on a (n, 16, 3) capture. Abstains when the abstain class wins or conf < tau."""
    model = model if model is not None else get_c3_model()
    if model is None:
        return Estimate("c3_onnx", None, float("nan"), None, ("model_not_loaded",))
    if rgb_patches.ndim != 3 or rgb_patches.shape[1] != N_PATCHES:
        return Estimate("c3_onnx", None, float("nan"), None, ("needs_16_patches",))
    if float(t_s[-1] - t_s[0]) < MIN_C3_SPAN_S:
        return Estimate("c3_onnx", None, float("nan"), None, ("needs_30s",))
    predict = model.predict if isinstance(model, C3Model) else model
    logits = np.asarray(predict(make_stmap(t_s, rgb_patches)), dtype=float).ravel()
    if logits.size != N_CLASSES_WITH_ABSTAIN:
        return Estimate("c3_onnx", None, float("nan"), None, (f"bad_output:{logits.size}",))
    raw, conf, p_abstain = decode_hr_bins(logits)
    flags = [f"p_abstain:{p_abstain:.3f}"]
    if raw is None:
        flags.append("abstain_class")
    hr = raw if raw is not None and conf >= tau else None
    if raw is not None and hr is None:
        flags.append("low_confidence_abstain")
    return Estimate("c3_onnx", hr, conf, raw, tuple(flags))


def cascade(c3: Estimate, i30: Estimate) -> Estimate:
    """C3 when it answers; else I30 when it answers; else abstain."""
    if c3.hr_bpm is not None:
        return Estimate("cascade", c3.hr_bpm, c3.confidence, c3.raw_hr_bpm, ("from:c3",))
    if i30.hr_bpm is not None:
        return Estimate("cascade", i30.hr_bpm, i30.confidence, i30.raw_hr_bpm, ("from:i30",))
    return Estimate("cascade", None, float("nan"), None, ("abstain",))


# --------------------------------------------------------------------------- #
# 4-rung coaching ladder (PRD), driven by I30
# --------------------------------------------------------------------------- #

MAX_RETRIES = 2
TIPS = {
    "light": "Move to brighter, even light facing you.",
    "motion": "Rest your phone on something and keep your head still.",
    "flicker": "Hold steady and avoid tube light; try daylight or a warm bulb.",
    "occlusion": "Make sure your forehead is uncovered (hair, cap, dupatta).",
    "no_pulse": "We couldn't find a pulse signal. Try again facing the light.",
}


@dataclass(frozen=True)
class Coaching:
    rung: int  # 1..4
    title: str
    message: str
    cause: str | None
    show_hr: bool
    show_hrv: bool


def _likely_cause(features: Mapping[str, float], n_exposure_steps: int) -> str:
    def f(key: str, default: float) -> float:
        v = features.get(key, default)
        return default if v is None or not math.isfinite(v) else float(v)

    if n_exposure_steps > 0:
        return "flicker"
    if f("win_mad", 0.0) > 4.0 or f("win_agree", 1.0) < 0.6:
        return "motion"
    if f("pmr_db", 99.0) < 6.0 or f("prom_db", 99.0) < 3.0:
        return "light"
    return "occlusion"


def coaching_rung(result: pbv_i30.HRResult, retries: int = 0, tau: float = pbv_i30.TAU) -> Coaching:
    """Map one I30 result (and the retry count so far) onto the PRD's 4 rungs."""
    feats = result.features or {}
    conf = result.confidence if math.isfinite(result.confidence) else 0.0
    if result.raw_hr_bpm is not None and conf >= tau:
        agree = feats.get("win_agree", 0.0)
        if agree is not None and math.isfinite(agree) and agree >= 0.999:
            return Coaching(
                1, "Answer", f"Your heart rate is {result.raw_hr_bpm:.0f} BPM.", None, True, True
            )
        return Coaching(
            2,
            "Answer, flagged",
            f"Your heart rate is {result.raw_hr_bpm:.0f} BPM. "
            "Beat timing was noisy, so we're not showing HRV this time.",
            None,
            True,
            False,
        )
    no_pulse = result.raw_hr_bpm is None
    if retries >= MAX_RETRIES or (no_pulse and retries >= 1):
        return Coaching(
            4,
            "Abstain",
            "We couldn't read your glow today. Please try again later.",
            "no_pulse" if no_pulse else None,
            False,
            False,
        )
    cause = "no_pulse" if no_pulse else _likely_cause(feats, result.n_exposure_steps)
    left = MAX_RETRIES - retries
    return Coaching(
        3,
        "Coach & retry",
        f"{TIPS[cause]} Free retry ({left} left).",
        cause,
        False,
        False,
    )


# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #

TABLE_HEADERS = ["Method", "HR (BPM)", "Confidence", "Decision", "Flags"]


def _row(e: Estimate) -> list[Any]:
    hr = "—" if e.hr_bpm is None else round(e.hr_bpm, 1)
    conf = "—" if not math.isfinite(e.confidence) else round(e.confidence, 3)
    if e.hr_bpm is not None:
        decision = "answer"
    elif "model_not_loaded" in e.flags:
        decision = "not loaded"
    elif "needs_16_patches" in e.flags:
        decision = "n/a"
    else:
        decision = "abstain"
    return [e.method, hr, conf, decision, ", ".join(e.flags)]


def _estimate_all(t_s, rgb_patches, c3_tau, model=None) -> tuple[list[Estimate], pbv_i30.HRResult]:
    mean_rgb = rgb_patches.mean(axis=1) if rgb_patches.ndim == 3 else rgb_patches
    pos = ClassicalEstimator(("pos",)).estimate(t_s, mean_rgb)["pos"]
    i30_raw = pbv_i30.estimate_hr(t_s, mean_rgb)
    i30 = PbvI30Estimator().estimate(t_s, mean_rgb)[PbvI30Estimator.methods[0]]
    c3 = c3_estimate(t_s, rgb_patches, tau=float(c3_tau), model=model)
    return [pos, i30, c3, cascade(c3, i30)], i30_raw


def _format_coaching(c: Coaching) -> str:
    return f"### Rung {c.rung}: {c.title}\n\n{c.message}\n\n_{DISCLAIMER}_"


def run_comparison(
    scenario: str,
    hr_bpm: float = 72.0,
    seed: int = 0,
    c3_tau: float = C3_TAU_VAL_TUNED,
    retries: int = 0,
    model: Any = None,
) -> tuple[list[list[Any]], str, dict[str, Any]]:
    """Simulate one capture and compare. Returns ``(table rows, coaching markdown, state)``."""
    t_s, rgb, info = simulate_patch_session(float(hr_bpm), scenario, seed=int(seed))
    estimates, i30_raw = _estimate_all(t_s, rgb, c3_tau, model=model)
    coach = coaching_rung(i30_raw, retries=int(retries))
    state = {
        "source": "synthetic",
        "scenario": scenario,
        "seed": int(seed),
        "true_hr_bpm": info["true_hr_bpm"],
        "delivered_fps": info["delivered_fps"],
        "rung": coach.rung,
        "estimates": {e.method: (e.hr_bpm, e.confidence) for e in estimates},
    }
    return [_row(e) for e in estimates], _format_coaching(coach), state


def parse_trace_csv(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse a ``t_s,r,g,b`` CSV (header optional) into sorted, de-duplicated arrays."""
    rows: list[list[float]] = []
    for line in csv.reader(io.StringIO(text)):
        if not line or not line[0].strip():
            continue
        try:
            rows.append([float(v) for v in line[:4]])
        except ValueError:
            if rows:
                raise
            continue  # header
    arr = np.asarray(rows, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 4 or arr.shape[0] < 60:
        raise ValueError("Need at least 60 rows of t_s,r,g,b")
    arr = arr[np.argsort(arr[:, 0])]
    keep = np.r_[True, np.diff(arr[:, 0]) > 0]
    return arr[keep, 0], arr[keep, 1:4]


def analyze_csv(file_or_text: Any, retries: int = 0) -> tuple[list[list[Any]], str, dict[str, Any]]:
    """Single-ROI upload: POS and I30 run; C3 is shown as n/a (it needs 16 patches)."""
    if hasattr(file_or_text, "name") and not isinstance(file_or_text, str):
        text = Path(file_or_text.name).read_text()
    elif isinstance(file_or_text, str | os.PathLike) and Path(str(file_or_text)).is_file():
        text = Path(str(file_or_text)).read_text()
    else:
        text = str(file_or_text)
    t_s, rgb = parse_trace_csv(text)
    estimates, i30_raw = _estimate_all(t_s, rgb, C3_TAU_VAL_TUNED)
    coach = coaching_rung(i30_raw, retries=int(retries))
    state = {
        "source": "csv_upload",
        "scenario": "upload",
        "seed": -1,
        "true_hr_bpm": None,
        "rung": coach.rung,
        "estimates": {e.method: (e.hr_bpm, e.confidence) for e in estimates},
    }
    return [_row(e) for e in estimates], _format_coaching(coach), state


FEEDBACK_FIELDS = [
    "utc",
    "source",
    "scenario",
    "seed",
    "true_hr_bpm",
    "rung",
    "pos_hr",
    "i30_hr",
    "i30_conf",
    "c3_hr",
    "c3_conf",
    "cascade_hr",
    "verdict",
    "tag",
    "note",
]
VERDICTS = ["pass", "fail", "unsure"]
FAILURE_TAGS = [
    "wrong_hr",
    "should_have_abstained",
    "abstained_wrongly",
    "wrong_coaching_tip",
    "alias_or_harmonic",
    "confusing_copy",
    "other",
]


def feedback_path() -> Path:
    default = Path(__file__).resolve().parent / "feedback" / "feedback_log.csv"
    return Path(os.environ.get("PRANASCAN_FEEDBACK_CSV", default))


def _fmt(v: Any) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ""
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def log_feedback(state: Mapping[str, Any] | None, verdict: str, tag: str, note: str = "") -> str:
    """Append one open-coding row (Hamel-style error analysis) to the feedback CSV."""
    if not state:
        return "Run a comparison first."
    if verdict not in VERDICTS:
        return f"Pick a verdict: {', '.join(VERDICTS)}."
    if tag and tag not in FAILURE_TAGS:
        return f"Unknown tag {tag!r}."
    est = state.get("estimates", {})

    def get(method: str, idx: int) -> Any:
        pair = est.get(method)
        return None if pair is None else pair[idx]

    row = {
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": state.get("source", ""),
        "scenario": state.get("scenario", ""),
        "seed": state.get("seed", ""),
        "true_hr_bpm": state.get("true_hr_bpm"),
        "rung": state.get("rung", ""),
        "pos_hr": get("pos", 0),
        "i30_hr": get(PbvI30Estimator.methods[0], 0),
        "i30_conf": get(PbvI30Estimator.methods[0], 1),
        "c3_hr": get("c3_onnx", 0),
        "c3_conf": get("c3_onnx", 1),
        "cascade_hr": get("cascade", 0),
        "verdict": verdict,
        "tag": tag or "",
        "note": " ".join(str(note).split())[:500],
    }
    path = feedback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FEEDBACK_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({k: _fmt(v) for k, v in row.items()})
    return f"Logged a '{verdict}' row to {path.name}."


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #


def build_demo():
    import gradio as gr

    c3_status = "loaded" if get_c3_model() is not None else "not loaded (see README)"
    with gr.Blocks(title="PranaScan rPPG: POS vs I30 vs C3") as demo:
        gr.Markdown(
            "# PranaScan rPPG demo\n"
            "Compare classical **POS**, the Cycle-1 **I30 PBV** pipeline and the Cycle-2 "
            f"**C3 PatchAttnSpec** net (C3 model: {c3_status}) on simulated budget-phone "
            f"captures. Signals are synthetic.\n\n**{DISCLAIMER}**"
        )
        state = gr.State(None)
        with gr.Tab("Simulated capture"):
            with gr.Row():
                scenario = gr.Dropdown(list(SCENARIOS), value=list(SCENARIOS)[2], label="Scenario")
                hr = gr.Slider(45, 160, value=72, step=1, label="True HR (BPM)")
                seed = gr.Number(value=0, precision=0, label="Seed")
            with gr.Row():
                tau = gr.Slider(0.3, 0.95, value=C3_TAU_VAL_TUNED, step=0.001, label="C3 tau")
                retries = gr.Slider(0, MAX_RETRIES, value=0, step=1, label="Retries so far")
            run = gr.Button("Run", variant="primary")
        with gr.Tab("Upload single-ROI CSV"):
            upload = gr.File(label="t_s,r,g,b CSV (30 s)", file_types=[".csv"])
            up_retries = gr.Slider(0, MAX_RETRIES, value=0, step=1, label="Retries so far")
            analyze = gr.Button("Analyze")
        table = gr.Dataframe(headers=TABLE_HEADERS, label="Estimators", interactive=False)
        coaching = gr.Markdown()
        with gr.Accordion("Feedback (open coding)", open=False):
            verdict = gr.Radio(VERDICTS, label="Verdict")
            tag = gr.Dropdown(FAILURE_TAGS, label="Failure tag (optional)")
            note = gr.Textbox(label="Note", lines=2)
            send = gr.Button("Log feedback")
            status = gr.Markdown()
        run.click(run_comparison, [scenario, hr, seed, tau, retries], [table, coaching, state])
        analyze.click(analyze_csv, [upload, up_retries], [table, coaching, state])
        send.click(log_feedback, [state, verdict, tag, note], [status])
    return demo


if __name__ == "__main__":
    build_demo().launch()
