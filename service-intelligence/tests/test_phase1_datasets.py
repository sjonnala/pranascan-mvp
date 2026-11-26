import json
from pathlib import Path

from learning.phase1.datasets import normalize_dataset_manifest


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
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    output_dir = tmp_path / "normalized"
    sessions = normalize_dataset_manifest(manifest_path, output_dir)

    assert len(sessions) == 1
    assert (output_dir / "subject_001" / "trace.csv").exists()
    assert (output_dir / "subject_001" / "summary.json").exists()
    commands = (output_dir / "validation_commands.txt").read_text(encoding="utf-8")
    assert "scripts/validate_accuracy.py" in commands
