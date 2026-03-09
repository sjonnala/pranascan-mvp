"""
Latency validation tests.

These tests verify that the scan completion endpoint processes a realistic
synthetic payload (all computation: rPPG fallback, voice DSP skipped,
vascular age, anemia screening, trend engine, DB write) within the 15-second
target on CI hardware.

Note: these are integration tests against the in-memory SQLite test DB.
On production hardware (cloud VM with PostgreSQL) latency will be lower.
"""

import time

import pytest
from httpx import AsyncClient

from app.config import settings
from tests.conftest import TEST_USER_ID

API_PREFIX = "/api/v1"


async def _grant_consent(client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID):
    await client.post(
        f"{API_PREFIX}/consent",
        json={"user_id": user_id, "consent_version": "1.0", "purpose": "wellness_screening"},
        headers=auth_headers,
    )


async def _create_session(
    client: AsyncClient, auth_headers: dict, user_id: str = TEST_USER_ID
) -> str:
    resp = await client.post(
        f"{API_PREFIX}/scans/sessions",
        json={"user_id": user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_scan_complete_latency_under_target(client: AsyncClient, auth_headers: dict):
    """
    Full scan completion with a realistic synthetic payload must process
    in under settings.latency_target_ms milliseconds.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    # Realistic payload: pre-computed vitals (no frame_data, no audio_samples)
    payload = {
        "hr_bpm": 68.0,
        "hrv_ms": 42.0,
        "respiratory_rate": 15.0,
        "voice_jitter_pct": 0.8,
        "voice_shimmer_pct": 3.2,
        "quality_score": 0.82,
        "lighting_score": 0.75,
        "motion_score": 0.97,
        "face_confidence": 0.85,
        "audio_snr_db": 22.0,
        "frame_r_mean": 145.0,
        "frame_g_mean": 112.0,
        "frame_b_mean": 98.0,
        "flags": [],
    }

    start = time.perf_counter()
    resp = await client.put(
        f"{API_PREFIX}/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200, f"Unexpected status: {resp.status_code} — {resp.text}"
    assert (
        elapsed_ms < settings.latency_target_ms
    ), f"Scan processing took {elapsed_ms:.1f}ms — exceeds {settings.latency_target_ms}ms target"


@pytest.mark.asyncio
async def test_scan_response_includes_process_time_header(client: AsyncClient, auth_headers: dict):
    """
    The X-Process-Time-Ms response header must be present and numeric.
    """
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    payload = {
        "hr_bpm": 70.0,
        "hrv_ms": 38.0,
        "respiratory_rate": 14.0,
        "quality_score": 0.80,
        "lighting_score": 0.70,
        "motion_score": 0.96,
        "face_confidence": 0.82,
        "audio_snr_db": 20.0,
        "flags": [],
    }

    resp = await client.put(
        f"{API_PREFIX}/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )

    assert resp.status_code == 200
    header_val = resp.headers.get("x-process-time-ms") or resp.headers.get("X-Process-Time-Ms")
    assert header_val is not None, "X-Process-Time-Ms header missing"
    assert float(header_val) >= 0


@pytest.mark.asyncio
async def test_p95_latency_across_ten_scans(client: AsyncClient, auth_headers: dict):
    """
    Submit 10 sequential scans and check that p95 latency is under target.
    This exercises DB write path, trend engine, vascular age, and anemia screening.
    """
    await _grant_consent(client, auth_headers)
    latencies: list[float] = []

    for i in range(10):
        session_id = await _create_session(client, auth_headers)

        payload = {
            "hr_bpm": 65.0 + i,
            "hrv_ms": 40.0,
            "respiratory_rate": 15.0,
            "quality_score": 0.80,
            "lighting_score": 0.72,
            "motion_score": 0.96,
            "face_confidence": 0.83,
            "audio_snr_db": 20.0,
            "frame_r_mean": 150.0,
            "frame_g_mean": 115.0,
            "frame_b_mean": 100.0,
            "flags": [],
        }

        start = time.perf_counter()
        resp = await client.put(
            f"{API_PREFIX}/scans/sessions/{session_id}/complete",
            json=payload,
            headers=auth_headers,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        latencies.append(elapsed_ms)

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95_ms = latencies[min(p95_idx, len(latencies) - 1)]

    assert p95_ms < settings.latency_target_ms, (
        f"p95 latency {p95_ms:.1f}ms exceeds {settings.latency_target_ms}ms target. "
        f"All latencies: {[round(ms, 1) for ms in latencies]}"
    )
