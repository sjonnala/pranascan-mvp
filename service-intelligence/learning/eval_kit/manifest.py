"""Load a ``DatasetSessionV2`` manifest into evaluation sessions.

The manifest is the Phase 1 format read by ``learning.phase1.datasets`` (``dataset_name`` plus
``sessions`` with ``trace_csv`` or ``video_path``, optional ``reference_csv`` and a ``metadata``
block that becomes a ``DatasetSessionV2``). Two optional metadata keys help synthetic and
negative sessions:

- ``has_pulse: false`` marks a no-pulse session (the correct outcome is abstention).
- ``hr_ref_bpm: 72.0`` gives a constant reference when there is no ``reference_csv``.

Licence: evaluation is a research use, so ``bench_only`` and non-commercial sessions are
allowed here. Nothing in the eval kit trains weights.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from learning.phase1.dataset_model import DatasetSessionV2
from learning.phase1.datasets import (
    DatasetSession,
    _load_session_patch_traces,
    _materialize_session,
)

FITZ_SCHEMES: dict[str, dict[int, str]] = {
    # The dossier's slices (sec. 3.7): III, IV, V, VI separately; I-II pooled.
    "dossier": {1: "I-II", 2: "I-II", 3: "III", 4: "IV", 5: "V", 6: "VI"},
    # The audit's slices (sec. 5.4).
    "audit": {1: "I-II", 2: "I-II", 3: "III-IV", 4: "III-IV", 5: "V-VI", 6: "V-VI"},
}
UNKNOWN = "unknown"

ReferenceFn = Callable[[float, float], "float | None"]


@dataclass
class EvalSession:
    """One recording ready for evaluation (times in seconds from the trace's own clock)."""

    session_id: str
    subject_id: str
    t_s: np.ndarray
    rgb: np.ndarray
    reference: ReferenceFn | None
    has_pulse: bool = True
    fitzpatrick: int | None = None
    lighting: str = UNKNOWN
    motion: str = UNKNOWN
    device: str = UNKNOWN
    dataset: str = UNKNOWN
    extra: dict[str, Any] = field(default_factory=dict)

    def reference_hr(self, start_s: float, end_s: float) -> float | None:
        if not self.has_pulse or self.reference is None:
            return None
        return self.reference(start_s, end_s)


def fitz_group(fitzpatrick: int | None, scheme: str = "dossier") -> str:
    if fitzpatrick is None:
        return UNKNOWN
    try:
        return FITZ_SCHEMES[scheme][int(fitzpatrick)]
    except KeyError as exc:
        raise ValueError(f"Unknown Fitzpatrick scheme '{scheme}' or type {fitzpatrick}") from exc


def fps_bin(delivered_fps: float) -> str:
    """Audit sec. 5.4 bins: <15, 15-20, 20-25, >=25."""
    if not np.isfinite(delivered_fps) or delivered_fps <= 0:
        return UNKNOWN
    if delivered_fps < 15:
        return "<15"
    if delivered_fps < 20:
        return "15-20"
    if delivered_fps < 25:
        return "20-25"
    return ">=25"


def delivered_fps(t_s: np.ndarray) -> float:
    if t_s.size < 2:
        return float("nan")
    span = float(t_s[-1] - t_s[0])
    return (t_s.size - 1) / span if span > 0 else float("nan")


def constant_reference(hr_bpm: float) -> ReferenceFn:
    return lambda _start, _end: float(hr_bpm)


def series_reference(t_s: np.ndarray, hr_bpm: np.ndarray) -> ReferenceFn:
    """Mean reference HR inside the window; nearest interpolation at its centre if empty."""
    t = np.asarray(t_s, dtype=np.float64)
    hr = np.asarray(hr_bpm, dtype=np.float64)
    keep = np.isfinite(t) & np.isfinite(hr)
    t, hr = t[keep], hr[keep]
    order = np.argsort(t)
    t, hr = t[order], hr[order]

    def _ref(start_s: float, end_s: float) -> float | None:
        if t.size == 0:
            return None
        inside = (t >= start_s) & (t <= end_s)
        if inside.any():
            return float(np.mean(hr[inside]))
        centre = 0.5 * (start_s + end_s)
        if centre < t[0] - 2.0 or centre > t[-1] + 2.0:
            return None
        return float(np.interp(centre, t, hr))

    return _ref


def load_reference_csv(path: Path, columns: dict[str, str]) -> ReferenceFn:
    t_col, hr_col = columns.get("timestamp_ms", "timestamp_ms"), columns.get("hr_bpm", "hr_bpm")
    times, values = [], []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                times.append(float(row[t_col]) / 1000.0)
                values.append(float(row[hr_col]) if row.get(hr_col) not in (None, "") else np.nan)
            except (KeyError, ValueError):
                continue
    return series_reference(np.asarray(times), np.asarray(values))


def _strata_from_v2(v2: DatasetSessionV2 | None, dataset_name: str) -> dict[str, Any]:
    if v2 is None:
        return {"subject_id": None, "fitzpatrick": None, "dataset": dataset_name}
    return {
        "subject_id": v2.subject.subject_id,
        "fitzpatrick": v2.subject.fitzpatrick,
        "lighting": v2.capture.lighting or UNKNOWN,
        "motion": v2.capture.motion or UNKNOWN,
        "device": v2.capture.device or UNKNOWN,
        "dataset": v2.dataset,
    }


def session_from_entry(entry: DatasetSession, dataset_name: str) -> EvalSession:
    patch_traces = _load_session_patch_traces(entry)
    frames = patch_traces[entry.patches[0]]
    t_s = np.array([f.t_ms for f in frames], dtype=np.float64) / 1000.0
    rgb = np.array([[f.r_mean, f.g_mean, f.b_mean] for f in frames], dtype=np.float64)
    order = np.argsort(t_s, kind="stable")
    t_s, rgb = t_s[order], rgb[order]

    meta = entry.metadata
    has_pulse = bool(meta.get("has_pulse", True))
    reference: ReferenceFn | None = None
    if entry.reference_csv is not None:
        reference = load_reference_csv(entry.reference_csv, entry.reference_columns)
    elif meta.get("hr_ref_bpm") is not None:
        reference = constant_reference(float(meta["hr_ref_bpm"]))

    strata = _strata_from_v2(entry.session_v2, dataset_name)
    return EvalSession(
        session_id=entry.session_id,
        subject_id=str(strata.get("subject_id") or meta.get("subject_id") or entry.session_id),
        t_s=t_s,
        rgb=rgb,
        reference=reference,
        has_pulse=has_pulse,
        fitzpatrick=strata.get("fitzpatrick"),
        lighting=str(strata.get("lighting", meta.get("lighting", UNKNOWN))),
        motion=str(strata.get("motion", meta.get("motion", UNKNOWN))),
        device=str(strata.get("device", meta.get("device", UNKNOWN))),
        dataset=str(strata.get("dataset") or dataset_name),
        extra={k: v for k, v in meta.items() if k in ("scenario", "preset", "seed")},
    )


def load_manifest(manifest_path: str | Path) -> list[EvalSession]:
    path = Path(manifest_path)
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if "dataset_name" not in manifest or "sessions" not in manifest:
        raise ValueError("Manifest must include 'dataset_name' and 'sessions'.")
    dataset_name = str(manifest["dataset_name"])
    sessions = []
    for raw in manifest["sessions"]:
        entry = _materialize_session(raw, path.parent, dataset_name)
        sessions.append(session_from_entry(entry, dataset_name))
    return sessions
