"""Dataset normalization scaffolding for Phase 1 experiments."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.rppg_processor import FrameSample

from .common import ensure_output_dir, load_frame_samples_csv, write_frame_samples_csv, write_json
from .dataset_model import DatasetSessionV2, session_v2_from_manifest, session_v2_to_dict

TRACE_COLUMN_DEFAULTS: dict[str, str] = {
    "t_ms": "t_ms",
    "r_mean": "r_mean",
    "g_mean": "g_mean",
    "b_mean": "b_mean",
}
REFERENCE_COLUMN_DEFAULTS: dict[str, str] = {
    "timestamp_ms": "timestamp_ms",
    "hr_bpm": "hr_bpm",
    "hrv_rmssd_ms": "hrv_rmssd_ms",
    "stiffness_index": "stiffness_index",
}

# Flag names exactly as scripts/validate_accuracy.py::parse_args defines them (gap G1).
VALIDATOR_TRACE_FLAGS: dict[str, str] = {
    "t_ms": "--trace-t-col",
    "r_mean": "--trace-r-col",
    "g_mean": "--trace-g-col",
    "b_mean": "--trace-b-col",
}
VALIDATOR_REFERENCE_FLAGS: dict[str, str] = {
    "timestamp_ms": "--ecg-t-col",
    "hr_bpm": "--ecg-hr-col",
    "hrv_rmssd_ms": "--ecg-hrv-col",
    "stiffness_index": "--ecg-si-col",
}
# The validator has no RR-interval input; it compares RMSSD (gap G2).
UNSUPPORTED_REFERENCE_KEYS: frozenset[str] = frozenset({"rr_ms"})


@dataclass(frozen=True)
class DatasetSession:
    """Manifest entry for one public-dataset session."""

    session_id: str
    trace_csv: Path | None
    video_path: Path | None
    reference_csv: Path | None
    trace_columns: dict[str, str]
    reference_columns: dict[str, str]
    roi_mode: str
    patch_name: str
    patch_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    session_v2: DatasetSessionV2 | None = None

    @property
    def patches(self) -> tuple[str, ...]:
        """Patches to extract. ``patch_names`` (G4) wins over the legacy ``patch_name``."""
        return self.patch_names or (self.patch_name,)


def normalize_dataset_manifest(
    manifest_path: str | Path,
    output_dir: str | Path,
) -> list[dict[str, Any]]:
    """Normalize all sessions in a manifest into the repo's RGB-trace contract."""
    manifest_file = Path(manifest_path)
    output_root = ensure_output_dir(output_dir)
    manifest = _load_manifest(manifest_file)

    normalized_sessions: list[dict[str, Any]] = []
    validation_commands: list[str] = []

    for session in manifest["sessions"]:
        session_entry = _materialize_session(
            session, manifest_file.parent, manifest["dataset_name"]
        )
        session_output = output_root / session_entry.session_id
        session_output.mkdir(parents=True, exist_ok=True)

        patch_traces = _load_session_patch_traces(session_entry)
        primary_patch = session_entry.patches[0]
        trace_output = session_output / "trace.csv"
        write_frame_samples_csv(trace_output, patch_traces[primary_patch])

        patch_outputs: dict[str, str] = {}
        if len(session_entry.patches) > 1:
            for patch_name in session_entry.patches:
                patch_output = session_output / f"trace_{patch_name}.csv"
                write_frame_samples_csv(patch_output, patch_traces[patch_name])
                patch_outputs[patch_name] = str(patch_output)

        summary: dict[str, Any] = {
            "session_id": session_entry.session_id,
            "normalized_trace_csv": str(trace_output),
            "patch_trace_csvs": patch_outputs,
            "reference_csv": (
                str(session_entry.reference_csv)
                if session_entry.reference_csv is not None
                else None
            ),
            "trace_columns": session_entry.trace_columns,
            "reference_columns": session_entry.reference_columns,
            "roi_mode": session_entry.roi_mode,
            "patch_name": primary_patch,
            "patch_names": list(session_entry.patches),
            "frame_count": len(patch_traces[primary_patch]),
            "ignored_reference_columns": sorted(
                UNSUPPORTED_REFERENCE_KEYS & set(session_entry.reference_columns)
            ),
            "metadata": session_entry.metadata,
            "dataset_session": (
                session_v2_to_dict(session_entry.session_v2)
                if session_entry.session_v2 is not None
                else None
            ),
        }
        write_json(session_output / "summary.json", summary)
        normalized_sessions.append(summary)

        if session_entry.reference_csv is not None:
            validation_commands.append(_build_validation_command(session_entry, trace_output))

    write_json(
        output_root / "normalized_sessions.json",
        {
            "dataset_name": manifest["dataset_name"],
            "sessions": normalized_sessions,
        },
    )
    (output_root / "validation_commands.txt").write_text(
        "\n".join(validation_commands) + ("\n" if validation_commands else ""),
        encoding="utf-8",
    )
    return normalized_sessions


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if "dataset_name" not in manifest or "sessions" not in manifest:
        raise ValueError("Manifest must include 'dataset_name' and 'sessions'.")
    return manifest


def _materialize_session(
    session: dict[str, Any],
    base_dir: Path,
    dataset_name: str = "unknown",
) -> DatasetSession:
    trace_columns = {**TRACE_COLUMN_DEFAULTS, **session.get("trace_columns", {})}
    reference_columns = {**REFERENCE_COLUMN_DEFAULTS, **session.get("reference_columns", {})}

    def _resolve(key: str) -> Path | None:
        raw_value = session.get(key)
        if raw_value in (None, ""):
            return None
        path = Path(raw_value)
        return path if path.is_absolute() else base_dir / path

    raw_patch_names = session.get("patch_names") or []
    if isinstance(raw_patch_names, str):
        raw_patch_names = [raw_patch_names]
    metadata = dict(session.get("metadata") or {})

    # The metadata block is optional (G8). When present it is validated through the
    # domain model, so a manifest cannot mislabel a non-commercial dataset (G7).
    session_v2 = session_v2_from_manifest(session, dataset_name) if metadata else None

    return DatasetSession(
        session_id=session["session_id"],
        trace_csv=_resolve("trace_csv"),
        video_path=_resolve("video_path"),
        reference_csv=_resolve("reference_csv"),
        trace_columns=trace_columns,
        reference_columns=reference_columns,
        roi_mode=session.get("roi_mode", "mediapipe"),
        patch_name=session.get("patch_name", "forehead"),
        patch_names=tuple(raw_patch_names),
        metadata=metadata,
        session_v2=session_v2,
    )


def _load_session_patch_traces(session: DatasetSession) -> dict[str, list[FrameSample]]:
    if session.trace_csv is not None:
        if len(session.patches) > 1:
            raise ValueError(
                f"Session '{session.session_id}' lists several patch_names but a single "
                "trace_csv; multi-patch extraction needs video_path."
            )
        return {session.patches[0]: _load_session_frames(session)}
    if session.video_path is None:
        raise ValueError(
            f"Session '{session.session_id}' must define either trace_csv or video_path."
        )

    from .roi import extract_multi_patch_traces_from_video

    return extract_multi_patch_traces_from_video(
        session.video_path,
        patch_names=list(session.patches),
        roi_mode=session.roi_mode,
    )


def _load_session_frames(session: DatasetSession) -> list[FrameSample]:
    if session.trace_csv is not None:
        return load_frame_samples_csv(session.trace_csv, columns=session.trace_columns)
    if session.video_path is None:
        raise ValueError(
            f"Session '{session.session_id}' must define either trace_csv or video_path."
        )

    from .roi import extract_patch_trace_from_video

    return extract_patch_trace_from_video(
        session.video_path,
        patch_name=session.patch_name,
        roi_mode=session.roi_mode,
    )


def _build_validation_command(
    session: DatasetSession,
    trace_output: Path,
    python_executable: str = "python",
) -> str:
    """Build a ``scripts/validate_accuracy.py`` call that the validator's argparse accepts.

    The normalized ``trace.csv`` is always written with canonical column names, so no
    trace-column flags are needed for it. Reference columns are passed through with
    the validator's own flag names. Paths are shell-quoted.
    """
    command = [
        python_executable,
        "scripts/validate_accuracy.py",
        "--trace-csv",
        str(trace_output),
        "--ecg-csv",
        str(session.reference_csv),
    ]

    for key, flag in VALIDATOR_REFERENCE_FLAGS.items():
        column = session.reference_columns.get(key, REFERENCE_COLUMN_DEFAULTS[key])
        if column != REFERENCE_COLUMN_DEFAULTS[key]:
            command.extend([flag, column])

    return shlex.join(command)


def build_trace_flag_arguments(trace_columns: dict[str, str]) -> list[str]:
    """Validator flags for a raw (non-normalized) trace CSV with custom column names."""
    arguments: list[str] = []
    for key, flag in VALIDATOR_TRACE_FLAGS.items():
        column = trace_columns.get(key, TRACE_COLUMN_DEFAULTS[key])
        if column != TRACE_COLUMN_DEFAULTS[key]:
            arguments.extend([flag, column])
    return arguments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    normalize_dataset_manifest(args.manifest, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
