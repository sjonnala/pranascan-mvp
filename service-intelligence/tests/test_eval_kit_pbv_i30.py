"""Tests for the I30 port (moved from the Cycle-1 winning_dsp_pipeline.py embedded tests)."""

import numpy as np

from learning.eval_kit.pbv_i30 import (
    FEATURES,
    FS_GRID_HZ,
    confidence,
    estimate_hr,
    fit_confidence,
    pulse_signal,
    repair_exposure_steps,
    resample_uniform,
)


def _synthetic(hr_bpm=72.0, fps=30.0, dur=30.0, pulse=True, seed=0, step_at=None, step=0.08):
    rng = np.random.default_rng(seed)
    t = np.arange(0, dur, 1.0 / fps)
    dc = np.array([176.0, 126.0, 101.0])
    ph = 2 * np.pi * hr_bpm / 60.0 * t
    wave = np.sin(ph) + 0.35 * np.sin(2 * ph + 0.6)
    ac = 0.004 * np.array([0.33, 0.77, 0.53]) / 0.77 * pulse
    common = 0.0015 * rng.standard_normal((t.size, 1))
    rgb = dc[None, :] * (1 + ac[None, :] * wave[:, None] + common)
    rgb += 0.12 * rng.standard_normal(rgb.shape)
    if step_at is not None:
        rgb[t >= step_at] *= 1 + step
    return t, rgb


def test_clean_pulse_is_accurate_and_accepted():
    for hr in (58.0, 75.0, 104.0):
        r = estimate_hr(*_synthetic(hr, seed=int(hr)))
        assert r.accepted, (hr, r.confidence)
        assert abs(r.hr_bpm - hr) < 1.5


def test_low_fps_jittered_pulse():
    t, rgb = _synthetic(66.0, fps=15.0, seed=3)
    t = np.sort(t + np.random.default_rng(1).normal(0, 0.003, t.size))
    r = estimate_hr(t, rgb)
    assert r.raw_hr_bpm is not None and abs(r.raw_hr_bpm - 66.0) < 2.0


def test_no_pulse_abstains():
    abstained = sum(not estimate_hr(*_synthetic(pulse=False, seed=s)).accepted for s in range(20))
    assert abstained >= 19


def test_flat_input_abstains():
    t = np.arange(0, 30, 1 / 30)
    r = estimate_hr(t, np.full((t.size, 3), 120.0))
    assert r.hr_bpm is None and r.raw_hr_bpm is None


def test_bad_input_abstains_without_raising():
    t = np.arange(0, 30, 1 / 30)
    assert estimate_hr(t[:10], np.ones((10, 3))).hr_bpm is None
    assert estimate_hr(t, np.ones((t.size, 2))).hr_bpm is None
    bad = np.ones((t.size, 3)) * 100
    bad[5, 1] = np.nan
    assert estimate_hr(t, bad).hr_bpm is None
    assert estimate_hr(t[::-1], np.ones((t.size, 3))).hr_bpm is None


def test_exposure_step_is_repaired():
    t, rgb = _synthetic(80.0, seed=7, step_at=12.3, step=0.08)
    _, x = resample_uniform(t, rgb)
    _, n = repair_exposure_steps(x, FS_GRID_HZ)
    assert n == 1
    r = estimate_hr(t, rgb)
    assert r.n_exposure_steps == 1 and r.accepted and abs(r.hr_bpm - 80.0) < 1.5


def test_no_false_steps_on_clean_signal():
    t, rgb = _synthetic(70.0, seed=11)
    _, x = resample_uniform(t, rgb)
    assert repair_exposure_steps(x, FS_GRID_HZ)[1] == 0


def test_output_contract_and_determinism():
    t, rgb = _synthetic(90.0, seed=5)
    a, b = estimate_hr(t, rgb), estimate_hr(t, rgb)
    assert (a.hr_bpm, a.confidence) == (b.hr_bpm, b.confidence)
    assert a.hr_bpm is None or isinstance(a.hr_bpm, float)
    assert 0.0 <= a.confidence <= 1.0
    assert set(a.features) == set(FEATURES)


def test_pulse_signal_is_30hz_and_none_for_flat_input():
    t, rgb = _synthetic(72.0, seed=2)
    bvp, fs = pulse_signal(t, rgb)
    assert fs == 30.0 and bvp.ndim == 1 and bvp.size > 600
    flat_t = np.arange(0, 30, 1 / 30)
    assert pulse_signal(flat_t, np.full((flat_t.size, 3), 120.0)) is None


def test_fit_confidence_recovers_separable_threshold():
    rng = np.random.default_rng(0)
    good = [
        {
            "pmr_db": 25 + rng.normal(),
            "prom_db": 15 + rng.normal(),
            "entropy": 0.7,
            "win_agree": 1.0,
            "win_mad": 0.5,
        }
        for _ in range(60)
    ]
    bad = [
        {
            "pmr_db": 8 + rng.normal(),
            "prom_db": 1 + rng.normal(),
            "entropy": 0.95,
            "win_agree": 0.2,
            "win_mad": 20.0,
        }
        for _ in range(60)
    ]
    mu, sd, w, tau = fit_confidence(
        good + bad, [1] * 60 + [0] * 60, is_nopulse=np.r_[np.zeros(60), np.ones(60)] > 0
    )
    cg = [confidence(d, mu, sd, w) for d in good]
    cb = [confidence(d, mu, sd, w) for d in bad]
    assert min(cg) > max(cb) and np.mean(np.array(cb) < tau) >= 0.985
