"""
Internal agent trigger endpoint.

POST /internal/agent/run
  - Protected by X-Agent-Secret header (must match settings.agent_secret_key).
  - Triggers one full agent cycle: discover active users, generate reports,
    fire trend alerts, deliver via configured channels.
  - Returns an AgentRunSummary as JSON.
  - Disabled (404) when settings.agent_secret_key is not configured.

This endpoint is NOT included in the public OpenAPI docs.
It is intended to be called by the OpenClaw cron job or the CLI runner only.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.agent_runner import AgentRunSummary, run_agent_cycle

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["Internal"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class UserRunResultResponse(BaseModel):
    user_id: str
    report_generated: bool
    alert_sent: bool
    error: str | None


class AgentRunResponse(BaseModel):
    run_at: datetime
    users_found: int
    reports_generated: int
    alerts_sent: int
    errors: list[str]
    results: list[UserRunResultResponse]

    @classmethod
    def from_summary(cls, summary: AgentRunSummary) -> "AgentRunResponse":
        return cls(
            run_at=summary.run_at,
            users_found=summary.users_found,
            reports_generated=summary.reports_generated,
            alerts_sent=summary.alerts_sent,
            errors=summary.errors,
            results=[
                UserRunResultResponse(
                    user_id=r.user_id,
                    report_generated=r.report_generated,
                    alert_sent=r.alert_sent,
                    error=r.error,
                )
                for r in summary.results
            ],
        )


# ---------------------------------------------------------------------------
# Dependency: verify agent secret
# ---------------------------------------------------------------------------


def _verify_agent_secret(request: Request) -> None:
    """Raise 404 if agent is not configured; 401 if secret is wrong."""
    if not settings.agent_secret_key:
        # Return 404 so the endpoint doesn't leak existence when unconfigured
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    provided = request.headers.get("X-Agent-Secret", "")
    if provided != settings.agent_secret_key:
        log.warning("agent_secret_mismatch", extra={"remote": request.client.host if request.client else "unknown"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent secret")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/agent/run",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
)
async def trigger_agent_run(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_agent_secret),
) -> AgentRunResponse:
    """
    Trigger one agent cycle.

    Discovers all active users (consented + enough recent scans), generates
    their weekly vitality report, and fires trend alerts where applicable.

    Requires ``X-Agent-Secret`` header matching ``AGENT_SECRET_KEY`` env var.
    Returns 404 when ``AGENT_SECRET_KEY`` is not configured.
    """
    summary = await run_agent_cycle(db)
    return AgentRunResponse.from_summary(summary)
