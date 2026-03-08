"""Consent & Privacy Flow router."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_auth
from app.schemas.consent import (
    ConsentDeletionRequest,
    ConsentGrantRequest,
    ConsentRecordResponse,
    ConsentRevokeRequest,
    ConsentStatusResponse,
)
from app.services import consent_service

router = APIRouter(prefix="/consent", tags=["Consent"])


def _extract_client_info(request: Request) -> tuple[str | None, str | None]:
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )
    ua = request.headers.get("user-agent")
    return ip, ua


@router.post("", response_model=ConsentRecordResponse, status_code=status.HTTP_201_CREATED)
async def grant_consent(
    body: ConsentGrantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_auth),
) -> ConsentRecordResponse:
    """
    Record informed consent for wellness screening.

    Consent records are append-only — previous records are never modified.
    """
    ip, ua = _extract_client_info(request)
    record = await consent_service.grant_consent(
        db,
        user_id=body.user_id,
        consent_version=body.consent_version,
        purpose=body.purpose,
        ip_address=body.ip_address or ip,
        user_agent=body.user_agent or ua,
    )
    return ConsentRecordResponse.model_validate(record)


@router.post("/revoke", response_model=ConsentRecordResponse, status_code=status.HTTP_201_CREATED)
async def revoke_consent(
    body: ConsentRevokeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_auth),
) -> ConsentRecordResponse:
    """
    Revoke consent. Appends a revocation record; does not delete prior records.
    """
    ip, ua = _extract_client_info(request)
    record = await consent_service.revoke_consent(
        db,
        user_id=body.user_id,
        ip_address=ip,
        user_agent=ua,
    )
    return ConsentRecordResponse.model_validate(record)


@router.post(
    "/deletion-request",
    response_model=ConsentRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_deletion(
    body: ConsentDeletionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_auth),
) -> ConsentRecordResponse:
    """
    Request data deletion. Data will be soft-deleted after a 30-day legal hold period.
    """
    ip, ua = _extract_client_info(request)
    record = await consent_service.request_deletion(
        db,
        user_id=body.user_id,
        ip_address=ip,
        user_agent=ua,
    )
    return ConsentRecordResponse.model_validate(record)


@router.get("/status", response_model=ConsentStatusResponse)
async def get_consent_status(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConsentStatusResponse:
    """
    Get current consent status for a user.
    Computes status from the append-only consent ledger.
    """
    return await consent_service.get_consent_status(db, user_id)
