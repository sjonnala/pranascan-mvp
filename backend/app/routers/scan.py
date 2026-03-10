"""Scan Session API router."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy import func as sql_func
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
from app.services.anemia_screen import screen_anemia
from app.services.delivery_service import deliver_alert
from app.services.quality_gate import run_quality_gate
from app.services.rppg_processor import build_frame_samples, process_frames
from app.services.trend_engine import (
    TrendBaseline,
    baselines_from_row,
    build_cooldown_check_query,
    build_trend_baseline_query,
    compute_trend_alert,
)
from app.services.vascular_age import estimate_vascular_age
from app.services.voice_processor import build_audio_samples, process_audio

router = APIRouter(prefix="/scans", tags=["Scans"])


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

    # Rate limit: max N scan sessions per user per hour
    one_hour_ago = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    rate_count_stmt = select(sql_func.count(ScanSession.id)).where(
        ScanSession.user_id == user_id,
        ScanSession.created_at >= one_hour_ago,
    )
    rate_result = await db.execute(rate_count_stmt)
    session_count_this_hour = rate_result.scalar_one()
    if session_count_this_hour >= settings.scan_rate_limit_per_hour:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: maximum {settings.scan_rate_limit_per_hour} "
                "scans per hour. Please try again later."
            ),
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
    rppg_flags: list[str] = []
    if body.frame_data:
        frames = build_frame_samples([f.model_dump() for f in body.frame_data])
        rppg = process_frames(frames)
        rppg_flags = rppg.flags  # propagated into result flags below

        if rppg.hr_bpm is not None:
            body = body.model_copy(
                update={
                    "hr_bpm": rppg.hr_bpm,
                    "hrv_ms": rppg.hrv_ms,
                    "respiratory_rate": rppg.respiratory_rate,
                    # rPPG quality score reflects spectral quality of the signal;
                    # take the max so a high camera quality_score isn't overwritten
                    # by a low rPPG quality when the signal is just quiet.
                    "quality_score": max(body.quality_score, rppg.quality_score),
                }
            )
        # If rPPG failed to extract HR and no client-provided HR exists,
        # hr_bpm stays None. Scan completes; flags describe the cause.

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

    # Compute trend alert from the prior 7-day multi-metric baseline.
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.trend_lookback_days)
    baseline_stmt = build_trend_baseline_query(session.user_id, cutoff)
    baseline_result = await db.execute(baseline_stmt)
    baselines = baselines_from_row(baseline_result.one())

    trend_alert = compute_trend_alert(
        {
            "hr_bpm": body.hr_bpm,
            "hrv_ms": body.hrv_ms,
            "respiratory_rate": body.respiratory_rate,
            "voice_jitter_pct": body.voice_jitter_pct,
            "voice_shimmer_pct": body.voice_shimmer_pct,
        },
        baselines,
        threshold_pct=settings.trend_alert_threshold_pct,
        min_baseline_scans=settings.trend_min_baseline_scans,
    )

    # Cooldown check: suppress the alert if one was already delivered within the window
    if trend_alert is not None:
        cooldown_cutoff = datetime.now(tz=timezone.utc) - timedelta(
            hours=settings.trend_cooldown_hours
        )
        cooldown_stmt = build_cooldown_check_query(session.user_id, cooldown_cutoff)
        cooldown_result = await db.execute(cooldown_stmt)
        if cooldown_result.scalar_one_or_none() is not None:
            trend_alert = None  # suppress — cooldown active

    # Deliver alert if one fired (after cooldown check)
    if trend_alert is not None:
        await deliver_alert(session.user_id, trend_alert)

    # Vascular age wellness indicator
    vascular_age = estimate_vascular_age(body.hr_bpm, body.hrv_ms)

    # Anemia screening wellness indicator (confidence-gated color heuristic)
    anemia = screen_anemia(
        r_mean=body.frame_r_mean,
        g_mean=body.frame_g_mean,
        b_mean=body.frame_b_mean,
        lighting_score=body.lighting_score,
        motion_score=body.motion_score,
    )

    # Merge quality-gate flags with rPPG processing flags (deduplicated)
    combined_flags = list(dict.fromkeys(gate.flags + rppg_flags))

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
        flags=combined_flags,
        trend_alert=trend_alert,
        vascular_age_estimate=vascular_age.estimate_years,
        vascular_age_confidence=vascular_age.confidence,
        hb_proxy_score=anemia.hb_proxy_score,
        anemia_wellness_label=anemia.wellness_label,
        anemia_confidence=anemia.confidence,
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
            prior_stmt = build_trend_baseline_query(user_id, cutoff, before=sess.created_at)
            prior_result = await db.execute(prior_stmt)
            baselines = baselines_from_row(prior_result.one())

            hr_baseline = baselines.get("hr_bpm", TrendBaseline(average=None, sample_count=0))
            hrv_baseline = baselines.get("hrv_ms", TrendBaseline(average=None, sample_count=0))

            if (
                scan_result.hr_bpm is not None
                and hr_baseline.average is not None
                and hr_baseline.sample_count >= settings.trend_min_baseline_scans
            ):
                hr_trend_delta = round(scan_result.hr_bpm - hr_baseline.average, 2)
            if (
                scan_result.hrv_ms is not None
                and hrv_baseline.average is not None
                and hrv_baseline.sample_count >= settings.trend_min_baseline_scans
            ):
                hrv_trend_delta = round(scan_result.hrv_ms - hrv_baseline.average, 2)

        items.append(
            ScanHistoryItem(
                session=ScanSessionResponse.model_validate(sess),
                result=ScanResultResponse.model_validate(scan_result) if scan_result else None,
                hr_trend_delta=hr_trend_delta,
                hrv_trend_delta=hrv_trend_delta,
            )
        )

    return ScanHistoryResponse(items=items, total=total, page=page, page_size=page_size)
