"""Tests for the contact-PPG morphology processor."""

from __future__ import annotations

import math

from app.services.morphology_processor import process_morphology_frames
from app.services.rppg_processor import FrameSample


def _synthetic_contact_frames(
    sample_rate_hz: int = 60,
    duration_s: int = 30,
    heart_rate_bpm: float = 66.0,
) -> list[FrameSample]:
    frames: list[FrameSample] = []
    beat_period_s = 60.0 / heart_rate_bpm

    for index in range(sample_rate_hz * duration_s):
        t_s = index / sample_rate_hz
        phase = (t_s % beat_period_s) / beat_period_s

        systolic = math.exp(-0.5 * ((phase - 0.16) / 0.05) ** 2)
        reflected = 0.42 * math.exp(-0.5 * ((phase - 0.43) / 0.07) ** 2)
        diastolic = 0.18 * math.exp(-0.5 * ((phase - 0.72) / 0.09) ** 2)
        baseline = 185.0 + 22.0 * systolic + 10.0 * reflected + 4.0 * diastolic

        frames.append(
            FrameSample(
                t_ms=t_s * 1000.0,
                r_mean=baseline,
                g_mean=baseline,
                b_mean=baseline,
            )
        )

    return frames


def test_morphology_processor_returns_hr_hrv_and_stiffness_index():
    result = process_morphology_frames(_synthetic_contact_frames(), user_height_cm=172.0)

    assert result.hr_bpm is not None
    assert abs(result.hr_bpm - 66.0) <= 5.0
    assert result.hrv_ms is not None
    assert result.stiffness_index is not None
    assert result.stiffness_index > 0.0


def test_morphology_processor_reports_missing_height():
    result = process_morphology_frames(_synthetic_contact_frames(), user_height_cm=None)

    assert result.hr_bpm is not None
    assert result.stiffness_index is None
    assert "height_required_for_stiffness_index" in result.flags


def test_morphology_processor_rejects_flat_signal():
    frames = [
        FrameSample(t_ms=index * (1000.0 / 60.0), r_mean=200.0, g_mean=200.0, b_mean=200.0)
        for index in range(60 * 30)
    ]

    result = process_morphology_frames(frames, user_height_cm=172.0)

    assert result.hr_bpm is None
    assert result.stiffness_index is None
    assert result.flags == ["flat_signal"]
