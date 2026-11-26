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


def test_pos_receives_raw_rgb_and_sample_rate(monkeypatch):
    """PR #1's windowed POS signature: (rgb, sample_rate_hz=UPSAMPLE_TARGET_FS, window_s=...)."""
    from app.services import rppg_processor
    from learning.phase1 import baselines

    seen = {}
    original = rppg_processor._extract_pos_waveform

    def windowed_pos(rgb, sample_rate_hz=rppg_processor.UPSAMPLE_TARGET_FS, window_s=1.6):
        seen["mean_green"] = float(rgb[:, 1].mean())
        seen["sample_rate_hz"] = sample_rate_hz
        return original(rgb)

    monkeypatch.setattr(rppg_processor, "_extract_pos_waveform", windowed_pos)
    frames = generate_synthetic_frames(
        SyntheticScenarioConfig(hr_bpm=72.0, fps=20.0, noise_std=0.1)
    )
    report = compare_methods(frames)
    assert seen["mean_green"] > 50.0  # raw RGB, not a zero-mean detrended trace
    assert seen["sample_rate_hz"] == rppg_processor.UPSAMPLE_TARGET_FS  # 20 FPS upsampled to 30
    assert abs(report["pos"].hr_bpm - 72.0) <= 6.0

    frames_30 = generate_synthetic_frames(SyntheticScenarioConfig(hr_bpm=72.0, fps=25.0))
    compare_methods(frames_30)
    assert seen["sample_rate_hz"] == rppg_processor.UPSAMPLE_TARGET_FS

    del baselines


def test_pos_still_works_with_the_legacy_rgb_only_signature(monkeypatch):
    from app.services import rppg_processor
    from learning.phase1.baselines import pos_waveform

    calls = []

    def legacy(rgb):
        calls.append(rgb.shape)
        return rgb[:, 1] - rgb[:, 1].mean()

    monkeypatch.setattr(rppg_processor, "_extract_pos_waveform", legacy)
    import numpy as np

    rgb = np.column_stack([np.full(90, 90.0), 100.0 + np.sin(np.arange(90)), np.full(90, 80.0)])
    out = pos_waveform(rgb, 30.0)
    assert calls == [(90, 3)]
    assert out.shape == (90,)
    assert abs(float(out.mean())) < 1e-9  # detrended after extraction
