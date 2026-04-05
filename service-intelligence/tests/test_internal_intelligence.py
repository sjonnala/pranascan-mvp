"""Tests for the internal gRPC intelligence contracts."""

from __future__ import annotations

import math

import pytest
import scan_intelligence_pb2

from app.config import settings
from app.grpc_runtime import ScanIntelligenceService


class AbortCalled(Exception):
    def __init__(self, code, details: str):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {details}")


class FakeContext:
    def __init__(self, metadata: tuple[tuple[str, str], ...] = ()):
        self._metadata = metadata

    def invocation_metadata(self):
        return tuple(_MetadataItem(key, value) for key, value in self._metadata)

    async def abort(self, code, details: str):
        raise AbortCalled(code, details)


class _MetadataItem:
    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value


GOOD_EVALUATION_REQUEST = scan_intelligence_pb2.ScanEvaluationRequest(
    scan_type=scan_intelligence_pb2.SCAN_TYPE_STANDARD,
    frame_data=[
        scan_intelligence_pb2.FrameSample(
            t_ms=float(index * (1000 / 30.0)),
            r_mean=96.0 + 1.0 * math.sin(2.0 * math.pi * 1.2 * (index / 30.0)),
            g_mean=112.0 + 2.0 * math.sin(2.0 * math.pi * 1.2 * (index / 30.0)),
            b_mean=82.0 + 0.5 * math.sin(2.0 * math.pi * 1.2 * (index / 30.0)),
        )
        for index in range(900)
    ],
    audio_samples=[0.05 if index % 2 == 0 else -0.05 for index in range(10_000)],
    quality_score=0.9,
    lighting_score=0.8,
    motion_score=0.98,
    face_confidence=0.95,
    audio_snr_db=24.0,
    frame_r_mean=104.0,
    frame_g_mean=118.0,
    frame_b_mean=92.0,
)


def _auth_context() -> FakeContext:
    return FakeContext((("x-internal-service-token", settings.internal_service_token),))


@pytest.mark.asyncio
async def test_scan_evaluation_requires_internal_token():
    service = ScanIntelligenceService()

    with pytest.raises(AbortCalled) as exc_info:
        await service.EvaluateScan(GOOD_EVALUATION_REQUEST, FakeContext())

    assert exc_info.value.details == "Invalid internal service token."


@pytest.mark.asyncio
async def test_scan_evaluation_returns_compute_only_payload():
    service = ScanIntelligenceService()

    response = await service.EvaluateScan(GOOD_EVALUATION_REQUEST, _auth_context())

    assert response.quality_gate_passed is True
    assert list(response.flags) is not None
    assert not response.HasField("rejection_reason")


@pytest.mark.asyncio
async def test_scan_evaluation_can_use_raw_media_bytes():
    service = ScanIntelligenceService()
    request = scan_intelligence_pb2.ScanEvaluationRequest(
        image_bytes=bytes((index * 13) % 256 for index in range(512)),
        quality_score=0.88,
        lighting_score=0.8,
        motion_score=0.98,
        face_confidence=0.95,
        audio_snr_db=24.0,
        frame_r_mean=104.0,
        frame_g_mean=118.0,
        frame_b_mean=92.0,
    )

    response = await service.EvaluateScan(request, _auth_context())

    assert response.HasField("hr_bpm")
    assert response.HasField("hrv_ms")
    assert response.HasField("spo2")
    assert 90.0 <= response.spo2 <= 100.0


@pytest.mark.asyncio
async def test_scan_evaluation_supports_deep_dive_contact_ppg():
    service = ScanIntelligenceService()
    heart_rate_bpm = 66.0
    beat_period_s = 60.0 / heart_rate_bpm
    request = scan_intelligence_pb2.ScanEvaluationRequest(
        scan_type=scan_intelligence_pb2.SCAN_TYPE_DEEP_DIVE,
        user_height_cm=172.0,
        frame_data=[
            scan_intelligence_pb2.FrameSample(
                t_ms=float(index * (1000 / 60.0)),
                r_mean=190.0
                + 20.0 * math.exp(
                    -0.5
                    * ((((index / 60.0) % beat_period_s) / beat_period_s - 0.16) / 0.05) ** 2
                )
                + 9.0
                * math.exp(
                    -0.5
                    * ((((index / 60.0) % beat_period_s) / beat_period_s - 0.43) / 0.07) ** 2
                ),
                g_mean=190.0
                + 20.0 * math.exp(
                    -0.5
                    * ((((index / 60.0) % beat_period_s) / beat_period_s - 0.16) / 0.05) ** 2
                )
                + 9.0
                * math.exp(
                    -0.5
                    * ((((index / 60.0) % beat_period_s) / beat_period_s - 0.43) / 0.07) ** 2
                ),
                b_mean=190.0
                + 20.0 * math.exp(
                    -0.5
                    * ((((index / 60.0) % beat_period_s) / beat_period_s - 0.16) / 0.05) ** 2
                )
                + 9.0
                * math.exp(
                    -0.5
                    * ((((index / 60.0) % beat_period_s) / beat_period_s - 0.43) / 0.07) ** 2
                ),
            )
            for index in range(60 * 30)
        ],
        quality_score=0.94,
        lighting_score=0.95,
        motion_score=0.99,
        face_confidence=0.92,
    )

    response = await service.EvaluateScan(request, _auth_context())

    assert response.quality_gate_passed is True
    assert response.HasField("hr_bpm")
    assert response.HasField("stiffness_index")
