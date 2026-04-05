"""Scan Session API router."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import enforce_self_scope, require_auth
from app.schemas.scan import (
    ScanHistoryItem,
    ScanHistoryResponse,
    ScanResultResponse,
    ScanResultSubmit,
    ScanSessionCreateRequest,
    ScanSessionResponse,
    ScanSessionWithResult,
)
from app.services.scan_service import (
    ScanServiceError,
    get_scan_history_page,
    get_scan_session_with_result,
)
from app.services.scan_service import (
    complete_scan_session as complete_scan_session_workflow,
)
from app.services.scan_service import (
    create_scan_session as create_scan_session_workflow,
)

router = APIRouter(prefix="/scans", tags=["Scans"])


@router.post("/sessions", response_model=ScanSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_scan_session(
    body: ScanSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanSessionResponse:
    user_id = enforce_self_scope(auth_user_id, body.user_id)
    try:
        session = await create_scan_session_workflow(
            db,
            user_id=user_id,
            device_model=body.device_model,
            app_version=body.app_version,
        )
    except ScanServiceError as exc:
        _raise_http_for_scan_service_error(exc)
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
    try:
        scan_result = await complete_scan_session_workflow(
            db,
            session_id=session_id,
            auth_user_id=auth_user_id,
            submission=body,
        )
    except ScanServiceError as exc:
        _raise_http_for_scan_service_error(exc)
    return ScanResultResponse.model_validate(scan_result)


@router.get("/sessions/{session_id}", response_model=ScanSessionWithResult)
async def get_scan_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanSessionWithResult:
    try:
        scan_bundle = await get_scan_session_with_result(
            db,
            session_id=session_id,
            auth_user_id=auth_user_id,
        )
    except ScanServiceError as exc:
        _raise_http_for_scan_service_error(exc)
    return ScanSessionWithResult(
        session=ScanSessionResponse.model_validate(scan_bundle.session),
        result=(
            ScanResultResponse.model_validate(scan_bundle.result)
            if scan_bundle.result is not None
            else None
        ),
    )


@router.get("/history", response_model=ScanHistoryResponse)
async def get_scan_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(require_auth),
) -> ScanHistoryResponse:
    history_page = await get_scan_history_page(
        db,
        user_id=auth_user_id,
        page=page,
        page_size=page_size,
    )
    items = [
        ScanHistoryItem(
            session=ScanSessionResponse.model_validate(item.session),
            result=ScanResultResponse.model_validate(item.result) if item.result is not None else None,
            hr_trend_delta=item.hr_trend_delta,
            hrv_trend_delta=item.hrv_trend_delta,
        )
        for item in history_page.items
    ]
    return ScanHistoryResponse(
        items=items,
        total=history_page.total,
        page=history_page.page,
        page_size=history_page.page_size,
    )


def _raise_http_for_scan_service_error(exc: ScanServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
