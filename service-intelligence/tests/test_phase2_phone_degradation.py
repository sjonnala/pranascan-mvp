import math

import numpy as np
import pytest

from app.services.rppg_processor import FrameSample
from learning.phase1.common import SyntheticScenarioConfig, generate_synthetic_frames
from learning.phase2_fastai.phone_degradation import (
    PRESETS,
    DegradationConfig,
    alias_frequency_hz,
    degrade_patch_traces,
    degrade_trace,
    frames_to_arrays,
    get_preset,
)

# A config with every nuisance switched off, so one effect can be tested at a time.
QUIET = DegradationConfig(
    fps_range=(30.0, 30.0),
    fps_wander=0.0,
    jitter_ms=0.0,
    drop_prob=0.0,
    drop_burst_prob=0.0,
    bit_depth=16,
    roi_pixel_samples=256,
    pixel_dither_std=0.0,
    shot_noise_coeff=0.0,
    read_noise_std=0.0,
    ae_step_count=(0, 0),
)


def _clean(hr=72.0, duration_s=30.0, scale=1.0, seed=3):
    return generate_synthetic_frames(
        SyntheticScenarioConfig(
            hr_bpm=hr,
            fps=60.0,
            duration_s=duration_s,
            noise_std=0.0,
            illumination_amplitude=0.0,
            signal_scale=scale,
            seed=seed,
        )
    )


def _flat(level=(120.0, 110.0, 90.0), duration_s=30.0, fps=60.0):
    n = int(duration_s * fps)
    return [FrameSample(i * 1000.0 / fps, *level) for i in range(n)]


def _spectrum(frames, grid_fs=30.0):
    t, rgb = frames_to_arrays(frames)
    grid = np.arange(t[0], t[-1], 1.0 / grid_fs)
    g = np.interp(grid, t, rgb[:, 1])
    g = (g - g.mean()) * np.hanning(g.size)
    power = np.abs(np.fft.rfft(g)) ** 2
    freqs = np.fft.rfftfreq(g.size, 1.0 / grid_fs)
    return freqs, power


def _band_amplitude(frames, low=0.7, high=4.0):
    freqs, power = _spectrum(frames)
    band = (freqs >= low) & (freqs <= high)
    return float(np.sqrt(power[band].max()))


def test_same_seed_gives_identical_output_and_other_seeds_differ():
    clean = _clean()
    a = degrade_trace(clean, "budget_worst_case", seed=11)
    b = degrade_trace(clean, "budget_worst_case", seed=11)
    c = degrade_trace(clean, "budget_worst_case", seed=12)
    assert a.frames == b.frames
    assert a.events == b.events
    assert a.frames != c.frames


@pytest.mark.parametrize("seed", range(5))
def test_budget_frame_rate_stays_in_the_12_to_20_fps_band(seed):
    out = degrade_trace(_clean(), "budget_bright", seed=seed)
    assert 12.0 <= out.base_fps <= 20.0
    assert 10.5 <= out.delivered_fps <= 20.5  # drops lower the delivered rate a little
    stamps = np.array([f.t_ms for f in out.frames])
    assert np.all(np.diff(stamps) > 0)
    assert np.allclose(stamps, np.round(stamps))  # whole milliseconds like a phone clock
    gaps = np.diff(stamps)
    assert gaps.std() > 1.0  # jitter and wander, not a perfect clock


def test_drop_fraction_matches_the_configured_rate():
    cfg = replace_cfg(QUIET, fps_range=(15.0, 15.0), drop_prob=0.10)
    out = degrade_trace(_clean(duration_s=120.0), cfg, seed=4)
    fraction = out.dropped_count / out.nominal_frame_count
    assert 0.07 <= fraction <= 0.13
    assert len(out.frames) == out.nominal_frame_count - out.dropped_count


def replace_cfg(cfg, **changes):
    from dataclasses import replace

    return replace(cfg, **changes)


def test_alias_frequency_of_india_mains_flicker():
    assert alias_frequency_hz(100.0, 17.0) == pytest.approx(2.0)
    assert alias_frequency_hz(100.0, 14.0) == pytest.approx(2.0)
    assert alias_frequency_hz(100.0, 20.0) == pytest.approx(0.0)
    assert alias_frequency_hz(100.0, 30.0) == pytest.approx(10.0)


@pytest.mark.parametrize("fps", [14.0, 17.0])
def test_tube_light_flicker_aliases_to_120_bpm_on_a_pulseless_face(fps):
    cfg = replace_cfg(QUIET, fps_range=(fps, fps), flicker_depth=(0.1, 0.1), exposure_ms=(2.0, 2.0))
    out = degrade_trace(_flat(), cfg, seed=1)
    freqs, power = _spectrum(out.frames)
    band = (freqs >= 0.7) & (freqs <= 4.0)
    peak_hz = float(freqs[band][np.argmax(power[band])])
    assert peak_hz == pytest.approx(2.0, abs=0.07)
    assert any(e.kind == "flicker" for e in out.events)


def test_exposure_of_one_mains_period_cancels_flicker():
    def amplitude(exposure_ms):
        cfg = replace_cfg(
            QUIET,
            fps_range=(17.0, 17.0),
            flicker_depth=(0.1, 0.1),
            exposure_ms=(exposure_ms, exposure_ms),
        )
        return _band_amplitude(degrade_trace(_flat(), cfg, seed=1).frames)

    assert amplitude(10.0) < 0.02 * amplitude(2.0)


def test_eight_bit_readout_quantises_a_single_pixel_roi():
    cfg = replace_cfg(QUIET, bit_depth=8, roi_pixel_samples=1)
    out = degrade_trace(_clean(), cfg, seed=2)
    values = np.array([[f.r_mean, f.g_mean, f.b_mean] for f in out.frames])
    assert np.allclose(values, np.round(values))
    assert values.min() >= 0 and values.max() <= 255


def test_averaging_dithered_pixels_recovers_sub_lsb_pulse():
    def amplitude(pixels, dither):
        cfg = replace_cfg(QUIET, bit_depth=8, roi_pixel_samples=pixels, pixel_dither_std=dither)
        return _band_amplitude(degrade_trace(_clean(scale=0.3), cfg, seed=5).frames)

    reference = _band_amplitude(degrade_trace(_clean(scale=0.3), QUIET, seed=5).frames)
    assert abs(amplitude(64, 0.8) - reference) / reference < 0.25


def test_darker_skin_attenuates_the_pulse_not_the_baseline():
    clean = _clean()
    light = degrade_trace(clean, QUIET, seed=6)
    dark = degrade_trace(
        clean, replace_cfg(QUIET, skin_ac_attenuation=0.45, skin_dc_scale=1.0), seed=6
    )
    ratio = _band_amplitude(dark.frames) / _band_amplitude(light.frames)
    assert ratio == pytest.approx(0.45, abs=0.05)
    mean_light = np.mean([f.g_mean for f in light.frames])
    mean_dark = np.mean([f.g_mean for f in dark.frames])
    assert mean_dark == pytest.approx(mean_light, rel=0.01)


def test_dim_light_lowers_the_level_and_ae_only_partly_compensates():
    clean = _clean()
    bright = degrade_trace(clean, QUIET, seed=7)
    dim = degrade_trace(clean, replace_cfg(QUIET, light_scale=(0.4, 0.4)), seed=7)
    level = np.mean([f.g_mean for f in dim.frames]) / np.mean([f.g_mean for f in bright.frames])
    assert level == pytest.approx(0.4**0.5, rel=0.02)  # ae_compensation = 0.5


def test_ae_steps_are_reported_as_exposure_events():
    cfg = replace_cfg(QUIET, ae_step_count=(2, 2), ae_step_magnitude=(0.1, 0.1))
    out = degrade_trace(_clean(), cfg, seed=8)
    steps = [e for e in out.events if e.kind == "exposure_event"]
    assert len(steps) == 2
    assert all(abs(e.magnitude) == pytest.approx(0.1) for e in steps)
    g = np.array([f.g_mean for f in out.frames])
    t = np.array([f.t_ms for f in out.frames])
    before = g[t < steps[0].start_ms - 500].mean()
    after = g[(t > steps[0].end_ms + 300) & (t < (steps[1].start_ms if len(steps) > 1 else 1e12))]
    assert after.size and abs(after.mean() / before - 1.0) > 0.05


def test_motion_bursts_are_labelled_and_add_energy():
    cfg = replace_cfg(QUIET, motion_burst_count=(3, 3), motion_amplitude=8.0)
    out = degrade_trace(_clean(), cfg, seed=9)
    bursts = [e for e in out.events if e.kind == "motion"]
    assert len(bursts) == 3
    g = np.array([f.g_mean for f in out.frames])
    t = np.array([f.t_ms for f in out.frames])
    clean_out = degrade_trace(_clean(), QUIET, seed=9)
    g_clean = np.interp(t, [f.t_ms for f in clean_out.frames], [f.g_mean for f in clean_out.frames])
    inside = np.zeros(t.size, dtype=bool)
    for e in bursts:
        inside |= (t >= e.start_ms) & (t <= e.end_ms)
    assert np.abs(g - g_clean)[inside].mean() > 5 * np.abs(g - g_clean)[~inside].mean() + 1e-9
    assert out.events_overlapping(bursts[0].start_ms, bursts[0].end_ms)


def test_patches_share_timing_but_get_independent_noise():
    clean = _clean()
    out = degrade_patch_traces({"forehead": clean, "cheek": clean}, "budget_bright", seed=10)
    forehead, cheek = out.patch_frames["forehead"], out.patch_frames["cheek"]
    assert [f.t_ms for f in forehead] == [f.t_ms for f in cheek]
    assert any(a.g_mean != b.g_mean for a, b in zip(forehead, cheek, strict=False))


def test_presets_and_config_validation():
    assert set(PRESETS) >= {
        "flagship_reference",
        "budget_india_indoor",
        "budget_dim_darker_skin",
        "budget_tubelight_flicker",
        "budget_motion",
        "budget_worst_case",
    }
    assert get_preset("budget_bright", drop_prob=0.2).drop_prob == 0.2
    with pytest.raises(ValueError):
        get_preset("does_not_exist")
    with pytest.raises(ValueError):
        DegradationConfig(fps_range=(20.0, 12.0))
    with pytest.raises(ValueError):
        DegradationConfig(drop_prob=1.0)
    with pytest.raises(ValueError):
        DegradationConfig(bit_depth=0)
    with pytest.raises(ValueError):
        degrade_patch_traces({}, QUIET)


def test_flagship_preset_keeps_the_pulse_recoverable():
    from app.services.rppg_processor import process_frames

    out = degrade_trace(_clean(hr=78.0), "flagship_reference", seed=13)
    result = process_frames(out.frames)
    assert result.hr_bpm is not None
    assert math.isclose(result.hr_bpm, 78.0, abs_tol=5.0)
