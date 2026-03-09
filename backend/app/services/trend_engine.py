"""Helpers for multi-metric baseline and deviation trend alerts."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select

from app.models.scan import ScanResult

TREND_METRICS = (
    ("hr_bpm", ScanResult.hr_bpm),
    ("hrv_ms", ScanResult.hrv_ms),
    ("respiratory_rate", ScanResult.respiratory_rate),
    ("voice_jitter_pct", ScanResult.voice_jitter_pct),
    ("voice_shimmer_pct", ScanResult.voice_shimmer_pct),
)


@dataclass(frozen=True)
class TrendBaseline:
    average: float | None
    sample_count: int


def build_trend_baseline_query(
    user_id: str,
    cutoff: datetime,
    *,
    before: datetime | None = None,
):
    """Aggregate prior metric averages and counts for a user's rolling baseline."""
    columns = []
    for _, metric_column in TREND_METRICS:
        columns.extend((func.avg(metric_column), func.count(metric_column)))

    stmt = select(*columns).where(
        ScanResult.user_id == user_id,
        ScanResult.created_at >= cutoff,
    )
    if before is not None:
        stmt = stmt.where(ScanResult.created_at < before)
    return stmt


def baselines_from_row(row: tuple[object, ...]) -> dict[str, TrendBaseline]:
    """Convert a SQL aggregate row into named per-metric baselines."""
    baselines: dict[str, TrendBaseline] = {}
    for index, (metric_name, _) in enumerate(TREND_METRICS):
        avg_value = row[index * 2]
        sample_count = int(row[index * 2 + 1] or 0)
        baselines[metric_name] = TrendBaseline(
            average=float(avg_value) if avg_value is not None else None,
            sample_count=sample_count,
        )
    return baselines


def compute_metric_deviation_pct(
    current_value: float | None,
    baseline: TrendBaseline,
    *,
    min_baseline_scans: int,
) -> float | None:
    """
    Compute absolute percent deviation from baseline for one metric.

    Returns None when the current value is absent, the baseline is not mature
    enough, or the baseline average is zero.
    """
    if (
        current_value is None
        or baseline.average is None
        or baseline.average == 0
        or baseline.sample_count < min_baseline_scans
    ):
        return None

    deviation = abs((current_value - baseline.average) / baseline.average) * 100
    return round(deviation, 2)


def build_cooldown_check_query(user_id: str, cutoff: datetime) -> Select:
    """
    Return a SELECT that checks whether any trend alert was fired for this user
    since `cutoff`. Returns the most recent trend_alert value (or None).
    """
    return (
        select(ScanResult.trend_alert)
        .where(
            ScanResult.user_id == user_id,
            ScanResult.created_at >= cutoff,
            ScanResult.trend_alert.isnot(None),
        )
        .order_by(ScanResult.created_at.desc())
        .limit(1)
    )


def compute_trend_alert(
    current_metrics: Mapping[str, float | None],
    baselines: Mapping[str, TrendBaseline],
    *,
    threshold_pct: float,
    min_baseline_scans: int,
) -> str | None:
    """
    Raise a wellness trend alert when any mature metric deviates by threshold_pct.

    Returns only "consider_lab_followup" or None to preserve non-diagnostic copy.
    """
    for metric_name, _ in TREND_METRICS:
        deviation_pct = compute_metric_deviation_pct(
            current_metrics.get(metric_name),
            baselines.get(metric_name, TrendBaseline(average=None, sample_count=0)),
            min_baseline_scans=min_baseline_scans,
        )
        if deviation_pct is not None and deviation_pct >= threshold_pct:
            return "consider_lab_followup"

    return None
