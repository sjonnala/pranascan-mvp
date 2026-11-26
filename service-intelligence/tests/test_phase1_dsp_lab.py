from pathlib import Path

from learning.phase1.common import SyntheticScenarioConfig, generate_synthetic_frames
from learning.phase1.dsp_lab import run_pipeline_stages, write_pipeline_artifacts


def test_pipeline_lab_recovers_known_heart_rates():
    for hr_bpm, tolerance in [(60.0, 5.0), (80.0, 5.0), (100.0, 7.0)]:
        frames = generate_synthetic_frames(
            SyntheticScenarioConfig(
                hr_bpm=hr_bpm,
                noise_std=0.16,
            )
        )
        artifacts = run_pipeline_stages(frames)
        assert artifacts.hr_bpm is not None
        assert abs(artifacts.hr_bpm - hr_bpm) <= tolerance


def test_pipeline_lab_flags_low_frame_rate():
    frames = generate_synthetic_frames(
        SyntheticScenarioConfig(hr_bpm=55.0, fps=20.0, noise_std=0.08)
    )
    artifacts = run_pipeline_stages(frames)
    assert "low_framerate_upsampled" in artifacts.flags
    assert artifacts.hr_bpm is not None


def test_pipeline_artifacts_are_written(tmp_path: Path):
    frames = generate_synthetic_frames(SyntheticScenarioConfig())
    artifacts = run_pipeline_stages(frames)
    write_pipeline_artifacts(tmp_path, "default", frames, artifacts)
    assert (tmp_path / "frames.csv").exists()
    assert (tmp_path / "stages.csv").exists()
    assert (tmp_path / "summary.json").exists()
