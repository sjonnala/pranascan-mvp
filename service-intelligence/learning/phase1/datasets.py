"""Dataset normalization scaffolding for Phase 1 experiments."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.rppg_processor import FrameSample

from .common import ensure_output_dir, load_frame_samples_csv, write_frame_samples_csv, write_json


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
        session_entry = _materialize_session(session, manifest_file.parent)
        session_output = output_root / session_entry.session_id
        session_output.mkdir(parents=True, exist_ok=True)

        frames = _load_session_frames(session_entry)
        trace_output = session_output / "trace.csv"
        write_frame_samples_csv(trace_output, frames)

        summary = {
            "session_id": session_entry.session_id,
            "normalized_trace_csv": str(trace_output),
            "reference_csv": (
                str(session_entry.reference_csv)
                if session_entry.reference_csv is not None
                else None
            ),
            "trace_columns": session_entry.trace_columns,
            "reference_columns": session_entry.reference_columns,
            "roi_mode": session_entry.roi_mode,
            "patch_name": session_entry.patch_name,
            "frame_count": len(frames),
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


def _materialize_session(session: dict[str, Any], base_dir: Path) -> DatasetSession:
    trace_columns = session.get(
        "trace_columns",
        {
            "t_ms": "t_ms",
            "r_mean": "r_mean",
            "g_mean": "g_mean",
            "b_mean": "b_mean",
        },
    )
    reference_columns = session.get(
        "reference_columns",
        {
            "timestamp_ms": "timestamp_ms",
            "hr_bpm": "hr_bpm",
            "rr_ms": "rr_ms",
        },
    )

    def _resolve(key: str) -> Path | None:
        raw_value = session.get(key)
        if raw_value in (None, ""):
            return None
        path = Path(raw_value)
        return path if path.is_absolute() else base_dir / path

    return DatasetSession(
        session_id=session["session_id"],
        trace_csv=_resolve("trace_csv"),
        video_path=_resolve("video_path"),
        reference_csv=_resolve("reference_csv"),
        trace_columns=trace_columns,
        reference_columns=reference_columns,
        roi_mode=session.get("roi_mode", "mediapipe"),
        patch_name=session.get("patch_name", "forehead"),
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


def _build_validation_command(session: DatasetSession, trace_output: Path) -> str:
    command = [
        "python",
        "scripts/validate_accuracy.py",
        "--trace-csv",
        str(trace_output),
        "--ecg-csv",
        str(session.reference_csv),
    ]

    trace_defaults = {
        "t_ms": "t_ms",
        "r_mean": "r_mean",
        "g_mean": "g_mean",
        "b_mean": "b_mean",
    }
    trace_flag_names = {
        "t_ms": "--trace-time-column",
        "r_mean": "--trace-r-column",
        "g_mean": "--trace-g-column",
        "b_mean": "--trace-b-column",
    }
    for key, default in trace_defaults.items():
        column = session.trace_columns.get(key, default)
        if column != default:
            command.extend([trace_flag_names[key], column])

    reference_defaults = {
        "timestamp_ms": "timestamp_ms",
        "hr_bpm": "hr_bpm",
        "rr_ms": "rr_ms",
    }
    flag_names = {
        "timestamp_ms": "--ecg-time-column",
        "hr_bpm": "--ecg-hr-column",
        "rr_ms": "--ecg-rr-column",
    }
    for key, default in reference_defaults.items():
        column = session.reference_columns.get(key, default)
        if column != default:
            command.extend([flag_names[key], column])

    return " ".join(command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    normalize_dataset_manifest(args.manifest, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
