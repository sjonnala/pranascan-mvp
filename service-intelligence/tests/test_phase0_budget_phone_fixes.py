"""
Adversarial tests for the Phase 0 budget-phone reliability fixes.

Covers the failure modes diagnosed in the Cycle-1 low-caliber phone audit:

- pure "no pulse" noise must abstain (hr_bpm=None) in >= 95% of trials
- auto-exposure (AE) step shifts and auto-white-balance (AWB) drift
- Fitzpatrick V-VI HR invariance (no skin-tone HR scaling)
- JS-stall duplicate millisecond timestamps
- HRV withholding when the effective delivered frame rate is below 25 FPS
- scan evaluation: no max(mobile, spectral) merge, abstention respected,
  anemia heuristic not run on face-centre pixels

Synthetic traces use relative pulsatile amplitudes following the de Haan &
Jeanne (2013) blood-volume signature, so they behave like skin reflectance
rather than like the large absolute sine waves in the older fixtures.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.schemas.scan import FrameSampleSchema, ScanResultSubmit, ScanType
from app.services import rppg_processor as rp
from app.services.rppg_processor import FrameSample, process_frames
from app.services.scan_evaluation_service import evaluate_scan_submission
from app.services.skin_tone import FitzpatrickType, apply_skin_tone_calibration
from app.services.vitals_extraction import ExtractedVitals

# Relative pulsatile strength per channel (R, G, B), de Haan & Jeanne 2013 PBV.
_PBV = np.array([0.33, 0.77, 0.53])
_PBV = _PBV / np.linalg.norm(_PBV)

# Representative skin DC colours (sRGB 0-255) for Fitzpatrick groups.
_SKIN_DC = {
    "II": np.array([200.0, 160.0, 135.0]),
    "III": np.array([180.0, 135.0, 105.0]),
    "V": np.array([120.0, 80.0, 55.0]),
    "VI": np.array([70.0, 45.0, 32.0]),
}


def _timeline(fps: float, duration_s: float, rng: np.random.Generator, jitter_ms: float = 0.0):
    count = int(round(fps * duration_s))
    t = np.arange(count) / fps
    if jitter_ms > 0:
        t = t + rng.normal(0.0, jitter_ms / 1000.0, count)
        t = np.sort(t)
    return t


def _pulse_waveform(t: np.ndarray, hr_bpm: float, rng: np.random.Generator) -> np.ndarray:
    """Pulse with mild heart-rate variability and a second harmonic."""
    inst_hr_hz = hr_bpm / 60.0 + 0.03 * np.sin(2.0 * math.pi * 0.1 * t + rng.uniform(0, 6.28))
    phase = 2.0 * math.pi * np.cumsum(np.r_[0.0, np.diff(t)] * inst_hr_hz)
    return np.sin(phase) + 0.3 * np.sin(2.0 * phase + 0.6)


def _make_trace(
    *,
    hr_bpm: float | None = 72.0,
    fps: float = 30.0,
    duration_s: float = 30.0,
    dc: np.ndarray | None = None,
    ac_fraction: float = 0.006,
    noise_fraction: float = 0.002,
    seed: int = 0,
    jitter_ms: float = 0.0,
    ae_steps: int = 0,
    ae_step_fraction: float = 0.08,
    awb_drift_fraction: float = 0.0,
    drop_fraction: float = 0.0,
) -> list[FrameSample]:
    """Relative-amplitude skin trace: C(t) = DC * gain(t) * (1 + ac * pulse * PBV + noise)."""
    rng = np.random.default_rng(seed)
    dc = _SKIN_DC["III"] if dc is None else dc
    t = _timeline(fps, duration_s, rng, jitter_ms)
    n = t.size

    relative = np.zeros((n, 3))
    if hr_bpm is not None:
        relative += ac_fraction * _pulse_waveform(t, hr_bpm, rng)[:, None] * _PBV[None, :]
    relative += rng.normal(0.0, noise_fraction, (n, 3))

    gain = np.ones((n, 3))
    if ae_steps:
        step_times = np.sort(rng.uniform(0.15 * duration_s, 0.85 * duration_s, ae_steps))
        for step_time in step_times:
            sign = rng.choice([-1.0, 1.0])
            gain[t >= step_time, :] *= 1.0 + sign * ae_step_fraction
    if awb_drift_fraction:
        ramp = t / duration_s
        gain[:, 0] *= 1.0 + awb_drift_fraction * ramp
        gain[:, 2] *= 1.0 - awb_drift_fraction * ramp

    rgb = np.clip(dc[None, :] * gain * (1.0 + relative), 0.0, 255.0)

    keep = np.ones(n, dtype=bool)
    if drop_fraction:
        keep[1:-1] = rng.random(n - 2) >= drop_fraction

    return [
        FrameSample(
            t_ms=float(t[i] * 1000.0),
            r_mean=float(rgb[i, 0]),
            g_mean=float(rgb[i, 1]),
            b_mean=float(rgb[i, 2]),
        )
        for i in range(n)
        if keep[i]
    ]


def _make_no_pulse_trace(seed: int, fps: float) -> list[FrameSample]:
    """Pure noise: sensor noise, slow illumination wander and random AE steps, no pulse."""
    rng = np.random.default_rng(10_000 + seed)
    noise_fraction = float(rng.uniform(0.001, 0.01))
    trace = _make_trace(
        hr_bpm=None,
        fps=fps,
        noise_fraction=noise_fraction,
        seed=10_000 + seed,
        ae_steps=int(rng.integers(0, 3)),
        ae_step_fraction=float(rng.uniform(0.02, 0.08)),
        awb_drift_fraction=float(rng.uniform(0.0, 0.04)),
        dc=_SKIN_DC[rng.choice(list(_SKIN_DC))],
    )
    # Slow random-walk illumination wander (non-periodic).
    walk = np.cumsum(rng.normal(0.0, 0.0008, len(trace)))
    return [
        FrameSample(
            t_ms=frame.t_ms,
            r_mean=frame.r_mean * (1.0 + walk[i]),
            g_mean=frame.g_mean * (1.0 + walk[i]),
            b_mean=frame.b_mean * (1.0 + walk[i]),
        )
        for i, frame in enumerate(trace)
    ]


def _to_ms_stamps(frames: list[FrameSample]) -> list[FrameSample]:
    return [
        FrameSample(t_ms=float(round(f.t_ms)), r_mean=f.r_mean, g_mean=f.g_mean, b_mean=f.b_mean)
        for f in frames
    ]


def _inject_js_stalls(
    frames: list[FrameSample], stall_prob: float, burst: int, seed: int
) -> tuple[list[FrameSample], int]:
    """Simulate JS-thread stalls: queued samples drain back-to-back with one ms stamp."""
    rng = np.random.default_rng(seed)
    out = list(frames)
    corrupted = 0
    i = 1
    while i < len(out) - burst - 1:
        if rng.random() < stall_prob:
            drain_ms = out[i + burst - 1].t_ms
            for j in range(burst):
                out[i + j] = FrameSample(
                    t_ms=drain_ms,
                    r_mean=out[i + j].r_mean,
                    g_mean=out[i + j].g_mean,
                    b_mean=out[i + j].b_mean,
                )
            corrupted += burst - 1
            i += burst + 1
        else:
            i += 1
    return out, corrupted


# ---------------------------------------------------------------------------
# 1. "No pulse" abstention
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fps", [30.0, 15.0])
def test_pure_noise_abstains_in_at_least_95_percent_of_trials(fps):
    trials = 120
    abstained = 0
    for seed in range(trials):
        result = process_frames(_make_no_pulse_trace(seed, fps))
        if result.hr_bpm is None:
            abstained += 1
        if result.abstained:
            assert result.hr_bpm is None
            assert result.hrv_ms is None
            assert result.respiratory_rate is None
            assert "hr_abstained" in result.flags
            assert "no_reliable_pulse" in result.flags
            assert any(flag.startswith("abstain_reason:") for flag in result.flags)
            assert result.abstention_reason in {"low_spectral_quality", "low_spectral_snr"}
    assert abstained / trials >= 0.95, f"abstained {abstained}/{trials} at {fps} FPS"


@pytest.mark.parametrize("fps", [30.0, 15.0])
def test_real_pulse_is_answered_not_abstained(fps):
    """Coverage guard: the abstention threshold must not swallow ordinary scans."""
    trials = 60
    answered = 0
    errors = []
    for seed in range(trials):
        hr = 55.0 + (seed * 7) % 55
        result = process_frames(_make_trace(hr_bpm=hr, fps=fps, seed=seed, jitter_ms=3.0))
        if result.hr_bpm is not None:
            answered += 1
            errors.append(abs(result.hr_bpm - hr))
    assert answered / trials >= 0.95
    assert float(np.mean(errors)) <= 3.0


def test_abstention_threshold_is_configurable():
    frames = _make_trace(hr_bpm=72.0, seed=3)
    assert process_frames(frames).hr_bpm is not None
    strict = process_frames(frames, min_snr_db=60.0)
    assert strict.hr_bpm is None
    assert strict.abstained is True
    assert "abstain_reason:low_spectral_snr" in strict.flags


# ---------------------------------------------------------------------------
# 2. AE / AWB step shifts — windowed POS
# ---------------------------------------------------------------------------


def test_ae_steps_and_awb_drift_hr_within_tolerance():
    trials = 40
    errors = []
    for seed in range(trials):
        hr = 58.0 + (seed * 11) % 50
        frames = _make_trace(
            hr_bpm=hr,
            seed=500 + seed,
            ae_steps=3,
            ae_step_fraction=0.08,
            awb_drift_fraction=0.04,
        )
        result = process_frames(frames)
        if result.hr_bpm is not None:
            errors.append(abs(result.hr_bpm - hr))
    assert len(errors) >= 0.9 * trials
    within_5 = np.mean(np.array(errors) <= 5.0)
    assert within_5 >= 0.9, f"within 5 BPM: {within_5:.2f}"


def test_windowed_pos_beats_global_normalisation_under_ae_steps():
    """A 1.6 s window must not do worse than one window spanning the whole scan."""
    windowed, global_ = [], []
    for seed in range(30):
        hr = 60.0 + (seed * 13) % 45
        frames = _make_trace(
            hr_bpm=hr, seed=900 + seed, ae_steps=3, ae_step_fraction=0.1, awb_drift_fraction=0.04
        )
        w = process_frames(frames, min_snr_db=-math.inf, min_spectral_quality=0.0)
        g = process_frames(
            frames, pos_window_s=60.0, min_snr_db=-math.inf, min_spectral_quality=0.0
        )
        windowed.append(abs(w.hr_bpm - hr) if w.hr_bpm is not None else 60.0)
        global_.append(abs(g.hr_bpm - hr) if g.hr_bpm is not None else 60.0)
    assert float(np.mean(windowed)) <= float(np.mean(global_))
    assert float(np.mean(windowed)) <= 3.0


def test_pos_window_is_configurable_and_validated():
    frames = _make_trace(hr_bpm=80.0, seed=7)
    for window_s in (1.0, 1.6, 3.2):
        result = process_frames(frames, pos_window_s=window_s)
        assert result.hr_bpm is not None
        assert abs(result.hr_bpm - 80.0) <= 5.0
    with pytest.raises(ValueError):
        rp.extract_bvp(frames, pos_window_s=0.0)


def test_windowed_pos_is_invariant_to_constant_channel_gain():
    """Per-window temporal normalisation removes any constant per-channel gain."""
    rgb = np.random.default_rng(1).uniform(90.0, 110.0, (300, 3))
    base = rp._extract_pos_waveform(rgb, 30.0)
    scaled = rp._extract_pos_waveform(rgb * np.array([1.7, 0.6, 1.2]), 30.0)
    np.testing.assert_allclose(base, scaled, rtol=1e-9, atol=1e-12)


# ---------------------------------------------------------------------------
# 3. Fitzpatrick V-VI HR invariance
# ---------------------------------------------------------------------------


def test_identical_pulse_gives_identical_hr_across_skin_tones():
    """Same relative pulse on Type II and Type V/VI skin must give the same HR.

    Before Phase 0 the skin-tone module multiplied Type 5/6 HR by 0.97/0.95.
    """
    hrs = {}
    types = {}
    for group in ("II", "V", "VI"):
        frames = _make_trace(hr_bpm=76.0, seed=42, dc=_SKIN_DC[group])
        result, skin = apply_skin_tone_calibration(process_frames(frames), frames)
        hrs[group] = (result.hr_bpm, result.hrv_ms, result.quality_score)
        types[group] = skin.fitzpatrick_type
    assert hrs["II"][0] is not None
    assert hrs["II"] == hrs["V"] == hrs["VI"]
    assert types["VI"] in (FitzpatrickType.TYPE_5, FitzpatrickType.TYPE_6)
    assert types["II"].value <= 3


@pytest.mark.parametrize("ftype", list(FitzpatrickType))
def test_skin_tone_metadata_never_changes_values(ftype):
    from app.services.rppg_processor import RppgResult

    colours = {
        FitzpatrickType.TYPE_1: (255, 220, 195),
        FitzpatrickType.TYPE_2: (240, 200, 170),
        FitzpatrickType.TYPE_3: (210, 170, 135),
        FitzpatrickType.TYPE_4: (175, 130, 95),
        FitzpatrickType.TYPE_5: (120, 80, 55),
        FitzpatrickType.TYPE_6: (65, 40, 28),
    }
    frames = [FrameSample(i * 33.3, *colours[ftype]) for i in range(30)]
    base = RppgResult(81.3, 37.25, 15.0, 0.42, ["x"], snr_db=4.2, effective_fps=29.9)
    out, _ = apply_skin_tone_calibration(base, frames)
    assert (out.hr_bpm, out.hrv_ms, out.respiratory_rate, out.quality_score) == (
        81.3,
        37.25,
        15.0,
        0.42,
    )
    assert out.snr_db == 4.2
    assert out.effective_fps == 29.9


def test_dark_skin_low_amplitude_hr_unbiased():
    """Type V-VI (AC x0.45) must not be biased low: mean signed error near zero."""
    signed = []
    for seed in range(40):
        hr = 60.0 + (seed * 9) % 45
        frames = _make_trace(hr_bpm=hr, seed=300 + seed, dc=_SKIN_DC["VI"], ac_fraction=0.0027)
        result, _ = apply_skin_tone_calibration(process_frames(frames), frames)
        if result.hr_bpm is not None:
            signed.append(result.hr_bpm - hr)
    assert len(signed) >= 36
    assert abs(float(np.mean(signed))) <= 1.5


# ---------------------------------------------------------------------------
# 4. JS-stall duplicate timestamps
# ---------------------------------------------------------------------------


def test_js_stall_duplicate_ms_stamps_are_repaired_not_rejected():
    successes = 0
    trials = 30
    for seed in range(trials):
        hr = 62.0 + (seed * 5) % 40
        frames = _to_ms_stamps(_make_trace(hr_bpm=hr, seed=700 + seed, jitter_ms=4.0))
        stalled, corrupted = _inject_js_stalls(frames, stall_prob=0.01, burst=3, seed=seed)
        assert corrupted <= 0.05 * len(frames)
        result = process_frames(stalled)
        assert "irregular_timestamps" not in result.flags
        if corrupted:
            assert "duplicate_timestamps_repaired" in result.flags
        if result.hr_bpm is not None and abs(result.hr_bpm - hr) <= 5.0:
            successes += 1
    assert successes >= 0.9 * trials


def test_isolated_out_of_order_stamp_is_dropped():
    frames = _to_ms_stamps(_make_trace(hr_bpm=70.0, seed=11))
    frames[200] = FrameSample(
        t_ms=frames[150].t_ms,
        r_mean=frames[200].r_mean,
        g_mean=frames[200].g_mean,
        b_mean=frames[200].b_mean,
    )
    result = process_frames(frames)
    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 70.0) <= 5.0
    assert "duplicate_timestamps_repaired" in result.flags


def test_more_than_5_percent_corrupted_frames_is_rejected():
    frames = _to_ms_stamps(_make_trace(hr_bpm=70.0, seed=12))
    stalled, corrupted = _inject_js_stalls(frames, stall_prob=0.06, burst=4, seed=1)
    assert corrupted > 0.05 * len(frames)
    result = process_frames(stalled)
    assert result.hr_bpm is None
    assert "irregular_timestamps" in result.flags


def test_repair_keeps_timestamps_strictly_increasing():
    t = np.array([0.0, 0.033, 0.066, 0.120, 0.120, 0.120, 0.133, 0.166, 0.166])
    rgb = np.ones((t.size, 3))
    repaired, _, corrupted = rp._repair_timestamps(t, rgb)
    assert corrupted == 3
    assert np.all(np.diff(repaired) > 0)
    assert repaired[0] == 0.0 and repaired[6] == pytest.approx(0.133)


# ---------------------------------------------------------------------------
# 5. Low-FPS HRV withholding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fps", [12.0, 15.0, 20.0, 24.0])
def test_hrv_withheld_below_25_fps(fps):
    result = process_frames(_make_trace(hr_bpm=70.0, fps=fps, seed=21))
    assert result.hr_bpm is not None
    assert result.hrv_ms is None
    assert "hrv_withheld_low_fps" in result.flags
    assert result.effective_fps is not None and result.effective_fps < 25.0


def test_hrv_reported_at_30_fps():
    result = process_frames(_make_trace(hr_bpm=70.0, fps=30.0, seed=21))
    assert result.hr_bpm is not None
    assert result.hrv_ms is not None
    assert "hrv_withheld_low_fps" not in result.flags


def test_hrv_withheld_when_drops_lower_effective_fps():
    """30 FPS nominal with 25% dropped frames: median interval still says 30 FPS."""
    result = process_frames(_make_trace(hr_bpm=70.0, fps=30.0, seed=22, drop_fraction=0.25))
    assert result.effective_fps is not None and result.effective_fps < 25.0
    assert result.hrv_ms is None
    assert "hrv_withheld_low_fps" in result.flags


# ---------------------------------------------------------------------------
# 6. Scan evaluation: quality scores, abstention, anemia guard
# ---------------------------------------------------------------------------


def _submission(frames: list[FrameSample], **overrides) -> ScanResultSubmit:
    payload = {
        "scan_type": ScanType.STANDARD,
        "frame_data": [
            FrameSampleSchema(t_ms=f.t_ms, r_mean=f.r_mean, g_mean=f.g_mean, b_mean=f.b_mean)
            for f in frames
        ],
        "hr_bpm": 72.0,
        "hrv_ms": 48.0,
        "respiratory_rate": 14.0,
        "quality_score": 0.95,
        "lighting_score": 0.85,
        "motion_score": 0.99,
        "face_confidence": 0.9,
        "frame_r_mean": 180.0,
        "frame_g_mean": 135.0,
        "frame_b_mean": 105.0,
    }
    payload.update(overrides)
    return ScanResultSubmit(**payload)


def test_low_spectral_quality_is_not_hidden_by_mobile_quality():
    evaluation = evaluate_scan_submission(_submission(_make_no_pulse_trace(3, 30.0)))
    assert evaluation.mobile_quality_score == 0.95
    assert evaluation.spectral_quality_score is not None
    assert evaluation.submission.quality_score == evaluation.spectral_quality_score
    assert evaluation.submission.quality_score < 0.95
    assert "mobile_quality_score:0.9500" in evaluation.flags
    assert any(flag.startswith("spectral_quality_score:") for flag in evaluation.flags)
    assert any(flag.startswith("spectral_snr_db:") for flag in evaluation.flags)


def test_abstention_clears_client_hr_instead_of_passing_it_through():
    evaluation = evaluate_scan_submission(_submission(_make_no_pulse_trace(5, 30.0)))
    assert evaluation.hr_abstained is True
    assert evaluation.hr_abstention_reason in {"low_spectral_quality", "low_spectral_snr"}
    assert evaluation.submission.hr_bpm is None
    assert evaluation.submission.hrv_ms is None
    assert evaluation.submission.respiratory_rate is None
    assert evaluation.vascular_age_estimate is None
    assert "hr_abstained" in evaluation.flags


def test_good_scan_reports_spectral_quality_and_server_hr():
    evaluation = evaluate_scan_submission(_submission(_make_trace(hr_bpm=84.0, seed=4)))
    assert evaluation.hr_abstained is False
    assert evaluation.submission.hr_bpm is not None
    assert abs(evaluation.submission.hr_bpm - 84.0) <= 5.0
    assert evaluation.submission.quality_score == evaluation.spectral_quality_score
    assert evaluation.mobile_quality_score == 0.95


def test_low_fps_scan_does_not_keep_client_hrv():
    evaluation = evaluate_scan_submission(_submission(_make_trace(hr_bpm=70.0, fps=15.0, seed=8)))
    assert evaluation.submission.hr_bpm is not None
    assert evaluation.submission.hrv_ms is None
    assert "hrv_withheld_low_fps" in evaluation.flags


def test_standard_face_scan_does_not_run_anemia_on_face_pixels():
    evaluation = evaluate_scan_submission(_submission(_make_trace(hr_bpm=70.0, seed=9)))
    assert evaluation.hb_proxy_score is None
    assert evaluation.anemia_wellness_label is None
    assert evaluation.anemia_confidence is None
    assert evaluation.anemia_applicable is False
    assert evaluation.anemia_not_applicable_reason == "no_conjunctival_roi"
    assert "anemia_not_applicable" in evaluation.flags
    assert "anemia_not_applicable_reason:no_conjunctival_roi" in evaluation.flags


def test_anemia_runs_only_with_explicit_conjunctival_roi():
    evaluation = evaluate_scan_submission(
        _submission(
            _make_trace(hr_bpm=70.0, seed=9),
            conjunctival_r_mean=180.0,
            conjunctival_g_mean=120.0,
            conjunctival_b_mean=100.0,
        )
    )
    assert evaluation.anemia_applicable is True
    assert evaluation.hb_proxy_score is not None
    assert evaluation.anemia_not_applicable_reason is None
    assert "anemia_not_applicable" not in evaluation.flags


def test_partial_conjunctival_roi_is_not_applicable():
    evaluation = evaluate_scan_submission(
        _submission(_make_trace(hr_bpm=70.0, seed=9), conjunctival_r_mean=180.0)
    )
    assert evaluation.anemia_applicable is False
    assert evaluation.hb_proxy_score is None


def test_deep_dive_scan_skips_anemia_entirely():
    evaluation = evaluate_scan_submission(
        _submission(_make_trace(hr_bpm=70.0, seed=9), scan_type=ScanType.DEEP_DIVE)
    )
    assert evaluation.hb_proxy_score is None
    assert evaluation.anemia_not_applicable_reason is None


# ---------------------------------------------------------------------------
# 7. Follow-up: POS sample-rate default, flat / no-peak traces as abstentions
# ---------------------------------------------------------------------------


def test_pos_waveform_sample_rate_defaults_to_upsample_target():
    frames = _make_trace(hr_bpm=72.0, seed=21)
    rgb = np.array([[f.r_mean, f.g_mean, f.b_mean] for f in frames])
    default = rp._extract_pos_waveform(rgb)
    explicit = rp._extract_pos_waveform(rgb, rp.UPSAMPLE_TARGET_FS)
    assert np.allclose(default, explicit)
    # The window can still be passed by keyword without a sample rate.
    assert np.allclose(
        rp._extract_pos_waveform(rgb, window_s=1.6),
        rp._extract_pos_waveform(rgb, rp.UPSAMPLE_TARGET_FS, 1.6),
    )


def _flat_frames(count: int = 300, fps: float = 30.0) -> list[FrameSample]:
    return [
        FrameSample(t_ms=index * 1000.0 / fps, r_mean=150.0, g_mean=120.0, b_mean=95.0)
        for index in range(count)
    ]


_CLIENT_VITALS = ExtractedVitals(heart_rate=88.0, hrv=55.0, spo2=97.0)


def _assert_signal_failure_abstention(evaluation, reason: str) -> None:
    assert evaluation.hr_abstained is True
    assert evaluation.hr_abstention_reason == reason
    assert evaluation.submission.hr_bpm is None
    assert evaluation.submission.hrv_ms is None
    assert evaluation.submission.respiratory_rate is None
    assert evaluation.vascular_age_estimate is None
    assert "hr_abstained" in evaluation.flags
    assert f"abstain_reason:{reason}" in evaluation.flags


def test_flat_signal_scan_abstains_and_blocks_extracted_vitals_backfill():
    evaluation = evaluate_scan_submission(_submission(_flat_frames()), _CLIENT_VITALS)
    assert "flat_signal" in evaluation.flags
    _assert_signal_failure_abstention(evaluation, "flat_signal")
    # SpO2 is not an rPPG output and is still passed through.
    assert evaluation.spo2 == 97.0


def test_flat_signal_deep_dive_scan_never_leaks_client_hr():
    evaluation = evaluate_scan_submission(
        _submission(_flat_frames(count=900), scan_type=ScanType.DEEP_DIVE), _CLIENT_VITALS
    )
    assert "flat_signal" in evaluation.flags
    _assert_signal_failure_abstention(evaluation, "flat_signal")


@pytest.mark.parametrize("snr_db", [None, 4.0], ids=["before_spectral", "after_spectral"])
def test_insufficient_peaks_scan_abstains_and_blocks_extracted_vitals_backfill(monkeypatch, snr_db):
    from app.services import scan_evaluation_service as ses

    no_peaks = rp.RppgResult(
        hr_bpm=None,
        hrv_ms=None,
        respiratory_rate=None,
        quality_score=0.42,
        flags=["insufficient_peaks"],
        snr_db=snr_db,
        effective_fps=30.0,
    )
    monkeypatch.setattr(ses, "process_frames", lambda frames: no_peaks)

    evaluation = evaluate_scan_submission(
        _submission(_make_trace(hr_bpm=70.0, seed=22)), _CLIENT_VITALS
    )
    _assert_signal_failure_abstention(evaluation, "insufficient_peaks")
    if snr_db is None:
        # No spectral analysis: the mobile score stands, as before.
        assert evaluation.submission.quality_score == 0.95
    else:
        assert evaluation.submission.quality_score == 0.42


def test_insufficient_peaks_deep_dive_scan_never_leaks_client_hr(monkeypatch):
    from app.services import scan_evaluation_service as ses
    from app.services.morphology_processor import MorphologyResult

    no_peaks = MorphologyResult(
        hr_bpm=None,
        hrv_ms=None,
        stiffness_index=None,
        quality_score=0.3,
        flags=["insufficient_peaks"],
    )
    monkeypatch.setattr(ses, "process_morphology_frames", lambda frames, height: no_peaks)

    evaluation = evaluate_scan_submission(
        _submission(_make_trace(hr_bpm=70.0, seed=23), scan_type=ScanType.DEEP_DIVE),
        _CLIENT_VITALS,
    )
    _assert_signal_failure_abstention(evaluation, "insufficient_peaks")


def test_scan_without_frame_data_keeps_client_vitals():
    evaluation = evaluate_scan_submission(_submission([], frame_data=None), _CLIENT_VITALS)
    assert evaluation.hr_abstained is False
    assert evaluation.submission.hr_bpm == 72.0
    assert evaluation.submission.hrv_ms == 48.0
