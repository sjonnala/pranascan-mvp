#!/usr/bin/env python3
"""
PranaScan background agent — CLI entrypoint.

Usage
-----
  # Direct mode (imports service-intelligence modules, no HTTP server required):
  PYTHONPATH=../service-intelligence python3 pranascan_agent.py

  # HTTP mode (calls POST /internal/agent/run; server must be running):
  python3 pranascan_agent.py --http --base-url http://localhost:8000 --secret <key>

Environment variables (direct mode):
  DATABASE_URL          SQLAlchemy async URL (default: sqlite+aiosqlite:///./pranascan_test.db)
  TELEGRAM_BOT_TOKEN    Optional — enables Telegram delivery
  TELEGRAM_CHAT_ID      Optional — Telegram chat to deliver to
  AGENT_SECRET_KEY      Optional — matches the service-intelligence config for HTTP mode

Designed to be triggered by:
  - OpenClaw cron (weekly, via agentTurn or systemEvent payload)
  - systemd timer / crontab for standalone deployments
  - Manual run for testing

Exit codes:
  0   Success (even if some users had processing errors — see summary)
  1   Fatal startup / connection error
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("pranascan_agent")


# ---------------------------------------------------------------------------
# Direct mode (imports service-intelligence directly)
# ---------------------------------------------------------------------------


async def _run_direct() -> int:
    """Run the agent cycle by importing service-intelligence services directly."""
    try:
        from app.database import AsyncSessionLocal  # type: ignore[import]
        from app.services.agent_runner import run_agent_cycle  # type: ignore[import]
    except ImportError as exc:
        log.error(
            "Cannot import service-intelligence modules. "
            "Set PYTHONPATH=../service-intelligence. Error: %s",
            exc,
        )
        return 1

    log.info("PranaScan agent starting (direct mode) at %s", datetime.now(tz=timezone.utc).isoformat())

    async with AsyncSessionLocal() as db:
        async with db.begin():
            summary = await run_agent_cycle(db)

    _print_summary(summary)
    return 0


# ---------------------------------------------------------------------------
# HTTP mode (calls /internal/agent/run)
# ---------------------------------------------------------------------------


async def _run_http(base_url: str, secret: str) -> int:
    """Trigger the agent by calling the internal HTTP endpoint."""
    try:
        import httpx
    except ImportError:
        log.error("httpx is required for HTTP mode. Install: pip install httpx")
        return 1

    url = f"{base_url.rstrip('/')}/api/v1/internal/agent/run"
    log.info("PranaScan agent starting (HTTP mode) → %s", url)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers={"X-Agent-Secret": secret})
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.error("Agent HTTP call failed: %s %s", exc.response.status_code, exc.response.text)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("Agent HTTP call error: %s", exc)
        return 1

    _print_summary_dict(data)
    return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_summary(summary: object) -> None:
    """Print a structured summary from an AgentRunSummary dataclass."""
    print("\n── PranaScan Agent Run Summary ──────────────────")
    print(f"  Run at          : {summary.run_at.isoformat()}")  # type: ignore[attr-defined]
    print(f"  Users found     : {summary.users_found}")  # type: ignore[attr-defined]
    print(f"  Reports issued  : {summary.reports_generated}")  # type: ignore[attr-defined]
    print(f"  Alerts sent     : {summary.alerts_sent}")  # type: ignore[attr-defined]
    if summary.errors:  # type: ignore[attr-defined]
        print(f"  Errors          : {len(summary.errors)}")  # type: ignore[attr-defined]
        for err in summary.errors:  # type: ignore[attr-defined]
            print(f"    ✗ {err}")
    else:
        print("  Errors          : 0")
    print("─────────────────────────────────────────────────\n")


def _print_summary_dict(data: dict) -> None:
    """Print a structured summary from an HTTP response dict."""
    print("\n── PranaScan Agent Run Summary ──────────────────")
    print(f"  Run at          : {data.get('run_at', 'unknown')}")
    print(f"  Users found     : {data.get('users_found', 0)}")
    print(f"  Reports issued  : {data.get('reports_generated', 0)}")
    print(f"  Alerts sent     : {data.get('alerts_sent', 0)}")
    errors = data.get("errors", [])
    print(f"  Errors          : {len(errors)}")
    for err in errors:
        print(f"    ✗ {err}")
    print("─────────────────────────────────────────────────\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PranaScan background agent runner")
    parser.add_argument(
        "--http",
        action="store_true",
        help="HTTP mode: call /internal/agent/run endpoint instead of direct import",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PRANASCAN_BASE_URL", "http://localhost:8000"),
        help="Service intelligence base URL for HTTP mode (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("AGENT_SECRET_KEY", ""),
        help="Agent secret key for HTTP mode (or set AGENT_SECRET_KEY env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.http:
        if not args.secret:
            log.error("--secret / AGENT_SECRET_KEY required for HTTP mode")
            sys.exit(1)
        exit_code = asyncio.run(_run_http(args.base_url, args.secret))
    else:
        exit_code = asyncio.run(_run_direct())

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
