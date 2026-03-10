"""
Weekly Vitality Report generator.

Aggregates the past 7 days of scan results for a user and produces a
structured wellness summary with week-over-week comparison.

Output is a wellness summary only — not a medical report or diagnosis.
Always include the disclaimer in all rendered text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import ScanResult, ScanSession, SessionStatus

DISCLAIMER = (
    "This is a wellness summary, not a medical report. "
    "For health concerns, consult a qualified healthcare provider."
)

METRICS = [
    ("hr_bpm", "Heart Rate", "bpm"),
    ("hrv_ms", "HRV (RMSSD)", "ms"),
    ("respiratory_rate", "Respiratory Rate", "breaths/min"),
    ("voice_jitter_pct", "Voice Jitter", "%"),
    ("voice_shimmer_pct", "Voice Shimmer", "%"),
]


@dataclass
class MetricSummary:
    name: str
    unit: str
    current_avg: float | None
    prior_avg: float | None
    delta: float | None  # current - prior (None if either missing)
    scan_count: int


@dataclass
class VitalityReportData:
    user_id: str
    period_start: datetime
    period_end: datetime
    scan_count: int
    metrics: list[MetricSummary]
    alert_count: int  # number of trend alerts fired in the period
    latest_vascular_age: float | None
    latest_vascular_age_confidence: float | None
    latest_anemia_label: str | None
    latest_anemia_confidence: float | None
    summary_text: str  # human-readable plain text
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


async def generate_report(db: AsyncSession, user_id: str) -> VitalityReportData:
    """
    Generate a weekly vitality report for a user.

    Queries the past 7 days (current window) and the 7 days before that
    (prior window) to produce week-over-week deltas.
    """
    now = datetime.now(tz=timezone.utc)
    current_start = now - timedelta(days=7)
    prior_start = now - timedelta(days=14)

    # Fetch current-week scan results
    current_results = await _fetch_results(db, user_id, current_start, now)
    prior_results = await _fetch_results(db, user_id, prior_start, current_start)

    scan_count = len(current_results)
    alert_count = sum(1 for r in current_results if r.trend_alert is not None)

    # Metric summaries
    metric_summaries: list[MetricSummary] = []
    for field_name, label, unit in METRICS:
        curr_vals = [
            getattr(r, field_name) for r in current_results if getattr(r, field_name) is not None
        ]
        prior_vals = [
            getattr(r, field_name) for r in prior_results if getattr(r, field_name) is not None
        ]
        curr_avg = round(sum(curr_vals) / len(curr_vals), 1) if curr_vals else None
        prior_avg = round(sum(prior_vals) / len(prior_vals), 1) if prior_vals else None
        delta = (
            round(curr_avg - prior_avg, 1)
            if curr_avg is not None and prior_avg is not None
            else None
        )
        metric_summaries.append(
            MetricSummary(
                name=label,
                unit=unit,
                current_avg=curr_avg,
                prior_avg=prior_avg,
                delta=delta,
                scan_count=len(curr_vals),
            )
        )

    # Latest vascular age + anemia from the current window (most recent scan)
    latest = current_results[-1] if current_results else None
    latest_vascular_age = getattr(latest, "vascular_age_estimate", None) if latest else None
    latest_vascular_age_conf = getattr(latest, "vascular_age_confidence", None) if latest else None
    latest_anemia_label = getattr(latest, "anemia_wellness_label", None) if latest else None
    latest_anemia_conf = getattr(latest, "anemia_confidence", None) if latest else None

    summary_text = _render_text(
        user_id=user_id,
        period_start=current_start,
        period_end=now,
        scan_count=scan_count,
        metrics=metric_summaries,
        alert_count=alert_count,
        vascular_age=latest_vascular_age,
        anemia_label=latest_anemia_label,
    )

    return VitalityReportData(
        user_id=user_id,
        period_start=current_start,
        period_end=now,
        scan_count=scan_count,
        metrics=metric_summaries,
        alert_count=alert_count,
        latest_vascular_age=latest_vascular_age,
        latest_vascular_age_confidence=latest_vascular_age_conf,
        latest_anemia_label=latest_anemia_label,
        latest_anemia_confidence=latest_anemia_conf,
        summary_text=summary_text,
    )


async def _fetch_results(
    db: AsyncSession, user_id: str, start: datetime, end: datetime
) -> list[ScanResult]:
    """Fetch completed scan results for a user within [start, end)."""
    stmt = (
        select(ScanResult)
        .join(ScanSession, ScanSession.id == ScanResult.session_id)
        .where(
            ScanResult.user_id == user_id,
            ScanResult.created_at >= start,
            ScanResult.created_at < end,
            ScanSession.status == SessionStatus.COMPLETED,
        )
        .order_by(ScanResult.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _render_text(
    *,
    user_id: str,
    period_start: datetime,
    period_end: datetime,
    scan_count: int,
    metrics: list[MetricSummary],
    alert_count: int,
    vascular_age: float | None,
    anemia_label: str | None,
) -> str:
    """Render a plain-text wellness summary."""
    lines = [
        "PranaScan Weekly Wellness Summary",
        "=" * 36,
        f"Period : {period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}",
        f"Scans  : {scan_count}",
        "",
        "── Wellness Indicators ──────────────",
    ]

    for m in metrics:
        if m.current_avg is None:
            lines.append(f"  {m.name:<22} insufficient data")
            continue
        delta_str = ""
        if m.delta is not None:
            arrow = "↑" if m.delta > 0 else ("↓" if m.delta < 0 else "→")
            delta_str = f"  {arrow}{abs(m.delta):.1f} vs prior week"
        lines.append(f"  {m.name:<22} {m.current_avg:.1f} {m.unit}{delta_str}")

    lines.append("")
    lines.append("── Supplementary Indicators ─────────")

    if vascular_age is not None:
        lines.append(f"  Vascular Age Estimate  {int(vascular_age)} years (wellness indicator)")
    else:
        lines.append("  Vascular Age Estimate  insufficient data")

    if anemia_label is not None:
        label_display = anemia_label.replace("_", " ").title()
        lines.append(f"  Hemoglobin Proxy       {label_display}")
    else:
        lines.append("  Hemoglobin Proxy       insufficient data")

    lines.append("")
    if alert_count > 0:
        lines.append(f"── Wellness Alerts ({alert_count}) ────────────────")
        lines.append("  → Consider scheduling a routine check-up based on recent trends.")
        lines.append("")

    lines.append(DISCLAIMER)
    return "\n".join(lines)
