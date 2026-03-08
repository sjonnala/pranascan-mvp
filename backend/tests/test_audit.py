"""Tests for audit log API."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.services.audit_service import log_event
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_audit_log_list_empty(client: AsyncClient):
    """GET /audit/logs returns empty list when no logs exist."""
    resp = await client.get("/api/v1/audit/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_audit_log_created_via_service(client: AsyncClient, db_session: AsyncSession):
    """log_event service creates an immutable audit record."""
    entry = await log_event(
        db_session,
        action="test:action",
        http_method="POST",
        http_path="/api/v1/test",
        user_id=TEST_USER_ID,
        http_status=200,
        duration_ms=42,
    )
    await db_session.commit()

    assert entry.id is not None
    assert entry.action == "test:action"
    assert entry.user_id == TEST_USER_ID
    assert entry.duration_ms == 42


@pytest.mark.asyncio
async def test_audit_log_filter_by_user(client: AsyncClient, db_session: AsyncSession):
    """Audit logs can be filtered by user_id."""
    await log_event(
        db_session,
        action="consent:grant",
        http_method="POST",
        http_path="/api/v1/consent",
        user_id=TEST_USER_ID,
        http_status=201,
    )
    await log_event(
        db_session,
        action="consent:grant",
        http_method="POST",
        http_path="/api/v1/consent",
        user_id="other-user",
        http_status=201,
    )
    await db_session.commit()

    resp = await client.get("/api/v1/audit/logs", params={"user_id": TEST_USER_ID})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["user_id"] == TEST_USER_ID


@pytest.mark.asyncio
async def test_audit_logs_immutable_no_delete_endpoint(client: AsyncClient):
    """There must be no DELETE endpoint for audit logs."""
    resp = await client.delete("/api/v1/audit/logs/some-id")
    assert resp.status_code in (404, 405)


@pytest.mark.asyncio
async def test_audit_log_pagination(client: AsyncClient, db_session: AsyncSession):
    """Audit logs support pagination."""
    for i in range(5):
        await log_event(
            db_session,
            action=f"test:event:{i}",
            http_method="GET",
            http_path="/api/v1/test",
            user_id=TEST_USER_ID,
            http_status=200,
        )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/audit/logs",
        params={"user_id": TEST_USER_ID, "page": 1, "page_size": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 3
