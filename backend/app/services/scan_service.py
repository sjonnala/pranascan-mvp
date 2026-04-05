"""Application service for scan session orchestration."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.scan import ScanResult, ScanSession, SessionStatus
from app.schemas.scan import ScanResultSubmit
from app.services import consent_service
from app.services.anemia_screen import screen_anemia
from app.services.delivery_service import deliver_alert
from app.services.quality_gate import run_quality_gate
from app.services.rppg_processor import build_frame_samples, process_frames
from app.services.skin_tone import apply_skin_tone_calibration
from app.services.trend_engine import (
    TrendBaseline,
    baselines_from_row,
    build_cooldown_check_query,
    build_trend_baseline_query,
    compute_trend_alert,
)
from app.services.vascular_age import estimate_vascular_age
from app.services.voice_processor import build_audio_samples, process_audio


class ScanServiceError(Exception):
    """Base exception for scan service failures."""

    def __init__(self, *, status_code: int, detail: str | dict[str, object]) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class ActiveConsentRequiredError(ScanServiceError):
    """Raised when a user attempts to scan without active consent."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            detail="Active consent required to start a scan session. Please grant consent first.",
        )


class ScanRateLimitExceededError(ScanServiceError):
    """Raised when a user exceeds the configured scan rate limit."""

    def __init__(self, *, limit_per_hour: int) -> None:
        super().__init__(
            status_code=429,
            detail=(
                f"Rate limit exceeded: maximum {limit_per_hour} "
                "scans per hour. Please try again later."
            ),
        )


class ScanSessionNotFoundError(ScanServiceError):
    """Raised when a scan session cannot be found."""

    def __init__(self) -> None:
        super().__init__(status_code=404, detail="Session not found")


class ScanSessionAccessDeniedError(ScanServiceError):
    """Raised when a caller attempts to act on another user's session."""

    def __init__(self) -> None:
        super().__init__(status_code=403, detail="Session not found")


class ScanSessionConflictError(ScanServiceError):
    """Raised when a scan session is not in a state that allows the request."""

    def __init__(self, *, session_status: str) -> None:
        super().__init__(
            status_code=409,
            detail=f"Session is already in status '{session_status}'",
        )


class ScanQualityRejectedError(ScanServiceError):
    """Raised when quality-gate validation rejects a submitted scan."""

    def __init__(self, *, flags: list[str], rejection_reason: str | None) -> None:
        super().__init__(
            status_code=422,
            detail={
                "message": "Scan quality was insufficient. Please retry in better conditions.",
                "flags": flags,
                "rejection_reason": rejection_reason,
            },
        )


@dataclass(frozen=True)
class ScanSessionBundle:
    """One scan session and its persisted result, if any."""

    session: ScanSession
    result: ScanResult | None


@dataclass(frozen=True)
class ScanHistoryEntry:
    """One history row enriched with prior-baseline deltas."""

    session: ScanSession
    result: ScanResult | None
    hr_trend_delta: float | None
    hrv_trend_delta: float | None


@dataclass(frozen=True)
class ScanHistoryPage:
    """Paginated scan history response payload."""

    items: list[ScanHistoryEntry]
    total: int
    page: int
    page_size: int


async def create_scan_session(
    db: AsyncSession,
    *,
    user_id: str,
    device_model: str | None,
    app_version: str | None,
) -> ScanSession:
    """Create a new scan session after consent and rate-limit checks."""
    if not await consent_service.has_active_consent(db, user_id):
        raise ActiveConsentRequiredError()

    one_hour_ago = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    rate_count_stmt = select(func.count(ScanSession.id)).where(
        ScanSession.user_id == user_id,
        ScanSession.created_at >= one_hour_ago,
    )
    rate_result = await db.execute(rate_count_stmt)
    session_count_this_hour = rate_result.scalar_one()
    if session_count_this_hour >= settings.scan_rate_limit_per_hour:
        raise ScanRateLimitExceededError(limit_per_hour=settings.scan_rate_limit_per_hour)

    session = ScanSession(
        user_id=user_id,
        device_model=device_model,
        app_version=app_version,
        status=SessionStatus.INITIATED,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def complete_scan_session(
    db: AsyncSession,
    *,
    session_id: str,
    auth_user_id: str,
    submission: ScanResultSubmit,
) -> ScanResult:
    """Complete one scan session and persist its wellness result."""
    session = await _get_session_or_raise(db, session_id)
    if session.user_id != auth_user_id:
        raise ScanSessionAccessDeniedError()
    if session.status != SessionStatus.INITIATED:
        raise ScanSessionConflictError(session_status=session.status)

    submission, rppg_flags = _apply_server_side_rppg(submission)
    submission = _apply_server_side_voice_dsp(submission)

    gate = run_quality_gate(submission)
    if not gate.passed:
        session.status = SessionStatus.REJECTED
        session.completed_at = datetime.now(tz=timezone.utc)
        await db.flush()
        raise ScanQualityRejectedError(
            flags=gate.flags,
            rejection_reason=gate.rejection_reason,
        )

    trend_alert = await _compute_trend_alert_for_submission(db, session.user_id, submission)
    if trend_alert is not None:
        await deliver_alert(session.user_id, trend_alert)

    vascular_age = estimate_vascular_age(submission.hr_bpm, submission.hrv_ms)
    anemia = screen_anemia(
        r_mean=submission.frame_r_mean,
        g_mean=submission.frame_g_mean,
        b_mean=submission.frame_b_mean,
        lighting_score=submission.lighting_score,
        motion_score=submission.motion_score,
    )
    combined_flags = list(dict.fromkeys(gate.flags + rppg_flags))

    scan_result = ScanResult(
        session_id=session_id,
        user_id=session.user_id,
        hr_bpm=submission.hr_bpm,
        hrv_ms=submission.hrv_ms,
        respiratory_rate=submission.respiratory_rate,
        voice_jitter_pct=submission.voice_jitter_pct,
        voice_shimmer_pct=submission.voice_shimmer_pct,
        quality_score=submission.quality_score,
        lighting_score=submission.lighting_score,
        motion_score=submission.motion_score,
        face_confidence=submission.face_confidence,
        audio_snr_db=submission.audio_snr_db,
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
    return scan_result


async def get_scan_session_with_result(
    db: AsyncSession,
    *,
    session_id: str,
    auth_user_id: str,
) -> ScanSessionBundle:
    """Return one owned session and its result."""
    session = await _get_session_or_raise(db, session_id)
    if session.user_id != auth_user_id:
        raise ScanSessionNotFoundError()

    result_stmt = select(ScanResult).where(ScanResult.session_id == session_id)
    result_row = await db.execute(result_stmt)
    scan_result = result_row.scalar_one_or_none()
    return ScanSessionBundle(session=session, result=scan_result)


async def get_scan_history_page(
    db: AsyncSession,
    *,
    user_id: str,
    page: int,
    page_size: int,
) -> ScanHistoryPage:
    """Return paginated scan history with prior-baseline deltas."""
    offset = (page - 1) * page_size

    count_stmt = select(func.count(ScanSession.id)).where(
        ScanSession.user_id == user_id,
        ScanSession.status == SessionStatus.COMPLETED,
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    sessions_stmt = (
        select(ScanSession)
        .where(ScanSession.user_id == user_id, ScanSession.status == SessionStatus.COMPLETED)
        .order_by(ScanSession.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    sessions_result = await db.execute(sessions_stmt)
    sessions = sessions_result.scalars().all()

    items: list[ScanHistoryEntry] = []
    for session in sessions:
        result_stmt = select(ScanResult).where(ScanResult.session_id == session.id)
        result_row = await db.execute(result_stmt)
        scan_result = result_row.scalar_one_or_none()
        hr_trend_delta, hrv_trend_delta = await _compute_history_deltas(
            db,
            user_id,
            session,
            scan_result,
        )
        items.append(
            ScanHistoryEntry(
                session=session,
                result=scan_result,
                hr_trend_delta=hr_trend_delta,
                hrv_trend_delta=hrv_trend_delta,
            )
        )

    return ScanHistoryPage(items=items, total=total, page=page, page_size=page_size)


async def _get_session_or_raise(db: AsyncSession, session_id: str) -> ScanSession:
    stmt = select(ScanSession).where(ScanSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise ScanSessionNotFoundError()
    return session


def _apply_server_side_rppg(submission: ScanResultSubmit) -> tuple[ScanResultSubmit, list[str]]:
    rppg_flags: list[str] = []
    if not submission.frame_data:
        return submission, rppg_flags

    frames = build_frame_samples([frame.model_dump() for frame in submission.frame_data])
    rppg = process_frames(frames)
    rppg, _skin_calibration = apply_skin_tone_calibration(rppg, frames)
    rppg_flags = rppg.flags

    if rppg.hr_bpm is None:
        return submission, rppg_flags

    return (
        submission.model_copy(
            update={
                "hr_bpm": rppg.hr_bpm,
                "hrv_ms": rppg.hrv_ms,
                "respiratory_rate": rppg.respiratory_rate,
                "quality_score": max(submission.quality_score, rppg.quality_score),
            }
        ),
        rppg_flags,
    )


def _apply_server_side_voice_dsp(submission: ScanResultSubmit) -> ScanResultSubmit:
    if not submission.audio_samples:
        return submission

    audio = build_audio_samples(submission.audio_samples)
    voice = process_audio(audio)
    if voice.jitter_pct is None:
        return submission

    return submission.model_copy(
        update={
            "voice_jitter_pct": voice.jitter_pct,
            "voice_shimmer_pct": voice.shimmer_pct,
            "audio_snr_db": voice.snr_db if voice.snr_db is not None else submission.audio_snr_db,
        }
    )


async def _compute_trend_alert_for_submission(
    db: AsyncSession,
    user_id: str,
    submission: ScanResultSubmit,
) -> str | None:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.trend_lookback_days)
    baseline_stmt = build_trend_baseline_query(user_id, cutoff)
    baseline_result = await db.execute(baseline_stmt)
    baselines = baselines_from_row(baseline_result.one())

    trend_alert = compute_trend_alert(
        {
            "hr_bpm": submission.hr_bpm,
            "hrv_ms": submission.hrv_ms,
            "respiratory_rate": submission.respiratory_rate,
            "voice_jitter_pct": submission.voice_jitter_pct,
            "voice_shimmer_pct": submission.voice_shimmer_pct,
        },
        baselines,
        threshold_pct=settings.trend_alert_threshold_pct,
        min_baseline_scans=settings.trend_min_baseline_scans,
    )
    if trend_alert is None:
        return None

    cooldown_cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=settings.trend_cooldown_hours)
    cooldown_stmt = build_cooldown_check_query(user_id, cooldown_cutoff)
    cooldown_result = await db.execute(cooldown_stmt)
    if cooldown_result.scalar_one_or_none() is not None:
        return None

    return trend_alert


async def _compute_history_deltas(
    db: AsyncSession,
    user_id: str,
    session: ScanSession,
    scan_result: ScanResult | None,
) -> tuple[float | None, float | None]:
    if scan_result is None or session.created_at is None:
        return None, None

    cutoff = session.created_at - timedelta(days=settings.trend_lookback_days)
    prior_stmt = build_trend_baseline_query(user_id, cutoff, before=session.created_at)
    prior_result = await db.execute(prior_stmt)
    baselines = baselines_from_row(prior_result.one())

    hr_baseline = baselines.get("hr_bpm", TrendBaseline(average=None, sample_count=0))
    hrv_baseline = baselines.get("hrv_ms", TrendBaseline(average=None, sample_count=0))

    hr_trend_delta = None
    if (
        scan_result.hr_bpm is not None
        and hr_baseline.average is not None
        and hr_baseline.sample_count >= settings.trend_min_baseline_scans
    ):
        hr_trend_delta = round(scan_result.hr_bpm - hr_baseline.average, 2)

    hrv_trend_delta = None
    if (
        scan_result.hrv_ms is not None
        and hrv_baseline.average is not None
        and hrv_baseline.sample_count >= settings.trend_min_baseline_scans
    ):
        hrv_trend_delta = round(scan_result.hrv_ms - hrv_baseline.average, 2)

    return hr_trend_delta, hrv_trend_delta
