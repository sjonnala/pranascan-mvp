"""Hamel-style error analysis: export the worst sessions for open coding.

Reads the runner's ``per_session.csv`` and ``per_window.csv``, ranks one method's failing
sessions, and writes, for the top N (20-50 recommended):

- ``plots/<session_id>.png``: RGB trace, spectrogram of the I30 pulse signal, and per-window
  predicted vs reference HR (needs matplotlib; skipped with a warning if it is missing).
- ``open_coding.csv``: one row per session with the evidence columns filled in and the coding
  columns left blank for a human: ``failure_mode, root_cause, binary_pass, fix_hypothesis``.

A session fails when the method answered and missed the reference by more than 5 BPM, when it
abstained on a session that has a pulse, or when it answered on a no-pulse session. Ranking puts
false accepts on no-pulse sessions first (a confident wrong answer is the worst outcome), then
answered misses by error size, then abstentions by how many windows were wasted.

Usage::

    python -m learning.eval_kit.error_analysis --eval-dir out/eval --manifest manifest.json \
        --method pbv_i30 --top 30 --output-dir out/eval/error_analysis

Then open ``error_analysis_template.ipynb`` to read the plots and code the failures.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from learning.phase1.common import ensure_output_dir

from . import pbv_i30
from .eval_runner import EvalRow, read_rows_csv
from .manifest import EvalSession, load_manifest
from .metrics import WITHIN_TOL_BPM

CODING_FIELDS = ("failure_mode", "root_cause", "binary_pass", "fix_hypothesis")
OPEN_CODING_FIELDS = (
    "rank",
    "session_id",
    "subject_id",
    "method",
    "failure_kind",
    "hr_pred",
    "hr_raw",
    "hr_ref",
    "abs_err",
    "conf",
    "abstained",
    "window_abstain_rate",
    "window_mae",
    "fitz_group",
    "fps_bin",
    "lighting",
    "motion",
    "device",
    "dataset",
    "flags",
    "plot",
    *CODING_FIELDS,
)
# Suggested starting codes; reviewers may add their own (that is the point of open coding).
SUGGESTED_FAILURE_MODES = (
    "harmonic_lock",
    "motion_artifact",
    "low_light_noise",
    "exposure_step",
    "flicker_alias",
    "low_fps_or_jitter",
    "weak_pulse_darker_skin",
    "false_accept_no_pulse",
    "over_abstention",
    "reference_problem",
)


@dataclass(frozen=True)
class Failure:
    session: EvalRow
    kind: str
    severity: float
    window_abstain_rate: float
    window_mae: float


def _abs_err(row: EvalRow) -> float:
    if row.hr_pred is None or row.hr_ref is None:
        return math.nan
    return abs(row.hr_pred - row.hr_ref)


def classify(row: EvalRow, tol_bpm: float = WITHIN_TOL_BPM) -> str | None:
    """Failure kind for one session row, or ``None`` if it passed."""
    if not row.has_pulse or row.hr_ref is None:
        return "false_accept_no_pulse" if not row.abstained else None
    if row.abstained:
        return "abstained_with_pulse"
    return "answered_miss" if _abs_err(row) > tol_bpm else None


def rank_failures(
    session_rows: Sequence[EvalRow],
    window_rows: Sequence[EvalRow],
    method: str,
    top: int = 30,
    tol_bpm: float = WITHIN_TOL_BPM,
) -> list[Failure]:
    """The ``top`` worst failing sessions for ``method``, most severe first."""
    windows: dict[str, list[EvalRow]] = {}
    for w in window_rows:
        if w.method == method:
            windows.setdefault(w.session_id, []).append(w)

    failures: list[Failure] = []
    for row in session_rows:
        if row.method != method:
            continue
        kind = classify(row, tol_bpm)
        if kind is None:
            continue
        ws = windows.get(row.session_id, [])
        w_abst = float(np.mean([w.abstained for w in ws])) if ws else math.nan
        errs = [_abs_err(w) for w in ws]
        errs = [e for e in errs if math.isfinite(e)]
        w_mae = float(np.mean(errs)) if errs else math.nan
        if kind == "false_accept_no_pulse":
            severity = 1000.0 + (row.conf if math.isfinite(row.conf) else 0.0)
        elif kind == "answered_miss":
            severity = 100.0 + _abs_err(row)
        else:
            severity = w_abst if math.isfinite(w_abst) else 0.0
        failures.append(Failure(row, kind, severity, w_abst, w_mae))
    failures.sort(key=lambda f: (-f.severity, f.session.session_id))
    return failures[: max(0, top)]


def _fmt(v: float | None) -> str | float:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ""
    return round(float(v), 3)


def write_open_coding_csv(path: Path, failures: Sequence[Failure], plot_paths: dict[str, str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OPEN_CODING_FIELDS))
        writer.writeheader()
        for rank, f in enumerate(failures, start=1):
            r = f.session
            writer.writerow(
                {
                    "rank": rank,
                    "session_id": r.session_id,
                    "subject_id": r.subject_id,
                    "method": r.method,
                    "failure_kind": f.kind,
                    "hr_pred": _fmt(r.hr_pred),
                    "hr_raw": _fmt(r.hr_raw),
                    "hr_ref": _fmt(r.hr_ref),
                    "abs_err": _fmt(_abs_err(r)),
                    "conf": _fmt(r.conf),
                    "abstained": r.abstained,
                    "window_abstain_rate": _fmt(f.window_abstain_rate),
                    "window_mae": _fmt(f.window_mae),
                    "fitz_group": r.fitz_group,
                    "fps_bin": r.fps_bin,
                    "lighting": r.lighting,
                    "motion": r.motion,
                    "device": r.device,
                    "dataset": r.dataset,
                    "flags": r.flags,
                    "plot": plot_paths.get(r.session_id, ""),
                    **{k: "" for k in CODING_FIELDS},
                }
            )


def plot_session(
    out_path: Path,
    failure: Failure,
    session: EvalSession,
    window_rows: Sequence[EvalRow],
) -> bool:
    """RGB trace, pulse spectrogram and per-window HR. Returns False without matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    r = failure.session
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    t, rgb = session.t_s, session.rgb

    ax = axes[0]
    for c, colour, name in zip(range(3), ("tab:red", "tab:green", "tab:blue"), "RGB", strict=True):
        ch = rgb[:, c]
        scale = float(np.mean(ch)) or 1.0
        ax.plot(t, ch / scale - 1.0, color=colour, lw=0.7, label=name)
    ax.set_title("ROI mean RGB (relative to channel mean)")
    ax.set_xlabel("time (s)")
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[1]
    pulse = pbv_i30.pulse_signal(t, rgb)
    if pulse is not None and pulse[0].size > 64:
        bvp, fs = pulse
        nfft = 512
        ax.specgram(bvp, NFFT=256, Fs=fs, noverlap=224, pad_to=nfft, cmap="viridis")
        ax.set_ylim(0.6, 4.0)
        ax.set_ylabel("Hz")
        if r.hr_ref is not None:
            ax.axhline(r.hr_ref / 60.0, color="white", ls="--", lw=1, label="reference")
        if r.hr_raw is not None:
            ax.axhline(r.hr_raw / 60.0, color="tab:orange", ls=":", lw=1.5, label="raw estimate")
        ax.legend(loc="upper right", fontsize=8)
    else:
        ax.text(0.5, 0.5, "no pulse signal could be formed", ha="center", va="center")
    ax.set_title("Spectrogram of the I30 pulse signal (0.6-4 Hz)")
    ax.set_xlabel("time (s)")

    ax = axes[2]
    ws = sorted((w for w in window_rows if w.session_id == r.session_id), key=lambda w: w.t_start_s)
    centres = [0.5 * (w.t_start_s + w.t_end_s) for w in ws]
    ax.plot(
        centres, [np.nan if w.hr_ref is None else w.hr_ref for w in ws], "k-", label="reference"
    )
    ax.plot(
        centres,
        [np.nan if w.hr_raw is None else w.hr_raw for w in ws],
        "o",
        mfc="none",
        color="tab:orange",
        label="raw (abstained hollow)",
    )
    ax.plot(
        centres,
        [np.nan if w.hr_pred is None else w.hr_pred for w in ws],
        "o",
        color="tab:blue",
        label="answered",
    )
    ax.set_xlabel("window centre (s)")
    ax.set_ylabel("HR (BPM)")
    ax.set_title("Per-window predicted vs reference HR")
    ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(
        f"{r.session_id} | {r.method} | {failure.kind} | fitz {r.fitz_group}, {r.fps_bin} fps, "
        f"{r.lighting}, {r.motion}"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True


def export(
    eval_dir: str | Path,
    method: str,
    output_dir: str | Path,
    manifest: str | Path | None = None,
    top: int = 30,
    plots: bool = True,
) -> Path:
    """Write ``open_coding.csv`` (and plots when a manifest is given); return the CSV path."""
    eval_dir = Path(eval_dir)
    out = ensure_output_dir(output_dir)
    session_rows = read_rows_csv(eval_dir / "per_session.csv")
    window_rows = read_rows_csv(eval_dir / "per_window.csv")
    failures = rank_failures(session_rows, window_rows, method, top=top)

    plot_paths: dict[str, str] = {}
    if plots and manifest is not None and failures:
        wanted = {f.session.session_id for f in failures}
        sessions = {s.session_id: s for s in load_manifest(manifest) if s.session_id in wanted}
        method_windows = [w for w in window_rows if w.method == method]
        for f in failures:
            sess = sessions.get(f.session.session_id)
            if sess is None:
                continue
            rel = f"plots/{f.session.session_id}.png"
            if plot_session(out / rel, f, sess, method_windows):
                plot_paths[f.session.session_id] = rel
            else:
                warnings.warn("matplotlib is not installed; skipping plots.", stacklevel=2)
                break

    csv_path = out / "open_coding.csv"
    write_open_coding_csv(csv_path, failures, plot_paths)
    return csv_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--eval-dir", type=Path, required=True, help="eval_runner output dir")
    parser.add_argument("--method", default=pbv_i30.__name__.rsplit(".", 1)[-1])
    parser.add_argument("--manifest", type=Path, default=None, help="needed for plots")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.output_dir or (args.eval_dir / "error_analysis")
    path = export(args.eval_dir, args.method, out, args.manifest, args.top, not args.no_plots)
    with path.open(encoding="utf-8") as handle:
        n = sum(1 for _ in handle) - 1
    print(f"Wrote {n} failing sessions for {args.method} to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
