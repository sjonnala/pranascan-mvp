"""Vitality Report API router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_auth
from app.models.vitality_report import VitalityReport
from app.schemas.vitality_report import VitalityReportResponse
from app.services.delivery_service import deliver_alert
from app.services.vitality_report import generate_report

router = APIRouter(prefix="/reports", tags=["Vitality Reports"])


@router.post(
    "/generate",
    response_model=VitalityReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_vitality_report(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> VitalityReportResponse:
    """
    Generate a weekly vitality report for the authenticated user.

    Aggregates the past 7 days of scan results, computes week-over-week
    deltas, renders a plain-text summary, and stores the report.

    Output is a wellness summary only — not a medical report.
    """
    report_data = await generate_report(db, user_id)

    # Find the metric objects for storage
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
    await db.refresh(report)

    # Deliver via webhook stub if alerts were present in the period
    if report_data.alert_count > 0:
        await deliver_alert(user_id, "weekly_vitality_report_with_alerts")

    return VitalityReportResponse.model_validate(report)


@router.get(
    "/latest",
    response_model=VitalityReportResponse,
    status_code=status.HTTP_200_OK,
)
async def get_latest_report(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> VitalityReportResponse:
    """Fetch the most recently generated vitality report for the authenticated user."""
    stmt = (
        select(VitalityReport)
        .where(VitalityReport.user_id == user_id)
        .order_by(VitalityReport.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No vitality report found. Generate one first via POST /reports/generate.",
        )

    return VitalityReportResponse.model_validate(report)
