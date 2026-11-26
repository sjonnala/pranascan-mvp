"""Stratified rPPG evaluation runner with fairness and calibration release gates.

Implements the protocol from ``PranaScan-LowCaliber-Phone-Audit.md`` sec. 5 and
``rPPG-Datasets-and-Ethics-Dossier.md`` sec. 3.7 (AI-CV-Mastery, Cycle 1):

1. Every estimator runs on identical traces: 10 s windows with a 2 s hop, plus one estimate
   over the whole session (the product reports a session HR).
2. Results go to long-format CSVs (``per_window.csv``, ``per_session.csv``), one row per
   ``(session, window, method)``.
3. A scorecard (``scorecard.json`` + ``scorecard.md``) reports, per method and level, MAE, RMSE,
   Pearson r, % within 5 BPM, coverage, the risk-coverage curve and AURC, ECE, coverage at
   MAE <= 3 BPM, the no-pulse false-accept rate, and the Fitzpatrick parity gap and
   abstention-rate ratio, each with a subject-level bootstrap 95% CI. Breakdowns by Fitzpatrick
   group, FPS bin, lighting, motion, device and dataset follow.
4. Release gates run on the candidate method: parity gap <= 1.5 BPM and abstention-rate ratio
   <= 1.25 across Fitzpatrick groups. Gates fail closed: fewer than two Fitzpatrick groups with
   enough data is a failure, because fairness cannot be shown. The process exits 0 when every
   gate passes and 1 otherwise, so CI can block a release on it.

Usage::

    cd service-intelligence
    python -m learning.eval_kit.eval_runner --manifest path/to/manifest.json \
        --methods green,chrom,pos,ica,pbv_i30 --candidate pbv_i30 --output-dir out/eval

    # Smoke run on generated synthetic data:
    python -m learning.eval_kit.eval_runner --synthetic --output-dir out/eval_syn

    # A learned model: --plugin my_models.stmap:make_estimator  (returns an EstimatorSpec)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from learning.phase1.common import ensure_output_dir

from . import metrics as mx
from .estimators import (
    BUILTIN_METHODS,
    CLASSICAL_METHODS,
    PBV_METHOD,
    EstimatorSpec,
    build_estimators,
)
from .manifest import EvalSession, delivered_fps, fitz_group, fps_bin, load_manifest

WINDOW_S = 10.0
HOP_S = 2.0
SESSION_WINDOW_ID = "session"
LEVELS = ("window", "session")
STRATA = ("fitz_group", "fps_bin", "lighting", "motion", "device", "dataset")

CSV_FIELDS = (
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
    # Extra columns beyond the protocol's list, used by the scorecard and error analysis.
    "level",
    "subject_id",
    "hr_raw",
    "has_pulse",
    "t_start_s",
    "t_end_s",
    "delivered_fps",
    "flags",
)


@dataclass(frozen=True)
class GateConfig:
    """Release-gate thresholds. ``None`` disables an optional gate."""

    parity_gap_max_bpm: float = 1.5
    abstention_ratio_max: float = 1.25
    min_group_n: int = 5
    level: str = "session"
    # Optional gates from the audit's Stage (c) acceptance table (off unless set).
    mae_max_bpm: float | None = None
    min_coverage: float | None = None
    ece_max: float | None = None
    no_pulse_false_accept_max: float | None = None


@dataclass
class RunConfig:
    window_s: float = WINDOW_S
    hop_s: float = HOP_S
    fitz_scheme: str = "dossier"
    n_boot: int = 1000
    seed: int = 2026
    gates: GateConfig = field(default_factory=GateConfig)


@dataclass
class EvalRow:
    session_id: str
    window_id: str
    method: str
    hr_pred: float | None
    hr_ref: float | None
    conf: float
    abstained: bool
    fitz_group: str
    fps_bin: str
    lighting: str
    motion: str
    device: str
    dataset: str
    level: str
    subject_id: str
    hr_raw: float | None
    has_pulse: bool
    t_start_s: float
    t_end_s: float
    delivered_fps: float
    flags: str = ""


# --------------------------------------------------------------------------- #
# Running estimators
# --------------------------------------------------------------------------- #


def window_starts(t_s: np.ndarray, window_s: float, hop_s: float) -> list[float]:
    if t_s.size < 2:
        return []
    t0, t1 = float(t_s[0]), float(t_s[-1])
    starts = []
    s = t0
    while s + window_s <= t1 + 1e-9:
        starts.append(s)
        s += hop_s
    return starts


def _rows_for_segment(
    session: EvalSession,
    specs: Sequence[EstimatorSpec],
    t_s: np.ndarray,
    rgb: np.ndarray,
    window_id: str,
    level: str,
    start_s: float,
    end_s: float,
    scheme: str,
) -> list[EvalRow]:
    ref = session.reference_hr(start_s, end_s)
    fps = delivered_fps(t_s)
    rows: list[EvalRow] = []
    for spec in specs:
        for method, est in spec.estimate(t_s, rgb).items():
            rows.append(
                EvalRow(
                    session_id=session.session_id,
                    window_id=window_id,
                    method=method,
                    hr_pred=est.hr_bpm,
                    hr_ref=ref,
                    conf=est.confidence,
                    abstained=est.abstained,
                    fitz_group=fitz_group(session.fitzpatrick, scheme),
                    fps_bin=fps_bin(fps),
                    lighting=session.lighting,
                    motion=session.motion,
                    device=session.device,
                    dataset=session.dataset,
                    level=level,
                    subject_id=session.subject_id,
                    hr_raw=est.raw_hr_bpm,
                    has_pulse=session.has_pulse,
                    t_start_s=round(start_s, 3),
                    t_end_s=round(end_s, 3),
                    delivered_fps=round(fps, 3) if math.isfinite(fps) else float("nan"),
                    flags=";".join(est.flags),
                )
            )
    return rows


def evaluate_sessions(
    sessions: Sequence[EvalSession],
    specs: Sequence[EstimatorSpec],
    config: RunConfig | None = None,
) -> list[EvalRow]:
    """Run every estimator on every window and on each whole session."""
    cfg = config or RunConfig()
    rows: list[EvalRow] = []
    for session in sessions:
        t_s, rgb = session.t_s, session.rgb
        for i, start in enumerate(window_starts(t_s, cfg.window_s, cfg.hop_s)):
            end = start + cfg.window_s
            sel = (t_s >= start) & (t_s < end)
            rows.extend(
                _rows_for_segment(
                    session,
                    specs,
                    t_s[sel],
                    rgb[sel],
                    f"w{i:03d}",
                    "window",
                    start,
                    end,
                    cfg.fitz_scheme,
                )
            )
        if t_s.size >= 2:
            rows.extend(
                _rows_for_segment(
                    session,
                    specs,
                    t_s,
                    rgb,
                    SESSION_WINDOW_ID,
                    "session",
                    float(t_s[0]),
                    float(t_s[-1]),
                    cfg.fitz_scheme,
                )
            )
    return rows


# --------------------------------------------------------------------------- #
# Scorecard
# --------------------------------------------------------------------------- #


def _arr(rows: Sequence[EvalRow], attr: str) -> np.ndarray:
    return np.array(
        [np.nan if getattr(r, attr) is None else float(getattr(r, attr)) for r in rows],
        dtype=np.float64,
    )


def _round(x: float, nd: int = 4) -> float | None:
    if x is None or not math.isfinite(x):
        return None if x is None or math.isnan(x) else (math.inf if x > 0 else -math.inf)
    return round(float(x), nd)


def _core_metrics(pred, ref, raw, conf, fitz, min_group_n) -> dict[str, float]:
    curve = mx.risk_coverage(raw, ref, conf)
    par = mx.parity(pred, ref, fitz, min_answered=min_group_n)
    return {
        "mae": mx.mae(pred, ref),
        "rmse": mx.rmse(pred, ref),
        "pearson_r": mx.pearson_r(pred, ref),
        "within5_pct": mx.within_pct(pred, ref),
        "coverage": mx.coverage(pred, ref),
        "aurc": curve.aurc,
        "coverage_at_mae3": mx.coverage_at_risk(curve),
        "ece": mx.expected_calibration_error(raw, ref, conf),
        "no_pulse_false_accept": mx.no_pulse_false_accept_rate(pred, ref),
        "parity_gap_bpm": par.gap_bpm,
        "abstention_ratio": par.abstention_ratio,
    }


def score_method_level(
    rows: Sequence[EvalRow], n_boot: int = 1000, seed: int = 2026, min_group_n: int = 5
) -> dict[str, Any]:
    pred, ref, raw, conf = (_arr(rows, a) for a in ("hr_pred", "hr_ref", "hr_raw", "conf"))
    fitz = np.array([r.fitz_group for r in rows], dtype=object)
    subjects = [r.subject_id for r in rows]
    point = _core_metrics(pred, ref, raw, conf, fitz, min_group_n)

    def _stat(idx: np.ndarray) -> dict[str, float]:
        if idx.size == 0:
            return {k: float("nan") for k in point}
        return _core_metrics(pred[idx], ref[idx], raw[idx], conf[idx], fitz[idx], min_group_n)

    ci = mx.subject_bootstrap(subjects, _stat, n_boot=n_boot, seed=seed) if n_boot > 0 else {}
    curve = mx.risk_coverage(raw, ref, conf)
    par = mx.parity(pred, ref, fitz, min_answered=min_group_n)

    strata: dict[str, dict[str, dict[str, Any]]] = {}
    for stratum in STRATA:
        groups = np.array([getattr(r, stratum) for r in rows], dtype=object)
        table: dict[str, dict[str, Any]] = {}
        for g in sorted({str(x) for x in groups}):
            sel = groups == g
            sub_curve = mx.risk_coverage(raw[sel], ref[sel], conf[sel])
            table[g] = {
                "n": int(sel.sum()),
                "n_with_ref": int(np.isfinite(ref[sel]).sum()),
                "n_subjects": len({subjects[i] for i in np.flatnonzero(sel)}),
                "coverage": _round(mx.coverage(pred[sel], ref[sel])),
                "mae": _round(mx.mae(pred[sel], ref[sel])),
                "rmse": _round(mx.rmse(pred[sel], ref[sel])),
                "within5_pct": _round(mx.within_pct(pred[sel], ref[sel]), 2),
                "coverage_at_mae3": _round(mx.coverage_at_risk(sub_curve)),
                "no_pulse_false_accept": _round(mx.no_pulse_false_accept_rate(pred[sel], ref[sel])),
            }
        strata[stratum] = table

    return {
        "n_items": len(rows),
        "n_with_ref": int(np.isfinite(ref).sum()),
        "n_no_pulse": int(sum(not r.has_pulse for r in rows)),
        "n_subjects": len(set(subjects)),
        "metrics": {
            k: {"value": _round(v), "ci95": [_round(x) for x in ci.get(k, (math.nan, math.nan))]}
            for k, v in point.items()
        },
        "risk_coverage": curve.to_dict(),
        "reliability": mx.reliability_table(raw, ref, conf),
        "fairness": {
            "worst_group": par.worst_group,
            "best_group": par.best_group,
            "group_mae": {k: _round(v) for k, v in par.group_mae.items()},
            "group_abstention_rate": {k: _round(v) for k, v in par.group_abstention.items()},
            "qualifying_groups": list(par.qualifying_groups),
            "min_group_n": min_group_n,
        },
        "strata": strata,
    }


def evaluate_gates(card: dict[str, Any], gates: GateConfig) -> dict[str, Any]:
    m = card["metrics"]
    checks: list[dict[str, Any]] = []
    qualifying = card["fairness"]["qualifying_groups"]

    def _check(name: str, value: Any, threshold: float, op: str, reason: str = "") -> None:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            passed, why = False, reason or "insufficient_data"
        else:
            passed = value <= threshold if op == "<=" else value >= threshold
            why = "" if passed else "threshold_exceeded"
        checks.append(
            {
                "gate": name,
                "value": value,
                "op": op,
                "threshold": threshold,
                "passed": bool(passed),
                "reason": why,
            }
        )

    insufficient = f"needs >= 2 Fitzpatrick groups with >= {gates.min_group_n} items"
    gap = m["parity_gap_bpm"]["value"] if len(qualifying) >= 2 else None
    ratio = m["abstention_ratio"]["value"] if len(qualifying) >= 2 else None
    _check("fitzpatrick_parity_gap_bpm", gap, gates.parity_gap_max_bpm, "<=", insufficient)
    _check("abstention_rate_ratio", ratio, gates.abstention_ratio_max, "<=", insufficient)
    if gates.mae_max_bpm is not None:
        _check("mae_bpm", m["mae"]["value"], gates.mae_max_bpm, "<=")
    if gates.min_coverage is not None:
        _check("coverage", m["coverage"]["value"], gates.min_coverage, ">=")
    if gates.ece_max is not None:
        _check("ece", m["ece"]["value"], gates.ece_max, "<=")
    if gates.no_pulse_false_accept_max is not None:
        _check(
            "no_pulse_false_accept",
            m["no_pulse_false_accept"]["value"],
            gates.no_pulse_false_accept_max,
            "<=",
        )
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def build_scorecard(
    rows: Sequence[EvalRow], candidate: str, config: RunConfig | None = None
) -> dict[str, Any]:
    cfg = config or RunConfig()
    methods = list(dict.fromkeys(r.method for r in rows))
    if candidate not in methods:
        raise ValueError(f"Candidate '{candidate}' was not evaluated; methods: {methods}")
    results: dict[str, dict[str, Any]] = {}
    for method in methods:
        results[method] = {}
        for level in LEVELS:
            subset = [r for r in rows if r.method == method and r.level == level]
            if subset:
                card = score_method_level(subset, cfg.n_boot, cfg.seed, cfg.gates.min_group_n)
                card["confidence_is_probability"] = method not in CLASSICAL_METHODS
                results[method][level] = card
    gate_level = cfg.gates.level
    if gate_level not in results[candidate]:
        raise ValueError(f"No '{gate_level}' rows for candidate '{candidate}'.")
    gates = evaluate_gates(results[candidate][gate_level], cfg.gates)
    return {
        "protocol": {
            "source": "PranaScan-LowCaliber-Phone-Audit.md sec. 5; "
            "rPPG-Datasets-and-Ethics-Dossier.md sec. 3.7",
            "window_s": cfg.window_s,
            "hop_s": cfg.hop_s,
            "fitzpatrick_scheme": cfg.fitz_scheme,
            "bootstrap": {"unit": "subject", "draws": cfg.n_boot, "seed": cfg.seed, "ci": 0.95},
            "within_tol_bpm": mx.WITHIN_TOL_BPM,
            "fixed_error_mae_bpm": mx.FIXED_ERROR_MAE_BPM,
            "gate_config": asdict(cfg.gates),
        },
        "candidate": candidate,
        "gate_level": gate_level,
        "release_gate": gates,
        "methods": results,
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def _csv_value(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, float):
        return "" if math.isnan(v) else round(v, 4)
    return v


def write_rows_csv(path: Path, rows: Sequence[EvalRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for r in rows:
            d = asdict(r)
            writer.writerow({k: _csv_value(d[k]) for k in CSV_FIELDS})


def read_rows_csv(path: str | Path) -> list[EvalRow]:
    def _opt(x: str) -> float | None:
        return None if x == "" else float(x)

    out = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for d in csv.DictReader(handle):
            out.append(
                EvalRow(
                    session_id=d["session_id"],
                    window_id=d["window_id"],
                    method=d["method"],
                    hr_pred=_opt(d["hr_pred"]),
                    hr_ref=_opt(d["hr_ref"]),
                    conf=float(d["conf"]) if d["conf"] else float("nan"),
                    abstained=d["abstained"] == "True",
                    fitz_group=d["fitz_group"],
                    fps_bin=d["fps_bin"],
                    lighting=d["lighting"],
                    motion=d["motion"],
                    device=d["device"],
                    dataset=d["dataset"],
                    level=d["level"],
                    subject_id=d["subject_id"],
                    hr_raw=_opt(d["hr_raw"]),
                    has_pulse=d["has_pulse"] == "True",
                    t_start_s=float(d["t_start_s"]),
                    t_end_s=float(d["t_end_s"]),
                    delivered_fps=float(d["delivered_fps"]) if d["delivered_fps"] else math.nan,
                    flags=d["flags"],
                )
            )
    return out


def _json_default(o: Any) -> Any:
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(type(o))


def _sanitize(o: Any) -> Any:
    """Make floats JSON-safe: inf -> "inf", nan -> None."""
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_sanitize(v) for v in o]
    if isinstance(o, float):
        if math.isnan(o):
            return None
        if math.isinf(o):
            return "inf" if o > 0 else "-inf"
    return o


def _fmt(v: Any, nd: int = 2) -> str:
    if v is None:
        return "–"
    if isinstance(v, str):
        return v
    if isinstance(v, float) and math.isinf(v):
        return "∞"
    return f"{v:.{nd}f}"


def _fmt_ci(metric: dict[str, Any], nd: int = 2) -> str:
    lo, hi = metric["ci95"]
    ci = f" [{_fmt(lo, nd)}, {_fmt(hi, nd)}]" if lo is not None or hi is not None else ""
    return f"{_fmt(metric['value'], nd)}{ci}"


def render_markdown(card: dict[str, Any]) -> str:
    gate = card["release_gate"]
    lvl = card["gate_level"]
    lines = [
        "# rPPG Stratified Evaluation Scorecard",
        "",
        f"**Release gate ({card['candidate']}, {lvl} level): "
        f"{'PASS' if gate['passed'] else 'FAIL'}**",
        "",
        "| Gate | Value | Threshold | Result |",
        "|---|---|---|---|",
    ]
    for c in gate["checks"]:
        result = "pass" if c["passed"] else f"FAIL ({c['reason']})"
        lines.append(
            f"| {c['gate']} | {_fmt(c['value'])} | {c['op']} {c['threshold']} | {result} |"
        )
    fair = card["methods"][card["candidate"]][lvl]["fairness"]
    no_mae = [g for g in fair["qualifying_groups"] if g not in fair["group_mae"]]
    if no_mae:
        lines += [
            "",
            f"Groups left out of the parity gap for too few answered items: {', '.join(no_mae)}. "
            "They still count in the abstention-rate ratio.",
        ]
    p = card["protocol"]
    lines += [
        "",
        f"Windows {p['window_s']:.0f} s, hop {p['hop_s']:.0f} s. 95% CIs from "
        f"{p['bootstrap']['draws']} subject-level bootstrap draws. Fitzpatrick groups: "
        f"{p['fitzpatrick_scheme']} scheme.",
    ]
    for level in LEVELS:
        lines += [
            "",
            f"## Overall, {level} level",
            "",
            "| Method | Coverage | MAE | RMSE | Pearson r | ≤5 BPM % | AURC | ECE | "
            "Cov@MAE≤3 | No-pulse accept | Parity gap | Abstain ratio |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for method, levels in card["methods"].items():
            if level not in levels:
                continue
            m = levels[level]["metrics"]
            ece = _fmt_ci(m["ece"], 3)
            if not levels[level]["confidence_is_probability"]:
                ece += " †"
            lines.append(
                f"| {method} | {_fmt_ci(m['coverage'])} | {_fmt_ci(m['mae'])} | "
                f"{_fmt_ci(m['rmse'])} | {_fmt_ci(m['pearson_r'])} | "
                f"{_fmt_ci(m['within5_pct'], 1)} | {_fmt_ci(m['aurc'])} | {ece} | "
                f"{_fmt_ci(m['coverage_at_mae3'])} | {_fmt_ci(m['no_pulse_false_accept'])} | "
                f"{_fmt_ci(m['parity_gap_bpm'])} | {_fmt_ci(m['abstention_ratio'])} |"
            )
    lines += [
        "",
        "† Classical confidence is the spectral quality score, not a probability; its ECE shows "
        "that it is uncalibrated.",
    ]
    for stratum in ("fitz_group", "fps_bin", "lighting"):
        lines += [
            "",
            f"## By {stratum} ({lvl} level)",
            "",
            "| Method | Group | n | Coverage | MAE | ≤5 BPM % | Cov@MAE≤3 |",
            "|---|---|---|---|---|---|---|",
        ]
        for method, levels in card["methods"].items():
            if lvl not in levels:
                continue
            for g, s in levels[lvl]["strata"][stratum].items():
                lines.append(
                    f"| {method} | {g} | {s['n']} | {_fmt(s['coverage'])} | {_fmt(s['mae'])} | "
                    f"{_fmt(s['within5_pct'], 1)} | {_fmt(s['coverage_at_mae3'])} |"
                )
    lines += [
        "",
        "A model that lowers darker-skin error by refusing those users is not fixed: read the "
        "abstention ratio next to the parity gap.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(output_dir: str | Path, rows: Sequence[EvalRow], card: dict[str, Any]) -> Path:
    out = ensure_output_dir(output_dir)
    write_rows_csv(out / "per_window.csv", [r for r in rows if r.level == "window"])
    write_rows_csv(out / "per_session.csv", [r for r in rows if r.level == "session"])
    (out / "scorecard.json").write_text(
        json.dumps(_sanitize(card), indent=2, default=_json_default) + "\n", encoding="utf-8"
    )
    (out / "scorecard.md").write_text(render_markdown(card), encoding="utf-8")
    return out


def run(
    sessions: Sequence[EvalSession],
    specs: Sequence[EstimatorSpec],
    candidate: str,
    output_dir: str | Path,
    config: RunConfig | None = None,
) -> tuple[int, dict[str, Any]]:
    """Evaluate, write outputs and return ``(exit_code, scorecard)``."""
    cfg = config or RunConfig()
    rows = evaluate_sessions(sessions, specs, cfg)
    card = build_scorecard(rows, candidate, cfg)
    write_outputs(output_dir, rows, card)
    return (0 if card["release_gate"]["passed"] else 1), card


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--manifest", type=Path, help="DatasetSessionV2 manifest JSON")
    src.add_argument("--synthetic", action="store_true", help="generate a synthetic manifest")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--methods", default=",".join(BUILTIN_METHODS))
    parser.add_argument("--plugin", action="append", default=[], help="module:factory")
    parser.add_argument("--candidate", default=None, help="method the release gate applies to")
    parser.add_argument("--window-s", type=float, default=WINDOW_S)
    parser.add_argument("--hop-s", type=float, default=HOP_S)
    parser.add_argument("--fitz-scheme", choices=("dossier", "audit"), default="dossier")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--gate-level", choices=LEVELS, default="session")
    parser.add_argument("--parity-gap-max", type=float, default=1.5)
    parser.add_argument("--abstention-ratio-max", type=float, default=1.25)
    parser.add_argument("--min-group-n", type=int, default=5)
    parser.add_argument("--mae-max", type=float, default=None)
    parser.add_argument("--min-coverage", type=float, default=None)
    parser.add_argument("--ece-max", type=float, default=None)
    parser.add_argument("--no-pulse-accept-max", type=float, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    specs = build_estimators(methods, args.plugin)
    all_methods = [m for s in specs for m in s.methods]
    candidate = args.candidate or (PBV_METHOD if PBV_METHOD in all_methods else all_methods[-1])

    if args.synthetic:
        from .synthetic import write_synthetic_manifest

        manifest_path = write_synthetic_manifest(args.output_dir / "synthetic_data")
    else:
        manifest_path = args.manifest
    sessions = load_manifest(manifest_path)

    cfg = RunConfig(
        window_s=args.window_s,
        hop_s=args.hop_s,
        fitz_scheme=args.fitz_scheme,
        n_boot=args.bootstrap,
        seed=args.seed,
        gates=GateConfig(
            parity_gap_max_bpm=args.parity_gap_max,
            abstention_ratio_max=args.abstention_ratio_max,
            min_group_n=args.min_group_n,
            level=args.gate_level,
            mae_max_bpm=args.mae_max,
            min_coverage=args.min_coverage,
            ece_max=args.ece_max,
            no_pulse_false_accept_max=args.no_pulse_accept_max,
        ),
    )
    code, card = run(sessions, specs, candidate, args.output_dir, cfg)
    verdict = "PASS" if code == 0 else "FAIL"
    print(f"Release gate for {candidate} ({cfg.gates.level} level): {verdict}")
    for c in card["release_gate"]["checks"]:
        print(
            f"  {c['gate']}: {c['value']} {c['op']} {c['threshold']} -> "
            f"{'pass' if c['passed'] else 'FAIL ' + c['reason']}"
        )
    print(f"Outputs in {args.output_dir}")
    return code


if __name__ == "__main__":
    sys.exit(main())
