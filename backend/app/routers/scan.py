"""Scan Session API router."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import require_auth
from app.models.scan import ScanResult, ScanSession, SessionStatus
from app.schemas.scan import (
    ScanHistoryItem,
    ScanHistoryResponse,
    ScanResultResponse,
    ScanResultSubmit,
    ScanSessionCreateRequest,
    ScanSessionResponse,
    ScanSessionWithResult,
)
from app.services import consent_service
from app.services.quality_gate import run_quality_gate
from app.services.rppg_processor import build_frame_samples, process_frames
from app.services.voice_processor import build_audio_samples, process_audio

router = APIRouter(prefix="/scans", tags=["Scans"])


def _compute_trend_alert(
    current_hr: float | None,
    baseline_hr: float | None,
    threshold_pct: float,
) -> str | None:
    """
    Determine if a trend alert should be raised.
    Returns "consider_lab_followup" or None.
    Never returns diagnostic language.
    """
    if current_hr is None or baseline_hr is None or baseline_hr == 0:
        return None
    delta_pct = abs((current_hr - baseline_hr) / baseline_hr) * 100
    if delta_pct >= threshold_pct:
        return "consider_lab_followup"
    return None


@router.post("/sessions", response_model=ScanSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_scan_session(
    body: ScanSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanSessionResponse:
    """
    Initiate a new scan session.
    Requires active consent — returns 403 if not consented.
    """
    # Use authenticated user_id; ignore any user_id in body to prevent spoofing
    user_id = auth_user_id

    if not await consent_service.has_active_consent(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active consent required to start a scan session. Please grant consent first.",
        )

    session = ScanSession(
        user_id=user_id,
        device_model=body.device_model,
        app_version=body.app_version,
        status=SessionStatus.INITIATED,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return ScanSessionResponse.model_validate(session)


@router.put(
    "/sessions/{session_id}/complete",
    response_model=ScanResultResponse,
    status_code=status.HTTP_200_OK,
)
async def complete_scan_session(
    session_id: str,
    body: ScanResultSubmit,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanResultResponse:
    """
    Submit wellness indicator results for a scan session.

    Runs quality gate validation. If any threshold fails,
    the session is marked REJECTED and a 422 is returned.

    Raw video/audio must NOT be submitted here — edge processing only.
    """
    # Fetch session
    stmt = select(ScanSession).where(ScanSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Ensure authenticated user owns this session
    if session.user_id != auth_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session not found")

    if session.status != SessionStatus.INITIATED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already in status '{session.status}'",
        )

    # -------------------------------------------------------------------
    # Server-side rPPG processing (if frame_data provided)
    # -------------------------------------------------------------------
    if body.frame_data:
        frames = build_frame_samples([f.model_dump() for f in body.frame_data])
        rppg = process_frames(frames)
        if rppg.hr_bpm is not None:
            body = body.model_copy(
                update={
                    "hr_bpm": rppg.hr_bpm,
                    "hrv_ms": rppg.hrv_ms,
                    "respiratory_rate": rppg.respiratory_rate,
                    "quality_score": max(body.quality_score, rppg.quality_score),
                }
            )

    # -------------------------------------------------------------------
    # Server-side voice DSP processing (if audio_samples provided)
    # -------------------------------------------------------------------
    if body.audio_samples:
        audio = build_audio_samples(body.audio_samples)
        voice = process_audio(audio)
        if voice.jitter_pct is not None:
            body = body.model_copy(
                update={
                    "voice_jitter_pct": voice.jitter_pct,
                    "voice_shimmer_pct": voice.shimmer_pct,
                    "audio_snr_db": voice.snr_db if voice.snr_db is not None else body.audio_snr_db,
                }
            )

    # Quality gate
    gate = run_quality_gate(body)
    if not gate.passed:
        session.status = SessionStatus.REJECTED
        session.completed_at = datetime.now(tz=timezone.utc)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Scan quality was insufficient. Please retry in better conditions.",
                "flags": gate.flags,
                "rejection_reason": gate.rejection_reason,
            },
        )

    # Compute trend alert from 7-day baseline
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.trend_lookback_days)
    baseline_stmt = select(func.avg(ScanResult.hr_bpm)).where(
        ScanResult.user_id == session.user_id,
        ScanResult.created_at >= cutoff,
    )
    baseline_result = await db.execute(baseline_stmt)
    baseline_hr = baseline_result.scalar_one_or_none()

    trend_alert = _compute_trend_alert(
        body.hr_bpm,
        baseline_hr,
        settings.trend_alert_threshold_pct,
    )

    # Persist result
    scan_result = ScanResult(
        session_id=session_id,
        user_id=session.user_id,
        hr_bpm=body.hr_bpm,
        hrv_ms=body.hrv_ms,
        respiratory_rate=body.respiratory_rate,
        voice_jitter_pct=body.voice_jitter_pct,
        voice_shimmer_pct=body.voice_shimmer_pct,
        quality_score=body.quality_score,
        lighting_score=body.lighting_score,
        motion_score=body.motion_score,
        face_confidence=body.face_confidence,
        audio_snr_db=body.audio_snr_db,
        flags=gate.flags,
        trend_alert=trend_alert,
    )
    db.add(scan_result)

    session.status = SessionStatus.COMPLETED
    session.completed_at = datetime.now(tz=timezone.utc)
    await db.flush()
    await db.refresh(scan_result)

    return ScanResultResponse.model_validate(scan_result)


@router.get("/sessions/{session_id}", response_model=ScanSessionWithResult)
async def get_scan_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanSessionWithResult:
    """Fetch a single scan session with its result (if completed)."""
    stmt = select(ScanSession).where(ScanSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None or session.user_id != auth_user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    result_stmt = select(ScanResult).where(ScanResult.session_id == session_id)
    result_row = await db.execute(result_stmt)
    scan_result = result_row.scalar_one_or_none()

    return ScanSessionWithResult(
        session=ScanSessionResponse.model_validate(session),
        result=ScanResultResponse.model_validate(scan_result) if scan_result else None,
    )


@router.get("/history", response_model=ScanHistoryResponse)
async def get_scan_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanHistoryResponse:
    """
    Paginated scan history for a user, with trend deltas vs prior 7-day average.
    """
    offset = (page - 1) * page_size

    user_id = auth_user_id

    # Total count
    count_stmt = select(func.count(ScanSession.id)).where(
        ScanSession.user_id == user_id,
        ScanSession.status == SessionStatus.COMPLETED,
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Page of sessions
    sessions_stmt = (
        select(ScanSession)
        .where(ScanSession.user_id == user_id, ScanSession.status == SessionStatus.COMPLETED)
        .order_by(ScanSession.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    sessions_result = await db.execute(sessions_stmt)
    sessions = sessions_result.scalars().all()

    items: list[ScanHistoryItem] = []
    for sess in sessions:
        result_stmt = select(ScanResult).where(ScanResult.session_id == sess.id)
        result_row = await db.execute(result_stmt)
        scan_result = result_row.scalar_one_or_none()

        # Compute trend delta: compare this result vs prior 7-day avg (excluding this scan)
        hr_trend_delta = None
        hrv_trend_delta = None
        if scan_result and sess.created_at:
            cutoff = sess.created_at - timedelta(days=settings.trend_lookback_days)
            prior_stmt = select(
                func.avg(ScanResult.hr_bpm),
                func.avg(ScanResult.hrv_ms),
            ).where(
                ScanResult.user_id == user_id,
                ScanResult.created_at >= cutoff,
                ScanResult.created_at < sess.created_at,
            )
            prior_result = await db.execute(prior_stmt)
            prior_hr, prior_hrv = prior_result.one()

            if scan_result.hr_bpm is not None and prior_hr is not None:
                hr_trend_delta = round(scan_result.hr_bpm - prior_hr, 2)
            if scan_result.hrv_ms is not None and prior_hrv is not None:
                hrv_trend_delta = round(scan_result.hrv_ms - prior_hrv, 2)

        items.append(
            ScanHistoryItem(
                session=ScanSessionResponse.model_validate(sess),
                result=ScanResultResponse.model_validate(scan_result) if scan_result else None,
                hr_trend_delta=hr_trend_delta,
                hrv_trend_delta=hrv_trend_delta,
            )
        )

    return ScanHistoryResponse(items=items, total=total, page=page, page_size=page_size)
