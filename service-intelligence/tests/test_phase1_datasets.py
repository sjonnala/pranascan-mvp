import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from learning.phase1.common import (
    SyntheticScenarioConfig,
    generate_synthetic_frames,
    write_frame_samples_csv,
)
from learning.phase1.dataset_model import LicenceViolationError
from learning.phase1.datasets import (
    VALIDATOR_REFERENCE_FLAGS,
    VALIDATOR_TRACE_FLAGS,
    build_trace_flag_arguments,
    normalize_dataset_manifest,
)

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _validator_parser_flags() -> set[str]:
    source = (SERVICE_ROOT / "scripts" / "validate_accuracy.py").read_text(encoding="utf-8")
    import re

    return set(re.findall(r'add_argument\("(--[a-z0-9-]+)"', source))


def test_dataset_manifest_normalizes_trace_csv(tmp_path: Path):
    trace_csv = tmp_path / "input_trace.csv"
    trace_csv.write_text(
        "\n".join(
            [
                "t_ms,r_mean,g_mean,b_mean",
                "0,96,112,82",
                "33,97,113,83",
                "66,98,114,84",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reference_csv = tmp_path / "reference.csv"
    reference_csv.write_text("timestamp_ms,hr_bpm,rr_ms\n0,72,833\n", encoding="utf-8")

    manifest = {
        "dataset_name": "fixture",
        "sessions": [
            {
                "session_id": "subject_001",
                "trace_csv": str(trace_csv),
                "reference_csv": str(reference_csv),
            }
        ],
    }
    output_dir = tmp_path / "normalized"
    sessions = normalize_dataset_manifest(_write_manifest(tmp_path, manifest), output_dir)

    assert len(sessions) == 1
    assert (output_dir / "subject_001" / "trace.csv").exists()
    assert (output_dir / "subject_001" / "summary.json").exists()
    commands = (output_dir / "validation_commands.txt").read_text(encoding="utf-8")
    assert "scripts/validate_accuracy.py" in commands


def test_every_emitted_flag_exists_in_the_validator():
    accepted = _validator_parser_flags()
    for flag in [*VALIDATOR_TRACE_FLAGS.values(), *VALIDATOR_REFERENCE_FLAGS.values()]:
        assert flag in accepted, flag


def test_legacy_flag_names_are_rejected_by_the_validator():
    accepted = _validator_parser_flags()
    for legacy in (
        "--trace-time-column",
        "--ecg-time-column",
        "--ecg-hr-column",
        "--ecg-rr-column",
    ):
        assert legacy not in accepted


def test_custom_reference_columns_use_validator_flags(tmp_path: Path):
    frames = generate_synthetic_frames(SyntheticScenarioConfig(duration_s=2.0))
    trace_csv = tmp_path / "trace.csv"
    write_frame_samples_csv(trace_csv, frames)
    reference_csv = tmp_path / "ref.csv"
    reference_csv.write_text("Time,HR,RMSSD\n0,72,40\n", encoding="utf-8")
    manifest = {
        "dataset_name": "fixture",
        "sessions": [
            {
                "session_id": "s1",
                "trace_csv": str(trace_csv),
                "reference_csv": str(reference_csv),
                "reference_columns": {
                    "timestamp_ms": "Time",
                    "hr_bpm": "HR",
                    "hrv_rmssd_ms": "RMSSD",
                    "rr_ms": "RR",
                },
            }
        ],
    }
    out = tmp_path / "out"
    sessions = normalize_dataset_manifest(_write_manifest(tmp_path, manifest), out)
    command = shlex.split((out / "validation_commands.txt").read_text(encoding="utf-8").strip())
    assert command[command.index("--ecg-t-col") + 1] == "Time"
    assert command[command.index("--ecg-hr-col") + 1] == "HR"
    assert command[command.index("--ecg-hrv-col") + 1] == "RMSSD"
    assert not any(token.startswith("--trace-") and token != "--trace-csv" for token in command)
    assert sessions[0]["ignored_reference_columns"] == ["rr_ms"]


def test_trace_flag_helper_maps_custom_columns():
    arguments = build_trace_flag_arguments({"t_ms": "time", "g_mean": "G"})
    assert arguments == ["--trace-t-col", "time", "--trace-g-col", "G"]


def test_paths_with_spaces_are_quoted(tmp_path: Path):
    folder = tmp_path / "with space"
    folder.mkdir()
    frames = generate_synthetic_frames(SyntheticScenarioConfig(duration_s=2.0))
    write_frame_samples_csv(folder / "trace.csv", frames)
    (folder / "ref.csv").write_text("timestamp_ms,hr_bpm\n0,72\n", encoding="utf-8")
    manifest = {
        "dataset_name": "fixture",
        "sessions": [{"session_id": "s1", "trace_csv": "trace.csv", "reference_csv": "ref.csv"}],
    }
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    out = folder / "out dir"
    normalize_dataset_manifest(manifest_path, out)
    command = shlex.split((out / "validation_commands.txt").read_text(encoding="utf-8").strip())
    assert command[command.index("--ecg-csv") + 1] == str(folder / "ref.csv")


def test_generated_command_runs_through_the_validator(tmp_path: Path):
    """Integration: execute the generated command and check argparse and columns."""
    frames = generate_synthetic_frames(SyntheticScenarioConfig(hr_bpm=72.0, noise_std=0.1))
    raw_trace = tmp_path / "raw_trace.csv"
    raw_trace.write_text(
        "time,R,G,B\n" + "".join(f"{f.t_ms},{f.r_mean},{f.g_mean},{f.b_mean}\n" for f in frames),
        encoding="utf-8",
    )
    reference_csv = tmp_path / "reference.csv"
    reference_csv.write_text(
        "Time,HR,RMSSD\n" + "".join(f"{t * 1000},72.0,30.0\n" for t in range(0, 31)),
        encoding="utf-8",
    )
    manifest = {
        "dataset_name": "fixture",
        "sessions": [
            {
                "session_id": "subject 002",
                "trace_csv": str(raw_trace),
                "reference_csv": str(reference_csv),
                "trace_columns": {"t_ms": "time", "r_mean": "R", "g_mean": "G", "b_mean": "B"},
                "reference_columns": {
                    "timestamp_ms": "Time",
                    "hr_bpm": "HR",
                    "hrv_rmssd_ms": "RMSSD",
                },
            }
        ],
    }
    out = tmp_path / "normalized"
    normalize_dataset_manifest(_write_manifest(tmp_path, manifest), out)
    line = (out / "validation_commands.txt").read_text(encoding="utf-8").strip()
    command = shlex.split(line)
    assert command[0] == "python"
    report_path = tmp_path / "report.json"
    command = [sys.executable, *command[1:], "--output-json", str(report_path)]

    completed = subprocess.run(
        command, cwd=SERVICE_ROOT, capture_output=True, text=True, timeout=120, check=False
    )

    assert completed.returncode in (0, 1), completed.stderr
    assert "unrecognized arguments" not in completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))["report"]
    assert report["hr"]["windows"] > 0
    assert report["hr"]["passes"] is True
    assert report["hrv"]["windows"] > 0  # the RMSSD column was read through --ecg-hrv-col


def test_metadata_block_is_validated_and_summarised(tmp_path: Path):
    frames = generate_synthetic_frames(SyntheticScenarioConfig(duration_s=2.0))
    write_frame_samples_csv(tmp_path / "trace.csv", frames)
    manifest = {
        "dataset_name": "LGI-PPGI",
        "sessions": [
            {
                "session_id": "lgi_1",
                "trace_csv": "trace.csv",
                "metadata": {
                    "split": "train",
                    "capture": {"device": "Logitech C270", "nominal_fps": 25, "codec": "raw"},
                    "subject": {"subject_id": "lgi_s1", "fitzpatrick": 2},
                    "reference": {"kind": "ppg_waveform", "sensor": "CMS50E", "fs_hz": 60},
                },
            }
        ],
    }
    sessions = normalize_dataset_manifest(_write_manifest(tmp_path, manifest), tmp_path / "out")
    dataset_session = sessions[0]["dataset_session"]
    assert dataset_session["licence"] == "cc_by_4_0"
    assert dataset_session["commercial_training_allowed"] is True
    assert dataset_session["reference"]["kind"] == "ppg_waveform"


def test_metadata_cannot_put_mmpd_in_a_training_split(tmp_path: Path):
    frames = generate_synthetic_frames(SyntheticScenarioConfig(duration_s=2.0))
    write_frame_samples_csv(tmp_path / "trace.csv", frames)
    manifest = {
        "dataset_name": "MMPD",
        "sessions": [
            {
                "session_id": "mmpd_1",
                "trace_csv": "trace.csv",
                "metadata": {"licence": "cc_by_4_0", "split": "train"},
            }
        ],
    }
    with pytest.raises(LicenceViolationError):
        normalize_dataset_manifest(_write_manifest(tmp_path, manifest), tmp_path / "out")


def test_multiple_patches_need_video(tmp_path: Path):
    frames = generate_synthetic_frames(SyntheticScenarioConfig(duration_s=2.0))
    write_frame_samples_csv(tmp_path / "trace.csv", frames)
    manifest = {
        "dataset_name": "fixture",
        "sessions": [
            {
                "session_id": "s1",
                "trace_csv": "trace.csv",
                "patch_names": ["forehead", "left_cheek"],
            }
        ],
    }
    with pytest.raises(ValueError, match="video_path"):
        normalize_dataset_manifest(_write_manifest(tmp_path, manifest), tmp_path / "out")


def test_multi_patch_video_writes_one_trace_per_patch(tmp_path: Path, monkeypatch):
    frames = generate_synthetic_frames(SyntheticScenarioConfig(duration_s=2.0))

    def fake_extract(video_path, patch_names, roi_mode):
        return {name: frames for name in patch_names}

    import learning.phase1.roi as roi

    monkeypatch.setattr(roi, "extract_multi_patch_traces_from_video", fake_extract)
    manifest = {
        "dataset_name": "fixture",
        "sessions": [
            {
                "session_id": "s1",
                "video_path": "video.avi",
                "patch_names": ["forehead", "left_cheek", "right_cheek"],
            }
        ],
    }
    out = tmp_path / "out"
    sessions = normalize_dataset_manifest(_write_manifest(tmp_path, manifest), out)
    for patch in ("forehead", "left_cheek", "right_cheek"):
        assert (out / "s1" / f"trace_{patch}.csv").exists()
    assert (out / "s1" / "trace.csv").exists()
    assert sessions[0]["patch_names"] == ["forehead", "left_cheek", "right_cheek"]
