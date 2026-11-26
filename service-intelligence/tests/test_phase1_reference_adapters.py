import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from learning.phase1.reference_adapters import (
    VALIDATOR_STRIDE_S,
    VALIDATOR_WINDOW_S,
    beats_to_reference_rows,
    detect_beats,
    load_pure_json,
    load_ubfc_ground_truth,
    load_waveform_csv,
    reference_window_summary,
    waveform_to_reference_rows,
    write_reference_csv,
)

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_accuracy", SERVICE_ROOT / "scripts" / "validate_accuracy.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


def _beat_times(hr_bpm: float, duration_s: float, rmssd_ms: float = 0.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    mean_ibi = 60.0 / hr_bpm
    times = [0.3]
    # Alternating IBI perturbation gives a known RMSSD of about 2 * jitter.
    jitter = rmssd_ms / 2000.0
    sign = 1.0
    while times[-1] < duration_s - 0.3:
        times.append(times[-1] + mean_ibi + sign * jitter + rng.normal(0, 1e-4))
        sign = -sign
    return np.array(times[:-1])


def _ppg_from_beats(beats: np.ndarray, fs: float, duration_s: float):
    t = np.arange(0.0, duration_s, 1.0 / fs)
    x = np.zeros_like(t)
    for b in beats:
        x += np.exp(-0.5 * ((t - b) / 0.08) ** 2) + 0.3 * np.exp(-0.5 * ((t - b - 0.3) / 0.1) ** 2)
    return t, x


def _ecg_from_beats(beats: np.ndarray, fs: float, duration_s: float):
    t = np.arange(0.0, duration_s, 1.0 / fs)
    x = 0.05 * np.sin(2 * np.pi * 0.3 * t)
    for b in beats:
        x += np.exp(-0.5 * ((t - b) / 0.01) ** 2)
    return t, x


@pytest.mark.parametrize("hr", [55.0, 72.0, 110.0])
def test_ppg_waveform_recovers_hr(hr):
    beats = _beat_times(hr, 30.0)
    t, x = _ppg_from_beats(beats, 60.0, 30.0)
    rows = waveform_to_reference_rows(t, x, "ppg_waveform")
    hrs = np.array([r["hr_bpm"] for r in rows])
    # Band-pass edge effects shift the first and last beat by a few ms; interior rows
    # must be near exact, edge rows within a couple of BPM.
    assert np.all(np.abs(hrs[1:-1] - hr) < 0.5)
    assert np.all(np.abs(hrs[[0, -1]] - hr) < 2.5)


def test_ecg_rmssd_is_recovered():
    beats = _beat_times(65.0, 40.0, rmssd_ms=40.0)
    t, x = _ecg_from_beats(beats, 250.0, 40.0)
    detected = detect_beats(t, x, "ecg_waveform")
    assert detected.beat_times_s.size == beats.size
    rows = beats_to_reference_rows(detected, origin_s=0.0, end_s=40.0)
    rmssd = [r["hrv_rmssd_ms"] for r in rows if r["hrv_rmssd_ms"] is not None]
    assert abs(np.median(rmssd) - 40.0) < 4.0


def test_inverted_ecg_is_handled():
    beats = _beat_times(80.0, 20.0)
    t, x = _ecg_from_beats(beats, 250.0, 20.0)
    detected = detect_beats(t, -x, "ecg_waveform")
    assert abs(detected.beat_times_s.size - beats.size) <= 1


def test_low_rate_ppg_uses_subsample_peaks():
    beats = _beat_times(70.0, 30.0, rmssd_ms=30.0)
    t, x = _ppg_from_beats(beats, 30.0, 30.0)  # MMPD-like 30 Hz reference
    detected = detect_beats(t, x, "ppg_waveform")
    matched = [np.min(np.abs(detected.beat_times_s - b)) for b in beats[1:-1]]
    assert np.median(matched) < 0.012  # better than the 33 ms sample spacing


def test_rows_start_at_origin_on_a_uniform_grid():
    beats = _beat_times(72.0, 30.0)
    t, x = _ppg_from_beats(beats, 60.0, 30.0)
    rows = waveform_to_reference_rows(t, x, "ppg_waveform", grid_s=1.0)
    stamps = np.array([r["timestamp_ms"] for r in rows])
    assert stamps[0] == pytest.approx(t[0] * 1000.0)
    assert np.allclose(np.diff(stamps), 1000.0)


def test_validator_window_average_matches_exact_window_hr():
    # HR ramps from 60 to 90 BPM, so misaligned windows would show up as error.
    times = [0.2]
    while times[-1] < 39.5:
        hr = 60.0 + 30.0 * times[-1] / 40.0
        times.append(times[-1] + 60.0 / hr)
    beats = np.array(times[:-1])
    t, x = _ppg_from_beats(beats, 100.0, 40.0)
    detected = detect_beats(t, x, "ppg_waveform")
    rows = beats_to_reference_rows(detected, origin_s=0.0, end_s=40.0, grid_s=0.5)
    exact = reference_window_summary(detected, origin_s=0.0, end_s=40.0)
    assert len(exact) == int((40.0 - VALIDATOR_WINDOW_S) // VALIDATOR_STRIDE_S) + 1
    for window in exact:
        inside = [r["hr_bpm"] for r in rows if window.start_ms <= r["timestamp_ms"] < window.end_ms]
        assert abs(np.mean(inside) - window.hr_bpm) < 1.0


def test_irregular_and_unsorted_samples_are_tolerated():
    beats = _beat_times(75.0, 30.0)
    t, x = _ppg_from_beats(beats, 64.0, 30.0)
    rng = np.random.default_rng(1)
    t_jittered = t + rng.normal(0, 0.002, t.size)
    order = rng.permutation(t.size)
    rows = waveform_to_reference_rows(t_jittered[order], x[order], "ppg_waveform")
    assert abs(np.median([r["hr_bpm"] for r in rows]) - 75.0) < 1.5


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        detect_beats([0, 1, 2], [0, 1, 0], "ppg_waveform")
    with pytest.raises(ValueError):
        detect_beats(np.arange(100), np.zeros(100), "hr_series")
    with pytest.raises(ValueError):
        detect_beats(np.arange(100) / 4.0, np.zeros(100), "ecg_waveform")  # 4 Hz is too low


def test_reference_csv_is_read_by_the_validator(tmp_path: Path):
    beats = _beat_times(68.0, 30.0, rmssd_ms=25.0)
    t, x = _ppg_from_beats(beats, 60.0, 30.0)
    path = tmp_path / "reference.csv"
    write_reference_csv(path, waveform_to_reference_rows(t, x, "ppg_waveform"))
    validator = _load_validator()
    gold = validator.load_ecg_gold(path)
    assert len(gold) == 30
    assert gold[0]["timestamp_ms"] == 0.0
    assert abs(np.median([row["hr_bpm"] for row in gold]) - 68.0) < 1.0
    assert gold[5]["hrv_rmssd_ms"] is not None


def test_dataset_format_loaders(tmp_path: Path):
    ubfc = tmp_path / "ground_truth.txt"
    ubfc.write_text("0.1 0.5 0.2\n70 71 72\n0.0 0.033 0.066\n", encoding="utf-8")
    t, x = load_ubfc_ground_truth(ubfc)
    assert t.tolist() == [0.0, 0.033, 0.066]
    assert x.tolist() == [0.1, 0.5, 0.2]

    pure = tmp_path / "pure.json"
    pure.write_text(
        json.dumps(
            {
                "/FullPackage": [
                    {"Timestamp": 1_000_000_000, "Value": {"waveform": 10}},
                    {"Timestamp": 1_016_666_667, "Value": {"waveform": 12}},
                ]
            }
        ),
        encoding="utf-8",
    )
    t, x = load_pure_json(pure)
    assert t[0] == pytest.approx(1.0)
    assert x.tolist() == [10.0, 12.0]

    csv_path = tmp_path / "wave.csv"
    csv_path.write_text("t_ms,ppg\n0,1\n10,2\n", encoding="utf-8")
    t, x = load_waveform_csv(csv_path, "t_ms", "ppg")
    assert t.tolist() == [0.0, 0.01]
