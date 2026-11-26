from pathlib import Path

from learning.phase1.baselines import compare_methods, write_baseline_report
from learning.phase1.common import SyntheticScenarioConfig, generate_synthetic_frames


def test_baseline_report_covers_all_methods():
    frames = generate_synthetic_frames(SyntheticScenarioConfig(hr_bpm=72.0, noise_std=0.12))
    report = compare_methods(frames)
    assert set(report) == {"green", "ica", "chrom", "pos"}


def test_pos_and_chrom_recover_synthetic_trace():
    frames = generate_synthetic_frames(SyntheticScenarioConfig(hr_bpm=72.0, noise_std=0.1))
    report = compare_methods(frames)
    assert report["pos"].hr_bpm is not None
    assert report["chrom"].hr_bpm is not None
    assert abs(report["pos"].hr_bpm - 72.0) <= 6.0
    assert abs(report["chrom"].hr_bpm - 72.0) <= 8.0


def test_baseline_report_is_written(tmp_path: Path):
    frames = generate_synthetic_frames(SyntheticScenarioConfig(hr_bpm=80.0, noise_std=0.14))
    report = compare_methods(frames)
    write_baseline_report(tmp_path, report)
    assert (tmp_path / "baseline_comparison.csv").exists()
    assert (tmp_path / "baseline_comparison.json").exists()
