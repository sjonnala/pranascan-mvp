"""
PranaScan background agent runner.

Finds all active users (consented + enough recent scans), generates their
weekly vitality report, and fires trend alerts where deviation thresholds
are exceeded.

Designed to be called:
  - From the internal HTTP endpoint POST /internal/agent/run
  - Directly via CLI: agent/pranascan_agent.py
  - By an OpenClaw cron job (weekly schedule)

Privacy: operates on pseudonymous user_ids only. No PII is processed or logged.
Delivery: report summaries and alerts are forwarded to delivery_service which
routes to Telegram (if configured) or structured log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.consent import ConsentAction, ConsentRecord
from app.models.scan import ScanResult
from app.models.vitality_report import VitalityReport
from app.services.delivery_service import deliver_alert, deliver_report
from app.services.vitality_report import generate_report

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class UserRunResult:
    user_id: str
    report_generated: bool = False
    alert_sent: bool = False
    error: str | None = None


@dataclass
class AgentRunSummary:
    run_at: datetime
    users_found: int
    reports_generated: int
    alerts_sent: int
    errors: list[str] = field(default_factory=list)
    results: list[UserRunResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Active user discovery
# ---------------------------------------------------------------------------


async def get_active_user_ids(db: AsyncSession) -> list[str]:
    """
    Return pseudonymous user IDs eligible for agent processing.

    Criteria:
      1. At least ``settings.trend_min_baseline_scans`` completed scan results
         within the last ``settings.trend_lookback_days`` days.
      2. Most recent consent action is ``ConsentAction.GRANTED`` (not revoked or
         deletion-requested).
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.trend_lookback_days)

    # Step 1: users with enough recent scan results
    scan_stmt = (
        select(ScanResult.user_id)
        .where(ScanResult.created_at >= cutoff)
        .group_by(ScanResult.user_id)
        .having(func.count(ScanResult.id) >= settings.trend_min_baseline_scans)
    )
    scan_result = await db.execute(scan_stmt)
    candidate_ids: list[str] = [row[0] for row in scan_result.all()]

    if not candidate_ids:
        return []

    # Step 2: filter to those whose latest consent action is GRANTED
    active_ids: list[str] = []
    for user_id in candidate_ids:
        consent_stmt = (
            select(ConsentRecord.action)
            .where(ConsentRecord.user_id == user_id)
            .order_by(ConsentRecord.created_at.desc())
            .limit(1)
        )
        consent_result = await db.execute(consent_stmt)
        latest_action = consent_result.scalar_one_or_none()
        if latest_action == ConsentAction.GRANTED:
            active_ids.append(user_id)

    log.info(
        "agent_active_users_found",
        extra={"candidate_count": len(candidate_ids), "active_count": len(active_ids)},
    )
    return active_ids


# ---------------------------------------------------------------------------
# Per-user processing
# ---------------------------------------------------------------------------


async def _process_user(db: AsyncSession, user_id: str) -> UserRunResult:
    """
    Generate a weekly vitality report and fire any pending trend alerts for
    one user. Errors are caught and returned — they must not halt the cycle.
    """
    try:
        report_data = await generate_report(db, user_id)

        hr_metric = next((m for m in report_data.metrics if m.name == "Heart Rate"), None)
        hrv_metric = next((m for m in report_data.metrics if m.name == "HRV (RMSSD)"), None)

        report = VitalityReport(
            user_id=user_id,
            period_start=report_data.period_start,
            period_end=report_data.period_end,
            scan_count=report_data.scan_count,
            alert_count=report_data.alert_count,
            avg_hr_bpm=hr_metric.current_avg if hr_metric else None,
            avg_hrv_ms=hrv_metric.current_avg if hrv_metric else None,
            avg_respiratory_rate=next(
                (m.current_avg for m in report_data.metrics if m.name == "Respiratory Rate"),
                None,
            ),
            avg_voice_jitter_pct=next(
                (m.current_avg for m in report_data.metrics if m.name == "Voice Jitter"), None
            ),
            avg_voice_shimmer_pct=next(
                (m.current_avg for m in report_data.metrics if m.name == "Voice Shimmer"), None
            ),
            delta_hr_bpm=hr_metric.delta if hr_metric else None,
            delta_hrv_ms=hrv_metric.delta if hrv_metric else None,
            latest_vascular_age_estimate=report_data.latest_vascular_age,
            latest_vascular_age_confidence=report_data.latest_vascular_age_confidence,
            latest_anemia_label=report_data.latest_anemia_label,
            latest_anemia_confidence=report_data.latest_anemia_confidence,
            summary_text=report_data.summary_text,
            generated_at=report_data.generated_at,
        )
        db.add(report)
        await db.flush()

        await deliver_report(user_id, report_data.summary_text)

        alert_sent = False
        if report_data.alert_count > 0:
            await deliver_alert(user_id, "agent_weekly_trend_alert")
            alert_sent = True

        log.info(
            "agent_user_processed",
            extra={
                "user_id": user_id,
                "scan_count": report_data.scan_count,
                "alert_sent": alert_sent,
            },
        )
        return UserRunResult(
            user_id=user_id, report_generated=True, alert_sent=alert_sent, error=None
        )

    except Exception as exc:  # noqa: BLE001
        log.error(
            "agent_user_processing_failed",
            extra={"user_id": user_id, "error": str(exc)},
        )
        return UserRunResult(
            user_id=user_id, report_generated=False, alert_sent=False, error=str(exc)
        )


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------


async def run_agent_cycle(db: AsyncSession) -> AgentRunSummary:
    """
    Run one full agent cycle.

    Discovers active users, generates a weekly vitality report for each,
    delivers via configured channels, and fires trend alerts where applicable.

    Returns an ``AgentRunSummary`` with per-user results and aggregate counts.
    """
    run_at = datetime.now(tz=timezone.utc)
    log.info("agent_cycle_started", extra={"run_at": run_at.isoformat()})

    user_ids = await get_active_user_ids(db)

    results: list[UserRunResult] = []
    for user_id in user_ids:
        result = await _process_user(db, user_id)
        results.append(result)

    summary = AgentRunSummary(
        run_at=run_at,
        users_found=len(user_ids),
        reports_generated=sum(1 for r in results if r.report_generated),
        alerts_sent=sum(1 for r in results if r.alert_sent),
        errors=[r.error for r in results if r.error is not None],
        results=results,
    )

    log.info(
        "agent_cycle_complete",
        extra={
            "users_found": summary.users_found,
            "reports_generated": summary.reports_generated,
            "alerts_sent": summary.alerts_sent,
            "error_count": len(summary.errors),
        },
    )
    return summary
