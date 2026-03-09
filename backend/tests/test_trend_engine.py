"""Unit tests for the backend multi-metric trend engine."""

from datetime import datetime, timezone

from sqlalchemy import Select

from app.services.trend_engine import (
    TrendBaseline,
    baselines_from_row,
    build_cooldown_check_query,
    compute_metric_deviation_pct,
    compute_trend_alert,
)


def test_baselines_from_row_maps_metric_averages_and_counts():
    baselines = baselines_from_row((72.0, 3, 45.0, 4, 16.0, 5, 0.5, 3, 2.0, 6))

    assert baselines["hr_bpm"] == TrendBaseline(average=72.0, sample_count=3)
    assert baselines["voice_shimmer_pct"] == TrendBaseline(average=2.0, sample_count=6)


def test_compute_metric_deviation_pct_uses_absolute_percent():
    deviation = compute_metric_deviation_pct(
        82.8,
        TrendBaseline(average=72.0, sample_count=3),
        min_baseline_scans=3,
    )

    assert deviation == 15.0


def test_compute_trend_alert_requires_mature_baseline():
    trend_alert = compute_trend_alert(
        {"hr_bpm": 82.8},
        {"hr_bpm": TrendBaseline(average=72.0, sample_count=2)},
        threshold_pct=15.0,
        min_baseline_scans=3,
    )

    assert trend_alert is None


def test_compute_trend_alert_fires_for_non_hr_metric():
    trend_alert = compute_trend_alert(
        {
            "hr_bpm": 72.0,
            "hrv_ms": 38.0,
            "respiratory_rate": 16.0,
            "voice_jitter_pct": 0.5,
            "voice_shimmer_pct": 2.0,
        },
        {
            "hr_bpm": TrendBaseline(average=72.0, sample_count=3),
            "hrv_ms": TrendBaseline(average=45.0, sample_count=3),
            "respiratory_rate": TrendBaseline(average=16.0, sample_count=3),
            "voice_jitter_pct": TrendBaseline(average=0.5, sample_count=3),
            "voice_shimmer_pct": TrendBaseline(average=2.0, sample_count=3),
        },
        threshold_pct=15.0,
        min_baseline_scans=3,
    )

    assert trend_alert == "consider_lab_followup"


def test_build_cooldown_check_query_returns_selectable():
    """build_cooldown_check_query returns a SQLAlchemy Select object."""
    cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = build_cooldown_check_query("user1", cutoff)
    assert result is not None
    assert isinstance(result, Select)
