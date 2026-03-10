"""ABHA (Ayushman Bharat Health Account) integration router."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import require_auth
from app.models.scan import ScanResult, ScanSession, SessionStatus
from app.schemas.abha import (
    AbhaLinkRequest,
    AbhaLinkResponse,
    AbhaStatusResponse,
    AbhaSyncResponse,
)
from app.services import abha_adapter

log = logging.getLogger(__name__)

router = APIRouter(prefix="/abha", tags=["ABHA Integration"])


@router.post("/link", response_model=AbhaLinkResponse, status_code=status.HTTP_201_CREATED)
async def link_abha_account(
    body: AbhaLinkRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> AbhaLinkResponse:
    """
    Link an ABHA (Ayushman Bharat Health Account) ID to the authenticated user.

    Replaces any existing link. Future completed scans will be automatically
    synced to the ABDM gateway (sandbox or live, per server configuration).

    ABHA ID must be 14 digits, with or without hyphens (e.g. 91-2345-6789-0123).
    """
    link = await abha_adapter.link_account(db, user_id, body.abha_id)
    await db.commit()

    return AbhaLinkResponse(
        user_id=user_id,
        abha_id=link.abha_id,
        linked_at=link.linked_at,
        sandbox=settings.abha_sandbox,
    )


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_abha_account(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> None:
    """
    Unlink the ABHA account for the authenticated user.

    Future scans will no longer be synced to ABDM until re-linked.
    Existing sync records are preserved for audit purposes.
    """
    found = await abha_adapter.unlink_account(db, user_id)
    await db.commit()
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active ABHA link found for this user.",
        )


@router.get("/status", response_model=AbhaStatusResponse)
async def get_abha_status(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> AbhaStatusResponse:
    """
    Return ABHA link status and last sync info for the authenticated user.
    """
    link = await abha_adapter.get_active_link(db, user_id)
    last_sync = await abha_adapter.get_last_sync(db, user_id)

    return AbhaStatusResponse(
        user_id=user_id,
        linked=link is not None,
        abha_id=link.abha_id if link else None,
        linked_at=link.linked_at if link else None,
        last_sync_at=last_sync.synced_at if last_sync else None,
        last_sync_status=last_sync.status if last_sync else None,
        abha_enabled=settings.abha_enabled,
        sandbox=settings.abha_sandbox,
    )


@router.post("/sync/{session_id}", response_model=AbhaSyncResponse)
async def sync_scan_to_abha(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_auth),
) -> AbhaSyncResponse:
    """
    Manually trigger ABHA sync for a completed scan session.

    Only the session owner can trigger sync. Session must be in COMPLETED status.

    When ABHA is disabled (abha_enabled=False), returns status='skipped_disabled'.
    When no ABHA link exists, returns status='skipped_no_link'.
    """
    # Verify session ownership and completion
    stmt = select(ScanSession).where(ScanSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status != SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not completed (status='{session.status}'). Only completed scans can be synced.",
        )

    # Fetch result vitals
    result_stmt = select(ScanResult).where(ScanResult.session_id == session_id)
    result_row = await db.execute(result_stmt)
    scan_result = result_row.scalar_one_or_none()

    vitals: dict = {}
    if scan_result:
        vitals = {
            "hr_bpm": scan_result.hr_bpm,
            "hrv_ms": scan_result.hrv_ms,
            "respiratory_rate": scan_result.respiratory_rate,
            "voice_jitter_pct": scan_result.voice_jitter_pct,
            "voice_shimmer_pct": scan_result.voice_shimmer_pct,
            "vascular_age_estimate": scan_result.vascular_age_estimate,
            "hb_proxy_score": scan_result.hb_proxy_score,
        }

    sync = await abha_adapter.sync_vitals(db, user_id, session_id, vitals)
    await db.commit()

    return AbhaSyncResponse(
        session_id=session_id,
        abha_id=sync.abha_id,
        status=sync.status,
        gateway_ref=sync.gateway_ref,
        sandbox=sync.sandbox,
        synced_at=sync.synced_at,
    )
