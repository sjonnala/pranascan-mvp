"""gRPC server runtime for the intelligence-service compute boundary."""

from __future__ import annotations

import grpc
import scan_intelligence_pb2
import scan_intelligence_pb2_grpc

from app.config import settings
from app.schemas.scan import FrameSampleSchema, ScanResultSubmit
from app.services.scan_evaluation_service import evaluate_scan_submission
from app.services.vitals_extraction import extract_vitals_from_media

_INTERNAL_TOKEN_HEADER = "x-internal-service-token"


class ScanIntelligenceService(scan_intelligence_pb2_grpc.ScanIntelligenceServiceServicer):
    """Implements the full compute-only scan evaluation contract."""

    async def EvaluateScan(
        self,
        request: scan_intelligence_pb2.ScanEvaluationRequest,
        context: grpc.aio.ServicerContext,
    ) -> scan_intelligence_pb2.ScanEvaluationResponse:
        await _require_internal_service_token(context)

        media_bytes = None
        media_field = request.WhichOneof("media_payload")
        if media_field is not None:
            media_bytes = getattr(request, media_field)

        extracted_vitals = None
        if media_bytes:
            try:
                extracted_vitals = extract_vitals_from_media(media_bytes)
            except ValueError as exc:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        submission = _scan_result_submit_from_proto(request)
        evaluation = evaluate_scan_submission(submission, extracted_vitals=extracted_vitals)
        return _scan_evaluation_response_from_domain(evaluation)


async def _require_internal_service_token(context: grpc.aio.ServicerContext) -> None:
    metadata = {item.key: item.value for item in context.invocation_metadata()}
    if metadata.get(_INTERNAL_TOKEN_HEADER) != settings.internal_service_token:
        await context.abort(
            grpc.StatusCode.UNAUTHENTICATED,
            "Invalid internal service token.",
        )


def _scan_result_submit_from_proto(
    request: scan_intelligence_pb2.ScanEvaluationRequest,
) -> ScanResultSubmit:
    return ScanResultSubmit(
        frame_data=[
            FrameSampleSchema(
                t_ms=frame.t_ms,
                r_mean=frame.r_mean,
                g_mean=frame.g_mean,
                b_mean=frame.b_mean,
            )
            for frame in request.frame_data
        ]
        or None,
        audio_samples=list(request.audio_samples) or None,
        hr_bpm=_optional_double(request, "hr_bpm"),
        hrv_ms=_optional_double(request, "hrv_ms"),
        respiratory_rate=_optional_double(request, "respiratory_rate"),
        voice_jitter_pct=_optional_double(request, "voice_jitter_pct"),
        voice_shimmer_pct=_optional_double(request, "voice_shimmer_pct"),
        quality_score=request.quality_score,
        lighting_score=_optional_double(request, "lighting_score"),
        motion_score=_optional_double(request, "motion_score"),
        face_confidence=_optional_double(request, "face_confidence"),
        audio_snr_db=_optional_double(request, "audio_snr_db"),
        flags=list(request.flags),
        frame_r_mean=_optional_double(request, "frame_r_mean"),
        frame_g_mean=_optional_double(request, "frame_g_mean"),
        frame_b_mean=_optional_double(request, "frame_b_mean"),
    )


def _scan_evaluation_response_from_domain(
    evaluation,
) -> scan_intelligence_pb2.ScanEvaluationResponse:
    response = scan_intelligence_pb2.ScanEvaluationResponse(
        quality_score=evaluation.submission.quality_score,
        flags=evaluation.flags,
        warnings=evaluation.warnings,
        quality_gate_passed=evaluation.quality_gate_passed,
    )

    _set_optional_double(response, "hr_bpm", evaluation.submission.hr_bpm)
    _set_optional_double(response, "hrv_ms", evaluation.submission.hrv_ms)
    _set_optional_double(response, "spo2", evaluation.spo2)
    _set_optional_double(response, "respiratory_rate", evaluation.submission.respiratory_rate)
    _set_optional_double(response, "voice_jitter_pct", evaluation.submission.voice_jitter_pct)
    _set_optional_double(response, "voice_shimmer_pct", evaluation.submission.voice_shimmer_pct)
    _set_optional_double(response, "lighting_score", evaluation.submission.lighting_score)
    _set_optional_double(response, "motion_score", evaluation.submission.motion_score)
    _set_optional_double(response, "face_confidence", evaluation.submission.face_confidence)
    _set_optional_double(response, "audio_snr_db", evaluation.submission.audio_snr_db)
    _set_optional_double(response, "vascular_age_estimate", evaluation.vascular_age_estimate)
    _set_optional_double(response, "vascular_age_confidence", evaluation.vascular_age_confidence)
    _set_optional_double(response, "hb_proxy_score", evaluation.hb_proxy_score)
    _set_optional_double(response, "anemia_confidence", evaluation.anemia_confidence)
    _set_optional_string(response, "rejection_reason", evaluation.rejection_reason)
    _set_optional_string(response, "anemia_wellness_label", evaluation.anemia_wellness_label)

    return response


def _optional_double(message, field_name: str) -> float | None:
    return getattr(message, field_name) if message.HasField(field_name) else None


def _set_optional_double(message, field_name: str, value: float | None) -> None:
    if value is None:
        return
    setattr(message, field_name, value)


def _set_optional_string(message, field_name: str, value: str | None) -> None:
    if value is None:
        return
    setattr(message, field_name, value)


def build_grpc_bind_address(host: str | None = None, port: int | None = None) -> str:
    """Build the gRPC bind address from settings or explicit overrides."""
    grpc_host = host if host is not None else settings.grpc_host
    grpc_port = port if port is not None else settings.grpc_port
    return f"{grpc_host}:{grpc_port}"


async def start_grpc_server(bind_address: str | None = None) -> grpc.aio.Server:
    """Start the async gRPC server for the intelligence contracts."""
    server = grpc.aio.server(options=[("grpc.so_reuseport", 0)])
    scan_intelligence_pb2_grpc.add_ScanIntelligenceServiceServicer_to_server(
        ScanIntelligenceService(),
        server,
    )

    bound_port = server.add_insecure_port(bind_address or build_grpc_bind_address())
    if bound_port == 0:
        raise RuntimeError("Failed to bind gRPC server to the configured address.")

    await server.start()
    return server


async def stop_grpc_server(server: grpc.aio.Server | None) -> None:
    """Stop the async gRPC server if it is running."""
    if server is None:
        return
    await server.stop(grace=5)
