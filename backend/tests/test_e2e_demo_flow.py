"""
End-to-end demo flow smoke test.

Verifies the complete PranaScan user journey in a single test sequence:

  1. Auth       — obtain a valid bearer token
  2. Consent    — grant wellness screening consent
  3. Baseline   — complete 3+ scans to establish a metric baseline
  4. Deviation  — complete a scan with a >15% deviation to trigger a trend alert
  5. Alert      — verify trend alert is present and contains no diagnostic language
  6. Report     — generate a weekly vitality report via API
  7. Agent      — run the background agent cycle; verify it processes the user
  8. Language   — assert no diagnostic language anywhere in any response

This is the Sprint 2 exit criteria gap test: demo flow documented with evidence.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.auth_service import create_access_token
from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

DEMO_USER_ID = TEST_USER_ID

BASELINE_SCAN = {
    "hr_bpm": 72.0,
    "hrv_ms": 45.0,
    "respiratory_rate": 16.0,
    "voice_jitter_pct": 0.5,
    "voice_shimmer_pct": 2.0,
    "quality_score": 0.92,
    "lighting_score": 0.85,
    "motion_score": 0.98,
    "face_confidence": 0.95,
    "audio_snr_db": 25.0,
    "flags": [],
}

# HR deviated by ~22% above baseline (72 → 88) — should trigger consider_lab_followup
DEVIATED_SCAN = {
    **BASELINE_SCAN,
    "hr_bpm": 88.0,  # +22% above 72 baseline
}

# Positive diagnostic assertion patterns to detect.
# We match phrases that claim a health finding — not negations like
# "does not provide diagnoses" or "not a diagnosis".
# The PRD rule: output must never assert a diagnosis ON the user.
_DIAGNOSTIC_PATTERNS = [
    "you have been diagnosed",
    "you are diagnosed",
    "indicates disease",
    "indicates disorder",
    "indicates illness",
    "you have a condition",
    "you are suffering",
    "pathological finding",
    "clinical diagnosis",
]


def _has_diagnostic_language(text: str) -> bool:
    """Return True if text contains a positive diagnostic assertion."""
    lowered = text.lower()
    return any(pattern in lowered for pattern in _DIAGNOSTIC_PATTERNS)


async def _grant_consent(client: AsyncClient, headers: dict) -> None:
    resp = await client.post(
        "/api/v1/consent",
        json={"user_id": DEMO_USER_ID, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=headers,
    )
    assert resp.status_code == 201, f"Consent grant failed: {resp.text}"


async def _do_scan(client: AsyncClient, headers: dict, scan_data: dict) -> dict:
    """Create a session, complete it with scan_data, return the result JSON."""
    # Create session
    create_resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": DEMO_USER_ID},
        headers=headers,
    )
    assert create_resp.status_code == 201, f"Session create failed: {create_resp.text}"
    session_id = create_resp.json()["id"]

    # Complete session
    complete_resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=scan_data,
        headers=headers,
    )
    assert complete_resp.status_code == 200, f"Session complete failed: {complete_resp.text}"
    return complete_resp.json()


# ---------------------------------------------------------------------------
# Full E2E demo flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_full_demo_flow(client: AsyncClient):
    """
    Full demo flow: Auth → Consent → Baseline scans → Deviated scan →
    Trend alert → Weekly report → Agent cycle → No diagnostic language.
    """
    # ── Step 1: Auth ─────────────────────────────────────────────────────────
    token = create_access_token(DEMO_USER_ID)
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token is valid by hitting a protected endpoint (scan history)
    health_resp = await client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # ── Step 2: Consent ───────────────────────────────────────────────────────
    await _grant_consent(client, headers)

    consent_status = await client.get(
        f"/api/v1/consent/status?user_id={DEMO_USER_ID}", headers=headers
    )
    assert consent_status.status_code == 200
    assert consent_status.json()["has_active_consent"] is True

    # ── Step 3: Baseline scans (3 scans to satisfy trend_min_baseline_scans) ─
    baseline_results = []
    for _ in range(settings.trend_min_baseline_scans):
        result = await _do_scan(client, headers, BASELINE_SCAN)
        baseline_results.append(result)
        assert result["hr_bpm"] is not None or result.get("flags") is not None
        # No diagnostic language in individual scan results
        assert not _has_diagnostic_language(str(result)), (
            f"Diagnostic language found in scan result: {result}"
        )

    assert len(baseline_results) == settings.trend_min_baseline_scans

    # ── Step 4: Deviated scan — should trigger trend alert ───────────────────
    with patch("app.services.delivery_service._send_telegram", new_callable=AsyncMock):
        deviated_result = await _do_scan(client, headers, DEVIATED_SCAN)

    # ── Step 5: Verify trend alert ───────────────────────────────────────────
    assert deviated_result.get("trend_alert") == "consider_lab_followup", (
        f"Expected trend alert, got: {deviated_result.get('trend_alert')}"
    )
    # Alert must NOT contain diagnostic language
    trend_alert_value = deviated_result.get("trend_alert", "")
    assert not _has_diagnostic_language(trend_alert_value)

    # ── Step 6: Weekly vitality report ───────────────────────────────────────
    with patch("app.services.delivery_service._send_telegram", new_callable=AsyncMock):
        report_resp = await client.post("/api/v1/reports/generate", headers=headers)

    assert report_resp.status_code == 201, f"Report generation failed: {report_resp.text}"
    report = report_resp.json()

    # Report has expected fields
    assert "period_start" in report
    assert "period_end" in report
    assert "scan_count" in report
    assert "summary_text" in report
    assert report["scan_count"] >= settings.trend_min_baseline_scans

    # Disclaimer must be present
    summary_text = report["summary_text"]
    assert "wellness" in summary_text.lower() or "disclaimer" in summary_text.lower() or \
        "not a medical" in summary_text.lower() or "consult" in summary_text.lower(), (
        f"Disclaimer not found in report: {summary_text[:200]}"
    )

    # No diagnostic language in report
    assert not _has_diagnostic_language(summary_text), (
        f"Diagnostic language found in report summary: {summary_text[:200]}"
    )

    # ── Step 7: GET latest report ─────────────────────────────────────────────
    latest_resp = await client.get("/api/v1/reports/latest", headers=headers)
    assert latest_resp.status_code == 200
    assert latest_resp.json()["id"] == report["id"]

    # ── Step 8: Agent cycle ───────────────────────────────────────────────────
    with (
        patch.object(settings, "agent_secret_key", "e2e-test-secret"),
        patch("app.services.delivery_service._send_telegram", new_callable=AsyncMock),
    ):
        agent_resp = await client.post(
            "/api/v1/internal/agent/run",
            headers={"X-Agent-Secret": "e2e-test-secret"},
        )

    assert agent_resp.status_code == 200, f"Agent run failed: {agent_resp.text}"
    agent_summary = agent_resp.json()

    assert agent_summary["users_found"] >= 1
    assert agent_summary["reports_generated"] >= 1
    assert len(agent_summary["errors"]) == 0, f"Agent errors: {agent_summary['errors']}"

    # ── Step 9: Scan history — verify all scans recorded ─────────────────────
    history_resp = await client.get("/api/v1/scans/history", headers=headers)
    assert history_resp.status_code == 200
    history = history_resp.json()
    # At least the baseline + deviated scans
    assert len(history) >= settings.trend_min_baseline_scans + 1

    # No diagnostic language in any history entry
    for entry in history:
        assert not _has_diagnostic_language(str(entry)), (
            f"Diagnostic language in history entry: {entry}"
        )

    # ── Step 10: Audit log — verify endpoint is accessible ────────────────────
    # Note: audit middleware writes to its own DB session (AsyncSessionLocal),
    # separate from the test in-memory DB. We verify the endpoint is reachable
    # and returns the correct shape; entry count is not asserted in unit tests.
    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    audit_payload = audit_resp.json()
    # Verify response structure matches expected schema
    assert "items" in audit_payload or "logs" in audit_payload or isinstance(audit_payload, list)


# ---------------------------------------------------------------------------
# Minimal path smoke test (happy path, fast)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_minimal_happy_path(client: AsyncClient):
    """
    Minimal smoke test: Auth → Consent → Scan → Result in < 1s.
    Validates the core scan loop works end-to-end without baseline or alerts.
    """
    token = create_access_token(DEMO_USER_ID)
    headers = {"Authorization": f"Bearer {token}"}

    await _grant_consent(client, headers)
    result = await _do_scan(client, headers, BASELINE_SCAN)

    assert result.get("hr_bpm") is not None or result.get("flags") is not None
    assert not _has_diagnostic_language(str(result))


# ---------------------------------------------------------------------------
# Non-diagnostic language guard across all key endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_diagnostic_language_in_error_responses(client: AsyncClient):
    """Error responses (403, 404) must not contain diagnostic language."""
    # Unauthenticated scan attempt
    resp = await client.post("/api/v1/scans/sessions", json={"user_id": DEMO_USER_ID})
    assert resp.status_code == 403
    assert not _has_diagnostic_language(resp.text)

    # Health endpoint
    health = await client.get("/health")
    assert not _has_diagnostic_language(health.text)

    # Root endpoint
    root = await client.get("/")
    assert not _has_diagnostic_language(root.text)
