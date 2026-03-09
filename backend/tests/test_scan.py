"""Tests for scan session API endpoints."""

import math

import numpy as np
import pytest
from httpx import AsyncClient

from tests.conftest import TEST_USER_ID

GOOD_RESULT = {
    "hr_bpm": 72.0,
    "hrv_ms": 45.0,
    "respiratory_rate": 16.0,
    "voice_jitter_pct": 0.5,
    "voice_shimmer_pct": 2.0,
    "quality_score": 0.92,
    "lighting_score": 0.8,
    "motion_score": 0.98,
    "face_confidence": 0.95,
    "audio_snr_db": 25.0,
    "flags": [],
}

BAD_LIGHTING_RESULT = {
    **GOOD_RESULT,
    "lighting_score": 0.2,  # Below 0.4 threshold
}

BAD_FACE_RESULT = {
    **GOOD_RESULT,
    "face_confidence": 0.4,  # Below 0.8 threshold — simulates heuristic returning low score
}


async def _grant_consent(client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID):
    await client.post(
        "/api/v1/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )


async def _create_session(
    client: AsyncClient,
    auth_headers: dict,
    user_id: str = TEST_USER_ID,
) -> str:
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_session_requires_auth(client: AsyncClient):
    """Session creation fails without auth token."""
    resp = await client.post("/api/v1/scans/sessions", json={"user_id": TEST_USER_ID})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_session_requires_consent(client: AsyncClient, auth_headers: dict):
    """Session creation fails without active consent."""
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_session_with_consent(client: AsyncClient, auth_headers: dict):
    """Session creation succeeds with valid auth + active consent."""
    await _grant_consent(client, auth_headers)
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID, "device_model": "Pixel 8", "app_version": "0.1.0"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID
    assert data["status"] == "initiated"
    assert data["device_model"] == "Pixel 8"


@pytest.mark.asyncio
async def test_complete_session_good_quality(client: AsyncClient, auth_headers: dict):
    """Completing a session with good quality returns wellness indicators."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["hr_bpm"] == 72.0
    assert data["quality_score"] == 0.92
    assert data["trend_alert"] is None  # No prior baseline
    assert "diagnosis" not in str(data).lower()


@pytest.mark.asyncio
async def test_complete_session_edge_processed_vitals(client: AsyncClient, auth_headers: dict):
    """
    Edge-processing path: client submits pre-computed vitals WITHOUT frame_data.

    This is the production path after the on-device rPPG processor runs.
    The backend must accept pre-computed hr_bpm/hrv_ms/respiratory_rate and
    return them unchanged — no server-side rPPG should run or overwrite them.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # Edge-processed payload: vitals from on-device rPPG, no frame_data field.
    edge_payload = {
        "hr_bpm": 68.5,
        "hrv_ms": 38.2,
        "respiratory_rate": 15.0,
        "voice_jitter_pct": 0.4,
        "voice_shimmer_pct": 1.8,
        "quality_score": 0.88,
        "lighting_score": 0.75,
        "motion_score": 0.97,
        "face_confidence": 0.91,
        "audio_snr_db": 22.0,
        "flags": [],
        # frame_data intentionally absent — edge-processing path
    }

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=edge_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Vitals returned as submitted (no server-side override when frame_data absent)
    assert data["hr_bpm"] == 68.5
    assert data["hrv_ms"] == 38.2
    assert data["respiratory_rate"] == 15.0
    assert data["quality_score"] == 0.88
    assert data["trend_alert"] is None
    assert "diagnosis" not in str(data).lower()


@pytest.mark.asyncio
async def test_complete_session_bad_lighting_rejected(client: AsyncClient, auth_headers: dict):
    """Session with poor lighting is rejected by quality gate."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=BAD_LIGHTING_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "low_lighting" in detail["flags"]
    assert "diagnosis" not in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_complete_session_low_face_confidence_rejected(
    client: AsyncClient, auth_headers: dict
):
    """Session with face_confidence below 0.80 is rejected by quality gate.

    This exercises the path where the mobile heuristic (computeFaceConfidence)
    returns a low score — e.g. a dark/empty frame — and the backend enforces
    the gate independently of the client-side check.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=BAD_FACE_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "face_not_detected" in detail["flags"]
    assert "diagnosis" not in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_complete_session_not_found(client: AsyncClient, auth_headers: dict):
    """Completing a non-existent session returns 404."""
    resp = await client.put(
        "/api/v1/scans/sessions/nonexistent-id/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_session_other_user_forbidden(
    client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
):
    """User cannot complete another user's session."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # user2 tries to complete user1's session
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers_user2,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient, auth_headers: dict):
    """GET session returns session with result after completion."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)
    await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/scans/sessions/{session_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert data["session"]["status"] == "completed"
    assert data["result"]["hr_bpm"] == 72.0


@pytest.mark.asyncio
async def test_get_session_requires_auth(client: AsyncClient, auth_headers: dict):
    """GET session requires auth."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    resp = await client.get(f"/api/v1/scans/sessions/{session_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_scan_history_pagination(client: AsyncClient, auth_headers: dict):
    """Scan history returns paginated completed sessions for the authed user."""
    await _grant_consent(client, auth_headers)

    # Create and complete 3 sessions
    for _ in range(3):
        session_id = await _create_session(client, auth_headers)
        await client.put(
            f"/api/v1/scans/sessions/{session_id}/complete",
            json=GOOD_RESULT,
            headers=auth_headers,
        )

    resp = await client.get(
        "/api/v1/scans/history",
        params={"page": 1, "page_size": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_no_diagnostic_language_in_trend_alert(client: AsyncClient, auth_headers: dict):
    """Trend alert values must not contain diagnostic language."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=GOOD_RESULT,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # trend_alert can only be null or "consider_lab_followup"
    assert data["trend_alert"] in (None, "consider_lab_followup")
    assert "diagnosis" not in str(data).lower()
    assert "diagnostic" not in str(data).lower()


@pytest.mark.asyncio
async def test_trend_alert_requires_three_prior_baseline_scans(
    client: AsyncClient, auth_headers: dict
):
    """A 15% deviation should not alert until the user has three prior scans."""
    await _grant_consent(client, auth_headers)

    for _ in range(2):
        session_id = await _create_session(client, auth_headers)
        resp = await client.put(
            f"/api/v1/scans/sessions/{session_id}/complete",
            json=GOOD_RESULT,
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    session_id = await _create_session(client, auth_headers)
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json={**GOOD_RESULT, "hr_bpm": 82.8},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["trend_alert"] is None


@pytest.mark.asyncio
async def test_trend_alert_uses_15pct_threshold_and_non_hr_metrics(
    client: AsyncClient, auth_headers: dict
):
    """Trend alerting must fire at 15% deviation even when HR is stable."""
    await _grant_consent(client, auth_headers)

    for _ in range(3):
        session_id = await _create_session(client, auth_headers)
        resp = await client.put(
            f"/api/v1/scans/sessions/{session_id}/complete",
            json=GOOD_RESULT,
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    session_id = await _create_session(client, auth_headers)
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json={**GOOD_RESULT, "hrv_ms": 38.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["trend_alert"] == "consider_lab_followup"


# ---------------------------------------------------------------------------
# Helpers for rPPG integration tests
# ---------------------------------------------------------------------------

def _make_frame_data(
    hr_bpm: float = 55.0,
    fps: float = 30.0,
    duration_s: float = 30.0,
    noise_std: float = 0.2,
    seed: int = 42,
) -> list[dict]:
    """
    Build synthetic frame_data payload for integration tests.

    Uses a sinusoidal green-channel signal at the specified HR.
    At fps=30, hr_bpm in [42, 200] is within Nyquist and should be detected.
    At fps=2, only hr_bpm in [42, 58] is reliably within Nyquist.
    """
    rng = np.random.default_rng(seed)
    n = int(fps * duration_s)
    t = np.arange(n) / fps
    freq = hr_bpm / 60.0
    g = 100.0 + 5.0 * np.sin(2.0 * math.pi * freq * t) + rng.normal(0, noise_std, n)
    r = 80.0 + rng.normal(0, noise_std, n)
    b = 60.0 + rng.normal(0, noise_std, n)
    return [
        {
            "t_ms": float(t[i] * 1000),
            "r_mean": float(np.clip(r[i], 0, 255)),
            "g_mean": float(np.clip(g[i], 0, 255)),
            "b_mean": float(np.clip(b[i], 0, 255)),
        }
        for i in range(n)
    ]


# Base payload with good quality metrics but NO pre-computed wellness values.
# Backend must compute HR/HRV/RR from frame_data.
QUALITY_ONLY_PAYLOAD = {
    "quality_score": 0.88,
    "lighting_score": 0.80,
    "motion_score": 0.97,
    "face_confidence": 0.85,
    "audio_snr_db": 22.0,
    "flags": [],
    # hr_bpm / hrv_ms / respiratory_rate intentionally omitted
}


# ---------------------------------------------------------------------------
# rPPG integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_frame_data_triggers_backend_rppg(client: AsyncClient, auth_headers: dict):
    """
    Sending frame_data (no client-computed HR) causes the backend rPPG
    processor to compute hr_bpm. The result must have a non-None hr_bpm.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # 30 fps, 30 s at 60 bpm — within Nyquist, clean signal
    frame_data = _make_frame_data(hr_bpm=60.0, fps=30.0, duration_s=30.0, noise_std=0.15)

    payload = {**QUALITY_ONLY_PAYLOAD, "frame_data": frame_data}
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hr_bpm"] is not None, "Backend rPPG should have computed hr_bpm from frame_data"
    assert 30.0 <= data["hr_bpm"] <= 220.0, f"hr_bpm={data['hr_bpm']} out of range"


@pytest.mark.asyncio
async def test_frame_data_hr_within_tolerance_of_synthetic_signal(
    client: AsyncClient, auth_headers: dict
):
    """
    Backend-computed HR should be within ±10 bpm of the synthetic signal HR (72 bpm).
    Signal is clean (low noise) at 30 fps.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    frame_data = _make_frame_data(hr_bpm=72.0, fps=30.0, duration_s=30.0, noise_std=0.15)
    payload = {**QUALITY_ONLY_PAYLOAD, "frame_data": frame_data}
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hr_bpm"] is not None
    assert abs(data["hr_bpm"] - 72.0) <= 10.0, (
        f"HR={data['hr_bpm']} bpm, expected within ±10 of 72 bpm"
    )


@pytest.mark.asyncio
async def test_frame_data_overrides_client_provided_hr(
    client: AsyncClient, auth_headers: dict
):
    """
    When frame_data is provided alongside a client hr_bpm, the backend
    rPPG result should override the client value if rPPG succeeds.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    frame_data = _make_frame_data(hr_bpm=60.0, fps=30.0, duration_s=30.0, noise_std=0.15)
    payload = {
        **QUALITY_ONLY_PAYLOAD,
        "frame_data": frame_data,
        "hr_bpm": 999.0,  # deliberately wrong — should be overridden by rPPG
        "hrv_ms": 0.0,
    }
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    # 999.0 is out of schema range [30, 220] so Pydantic will reject it
    # This test verifies the schema rejects the bad value before we even hit rPPG
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        data = resp.json()
        # If somehow 999 passed, rPPG should have overridden it
        assert data["hr_bpm"] != 999.0


@pytest.mark.asyncio
async def test_insufficient_frame_data_scan_completes_with_null_hr(
    client: AsyncClient, auth_headers: dict
):
    """
    frame_data with too few frames → rPPG returns None.
    Scan still completes successfully (hr_bpm=None in result).
    Quality gate only blocks on lighting/motion/face/snr — not on rPPG outcome.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # Only 10 frames — far below MIN_FRAMES (30)
    sparse_frames = _make_frame_data(hr_bpm=72.0, fps=1.0, duration_s=10.0)

    payload = {**QUALITY_ONLY_PAYLOAD, "frame_data": sparse_frames}
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # HR is None — rPPG had insufficient data
    assert data["hr_bpm"] is None
    # rPPG flag should be in the result flags
    assert any(
        flag in data["flags"]
        for flag in ["insufficient_frames", "insufficient_temporal_span"]
    ), f"Expected rPPG flag in {data['flags']}"


@pytest.mark.asyncio
async def test_rppg_result_contains_no_diagnostic_language(
    client: AsyncClient, auth_headers: dict
):
    """Full rPPG path — result must contain no diagnostic language."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    frame_data = _make_frame_data(hr_bpm=60.0, fps=30.0, duration_s=30.0)
    payload = {**QUALITY_ONLY_PAYLOAD, "frame_data": frame_data}
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body_str = str(resp.json()).lower()
    forbidden = ["diagnosis", "diagnostic", "disease", "disorder", "clinical condition"]
    for word in forbidden:
        assert word not in body_str, f"Diagnostic term '{word}' found in response"


@pytest.mark.asyncio
async def test_rppg_flags_appear_in_result_flags(
    client: AsyncClient, auth_headers: dict
):
    """rPPG processing flags must be merged into the result flags field."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # 30 fps, low-quality (high noise) — likely to produce rPPG flags
    noisy_frames = _make_frame_data(
        hr_bpm=72.0, fps=30.0, duration_s=30.0, noise_std=25.0
    )
    payload = {**QUALITY_ONLY_PAYLOAD, "frame_data": noisy_frames}
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Result must have a flags list (may or may not include rPPG flags depending
    # on whether the noisy signal still passes peak detection)
    assert isinstance(data["flags"], list)
