"""Tests for the anemia screening wellness indicator service (D12).

Wellness screening indicator only. Not a diagnostic tool.
Results must not use diagnostic language.
"""

import pytest
from httpx import AsyncClient

from app.services.anemia_screen import screen_anemia
from tests.conftest import TEST_USER_ID

# ── Unit tests ────────────────────────────────────────────────────────────────


def test_returns_null_when_no_color_data():
    """All-None RGB inputs → hb_proxy_score None, flag insufficient_color_data."""
    result = screen_anemia(
        r_mean=None,
        g_mean=None,
        b_mean=None,
        lighting_score=0.8,
        motion_score=1.0,
    )
    assert result.hb_proxy_score is None
    assert "insufficient_color_data" in result.flags


def test_healthy_high_red_maps_to_high_score():
    """Well-vascularised proxy: high R → hb_proxy_score >= 0.6, label normal_range."""
    result = screen_anemia(
        r_mean=180,
        g_mean=120,
        b_mean=100,
        lighting_score=0.8,
        motion_score=1.0,
    )
    assert result.hb_proxy_score is not None
    assert result.hb_proxy_score >= 0.6
    assert result.wellness_label == "normal_range"


def test_pale_low_red_maps_to_low_score():
    """Low-red proxy: hb_proxy_score <= 0.4."""
    result = screen_anemia(
        r_mean=100,
        g_mean=130,
        b_mean=120,
        lighting_score=0.8,
        motion_score=1.0,
    )
    assert result.hb_proxy_score is not None
    assert result.hb_proxy_score <= 0.4


def test_low_lighting_gates_result():
    """Low confidence → hb_proxy_score None, low_confidence_environment flag.

    confidence = lighting*0.7 + motion*0.3
    With lighting=0.3, motion=0.4: confidence = 0.21 + 0.12 = 0.33 < 0.5 → gated.
    """
    result = screen_anemia(
        r_mean=160,
        g_mean=110,
        b_mean=100,
        lighting_score=0.3,
        motion_score=0.4,
    )
    assert result.hb_proxy_score is None
    assert "low_confidence_environment" in result.flags


def test_confidence_score_formula():
    """Confidence = lighting*0.7 + motion*0.3."""
    result = screen_anemia(
        r_mean=160,
        g_mean=110,
        b_mean=100,
        lighting_score=0.8,
        motion_score=1.0,
    )
    expected = round(0.8 * 0.7 + 1.0 * 0.3, 10)
    assert abs(result.confidence - expected) < 1e-9


def test_hb_proxy_score_bounded_0_to_1():
    """For any valid RGB with good lighting, hb_proxy_score is in [0, 1]."""
    test_cases = [
        (255, 0, 0),  # pure red → max score
        (0, 255, 255),  # zero red → min score
        (128, 128, 128),
        (180, 90, 90),
    ]
    for r, g, b in test_cases:
        result = screen_anemia(
            r_mean=r,
            g_mean=g,
            b_mean=b,
            lighting_score=0.9,
            motion_score=1.0,
        )
        assert result.hb_proxy_score is not None
        assert 0.0 <= result.hb_proxy_score <= 1.0, f"Out of bounds for r={r}, g={g}, b={b}"


def test_consider_followup_label_for_very_pale():
    """Very pale proxy (low r_fraction) → label consider_followup."""
    result = screen_anemia(
        r_mean=80,
        g_mean=140,
        b_mean=130,
        lighting_score=0.9,
        motion_score=1.0,
    )
    assert result.wellness_label == "consider_followup"


def test_no_diagnostic_language_in_labels():
    """Wellness label values must not contain diagnostic terminology."""
    forbidden = ["diagnos", "disease", "disorder", "anemia", "condition"]
    all_labels = ["normal_range", "below_typical_range", "consider_followup"]
    for label in all_labels:
        lower = label.lower()
        for word in forbidden:
            assert (
                word not in lower
            ), f"Diagnostic language '{word}' found in wellness label '{label}'"


def test_borderline_confidence_flag():
    """Confidence in [0.5, 0.7) → borderline_confidence flag, score still returned."""
    # confidence = 0.6 * 0.7 + 0.4 * 0.3 = 0.42 + 0.12 = 0.54
    result = screen_anemia(
        r_mean=160,
        g_mean=110,
        b_mean=100,
        lighting_score=0.6,
        motion_score=0.4,
    )
    assert result.hb_proxy_score is not None
    assert "borderline_confidence" in result.flags


def test_clamps_out_of_range_channels():
    """Out-of-range RGB values are clamped to [0, 255]."""
    # r=300 → clamped to 255, should behave like pure-red fraction
    result = screen_anemia(
        r_mean=300,
        g_mean=-10,
        b_mean=0,
        lighting_score=0.9,
        motion_score=1.0,
    )
    assert result.hb_proxy_score is not None
    assert result.hb_proxy_score == 1.0


def test_rgb_total_zero_returns_insufficient():
    """rgb_total < 1 → insufficient_color_data."""
    result = screen_anemia(
        r_mean=0,
        g_mean=0,
        b_mean=0,
        lighting_score=0.9,
        motion_score=1.0,
    )
    assert result.hb_proxy_score is None
    assert "insufficient_color_data" in result.flags


# ── Integration test ──────────────────────────────────────────────────────────

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


async def _grant_consent(client: AsyncClient, auth_headers: dict) -> None:
    await client.post(
        "/api/v1/consent",
        json={
            "user_id": TEST_USER_ID,
            "consent_version": "1.0",
            "purpose": "wellness_screening",
        },
        headers=auth_headers,
    )


async def _create_session(client: AsyncClient, auth_headers: dict) -> str:
    resp = await client.post(
        "/api/v1/scans/sessions",
        json={"user_id": TEST_USER_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_scan_result_includes_anemia_fields(client: AsyncClient, auth_headers: dict):
    """Integration: submitting frame_r/g/b_mean returns hb_proxy_score and anemia_wellness_label."""
    await _grant_consent(client, auth_headers)
    session_id = await _create_session(client, auth_headers)

    payload = {
        **GOOD_RESULT,
        "frame_r_mean": 160.0,
        "frame_g_mean": 115.0,
        "frame_b_mean": 100.0,
    }
    resp = await client.put(
        f"/api/v1/scans/sessions/{session_id}/complete",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "hb_proxy_score" in data
    assert data["hb_proxy_score"] is not None
    assert 0.0 <= data["hb_proxy_score"] <= 1.0

    assert "anemia_wellness_label" in data
    assert data["anemia_wellness_label"] in (
        "normal_range",
        "below_typical_range",
        "consider_followup",
    )

    assert "anemia_confidence" in data
    assert data["anemia_confidence"] is not None
