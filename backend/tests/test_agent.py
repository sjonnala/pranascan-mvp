"""Tests for the background agent runner and internal trigger endpoint."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.consent import ConsentAction, ConsentRecord
from app.models.scan import ScanResult, ScanSession, SessionStatus
from app.services.agent_runner import get_active_user_ids, run_agent_cycle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _seed_user(
    db: AsyncSession,
    user_id: str,
    *,
    consent_action: str = ConsentAction.GRANTED,
    scan_count: int = 5,
    days_ago: int = 2,
) -> None:
    """Seed a user with consent + scan results in the DB."""
    consent = ConsentRecord(
        user_id=user_id,
        action=consent_action,
        consent_version="1.0",
        purpose="test",
    )
    db.add(consent)

    for i in range(scan_count):
        session = ScanSession(
            user_id=user_id,
            status=SessionStatus.COMPLETED,
        )
        db.add(session)
        await db.flush()

        result = ScanResult(
            session_id=session.id,
            user_id=user_id,
            hr_bpm=72.0 + i,
            hrv_ms=45.0,
            respiratory_rate=15.0,
            voice_jitter_pct=0.5,
            voice_shimmer_pct=3.0,
            created_at=_now() - timedelta(days=days_ago, seconds=i),
        )
        db.add(result)

    await db.flush()


# ---------------------------------------------------------------------------
# get_active_user_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_user_ids_returns_consented_users_with_enough_scans(
    db_session: AsyncSession,
):
    """User with active consent and ≥3 scans in the lookback window is returned."""
    await _seed_user(db_session, "user-active", scan_count=settings.trend_min_baseline_scans)
    result = await get_active_user_ids(db_session)
    assert "user-active" in result


@pytest.mark.asyncio
async def test_get_active_user_ids_excludes_revoked_consent(db_session: AsyncSession):
    """User with revoked consent is excluded even if they have enough scans."""
    await _seed_user(db_session, "user-revoked", consent_action=ConsentAction.REVOKED)
    result = await get_active_user_ids(db_session)
    assert "user-revoked" not in result


@pytest.mark.asyncio
async def test_get_active_user_ids_excludes_deletion_requested(db_session: AsyncSession):
    """User who requested deletion is excluded."""
    await _seed_user(
        db_session,
        "user-delete",
        consent_action=ConsentAction.DELETION_REQUESTED,
    )
    result = await get_active_user_ids(db_session)
    assert "user-delete" not in result


@pytest.mark.asyncio
async def test_get_active_user_ids_excludes_insufficient_scans(db_session: AsyncSession):
    """User with fewer than trend_min_baseline_scans recent scans is excluded."""
    await _seed_user(
        db_session,
        "user-few-scans",
        scan_count=settings.trend_min_baseline_scans - 1,
    )
    result = await get_active_user_ids(db_session)
    assert "user-few-scans" not in result


@pytest.mark.asyncio
async def test_get_active_user_ids_returns_empty_when_no_users(db_session: AsyncSession):
    """Returns empty list when no qualifying users exist."""
    result = await get_active_user_ids(db_session)
    assert result == []


# ---------------------------------------------------------------------------
# run_agent_cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_cycle_generates_report_for_active_user(db_session: AsyncSession):
    """Agent cycle generates a report for each active user."""
    await _seed_user(db_session, "user-cycle", scan_count=5)

    with patch("app.services.agent_runner.deliver_report", new_callable=AsyncMock) as mock_deliver:
        summary = await run_agent_cycle(db_session)

    assert summary.users_found >= 1
    assert summary.reports_generated >= 1
    assert len(summary.errors) == 0
    mock_deliver.assert_called()


@pytest.mark.asyncio
async def test_run_agent_cycle_returns_zero_when_no_active_users(db_session: AsyncSession):
    """Agent cycle produces an empty summary when no users qualify."""
    summary = await run_agent_cycle(db_session)
    assert summary.users_found == 0
    assert summary.reports_generated == 0
    assert summary.alerts_sent == 0


@pytest.mark.asyncio
async def test_run_agent_cycle_does_not_propagate_per_user_errors(db_session: AsyncSession):
    """Processing error for one user is captured in summary, does not crash cycle."""
    await _seed_user(db_session, "user-err", scan_count=5)

    with (
        patch("app.services.agent_runner.deliver_report", new_callable=AsyncMock),
        patch(
            "app.services.agent_runner.generate_report",
            side_effect=RuntimeError("simulated failure"),
        ),
    ):
        summary = await run_agent_cycle(db_session)

    assert summary.users_found >= 1
    assert summary.reports_generated == 0
    assert len(summary.errors) >= 1


@pytest.mark.asyncio
async def test_run_agent_cycle_has_correct_run_at_timestamp(db_session: AsyncSession):
    """AgentRunSummary.run_at is a recent UTC datetime."""
    before = _now()
    summary = await run_agent_cycle(db_session)
    after = _now()
    assert before <= summary.run_at <= after


# ---------------------------------------------------------------------------
# Internal HTTP endpoint — /internal/agent/run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_endpoint_returns_404_when_not_configured(client: AsyncClient):
    """Endpoint returns 404 when AGENT_SECRET_KEY is not configured."""
    with patch.object(settings, "agent_secret_key", None):
        response = await client.post(
            "/api/v1/internal/agent/run",
            headers={"X-Agent-Secret": "anything"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_endpoint_returns_401_with_wrong_secret(client: AsyncClient):
    """Endpoint returns 401 when X-Agent-Secret does not match."""
    with patch.object(settings, "agent_secret_key", "correct-secret"):
        response = await client.post(
            "/api/v1/internal/agent/run",
            headers={"X-Agent-Secret": "wrong-secret"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_endpoint_runs_cycle_with_correct_secret(
    client: AsyncClient, db_session: AsyncSession
):
    """Endpoint triggers agent cycle and returns summary JSON with correct secret."""
    with (
        patch.object(settings, "agent_secret_key", "test-agent-secret"),
        patch(
            "app.services.agent_runner.deliver_report", new_callable=AsyncMock
        ),
    ):
        response = await client.post(
            "/api/v1/internal/agent/run",
            headers={"X-Agent-Secret": "test-agent-secret"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "users_found" in data
    assert "reports_generated" in data
    assert "alerts_sent" in data
    assert "errors" in data
    assert "run_at" in data


@pytest.mark.asyncio
async def test_agent_endpoint_not_in_openapi_schema(client: AsyncClient):
    """/internal/agent/run is excluded from the public OpenAPI schema."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json().get("paths", {})
    assert "/api/v1/internal/agent/run" not in paths
