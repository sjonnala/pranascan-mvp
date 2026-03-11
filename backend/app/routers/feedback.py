"""Post-scan feedback API router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_auth
from app.models.feedback import ScanFeedback
from app.models.scan import ScanSession, SessionStatus
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["Feedback"])


async def _get_owned_completed_session(
    db: AsyncSession, session_id: str, user_id: str
) -> ScanSession:
    stmt = select(ScanSession).where(ScanSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status != SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback can only be recorded for completed scan sessions.",
        )

    return session


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    body: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> FeedbackResponse:
    """Record one post-scan feedback event for a completed scan session."""
    await _get_owned_completed_session(db, body.session_id, user_id)

    existing_stmt = select(ScanFeedback).where(ScanFeedback.session_id == body.session_id)
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback has already been recorded for this scan session.",
        )

    feedback = ScanFeedback(
        session_id=body.session_id,
        user_id=user_id,
        useful_response=body.useful_response,
        nps_score=body.nps_score,
        comment=body.comment,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)
    return FeedbackResponse.model_validate(feedback)


@router.get("/sessions/{session_id}", response_model=FeedbackResponse)
async def get_feedback_for_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> FeedbackResponse:
    """Fetch feedback already recorded for a completed scan session."""
    await _get_owned_completed_session(db, session_id, user_id)

    stmt = select(ScanFeedback).where(ScanFeedback.session_id == session_id)
    result = await db.execute(stmt)
    feedback = result.scalar_one_or_none()

    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback found for this scan session.",
        )

    return FeedbackResponse.model_validate(feedback)
