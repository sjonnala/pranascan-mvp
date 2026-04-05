"""Compute-only scan evaluation service for internal service-to-service calls."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.scan import ScanResultSubmit
from app.services.anemia_screen import screen_anemia
from app.services.quality_gate import run_quality_gate
from app.services.rppg_processor import build_frame_samples, process_frames
from app.services.skin_tone import apply_skin_tone_calibration
from app.services.vascular_age import estimate_vascular_age
from app.services.vitals_extraction import ExtractedVitals
from app.services.voice_processor import build_audio_samples, process_audio


@dataclass(frozen=True)
class ScanEvaluation:
    submission: ScanResultSubmit
    spo2: float | None
    flags: list[str]
    warnings: list[str]
    quality_gate_passed: bool
    rejection_reason: str | None
    vascular_age_estimate: float | None
    vascular_age_confidence: float | None
    hb_proxy_score: float | None
    anemia_wellness_label: str | None
    anemia_confidence: float | None


def evaluate_scan_submission(
    submission: ScanResultSubmit,
    extracted_vitals: ExtractedVitals | None = None,
) -> ScanEvaluation:
    """Apply deterministic scan processing without persistence or user-state concerns."""
    processed_submission, rppg_flags = _apply_server_side_rppg(submission)
    processed_submission = _apply_server_side_voice_dsp(processed_submission)
    processed_submission, spo2 = _apply_extracted_vitals(processed_submission, extracted_vitals)

    gate = run_quality_gate(processed_submission)
    combined_flags = list(dict.fromkeys(gate.flags + rppg_flags))

    vascular_age = estimate_vascular_age(
        processed_submission.hr_bpm,
        processed_submission.hrv_ms,
    )
    anemia = screen_anemia(
        r_mean=processed_submission.frame_r_mean,
        g_mean=processed_submission.frame_g_mean,
        b_mean=processed_submission.frame_b_mean,
        lighting_score=processed_submission.lighting_score,
        motion_score=processed_submission.motion_score,
    )

    return ScanEvaluation(
        submission=processed_submission,
        spo2=spo2,
        flags=combined_flags,
        warnings=gate.warnings,
        quality_gate_passed=gate.passed,
        rejection_reason=gate.rejection_reason,
        vascular_age_estimate=vascular_age.estimate_years,
        vascular_age_confidence=vascular_age.confidence,
        hb_proxy_score=anemia.hb_proxy_score,
        anemia_wellness_label=anemia.wellness_label,
        anemia_confidence=anemia.confidence,
    )


def _apply_server_side_rppg(submission: ScanResultSubmit) -> tuple[ScanResultSubmit, list[str]]:
    rppg_flags: list[str] = []
    if not submission.frame_data:
        return submission, rppg_flags

    frames = build_frame_samples([frame.model_dump() for frame in submission.frame_data])
    rppg = process_frames(frames)
    rppg, _skin_calibration = apply_skin_tone_calibration(rppg, frames)
    rppg_flags = rppg.flags

    if rppg.hr_bpm is None:
        return submission, rppg_flags

    return (
        submission.model_copy(
            update={
                "hr_bpm": rppg.hr_bpm,
                "hrv_ms": rppg.hrv_ms,
                "respiratory_rate": rppg.respiratory_rate,
                "quality_score": max(submission.quality_score, rppg.quality_score),
            }
        ),
        rppg_flags,
    )


def _apply_server_side_voice_dsp(submission: ScanResultSubmit) -> ScanResultSubmit:
    if not submission.audio_samples:
        return submission

    audio = build_audio_samples(submission.audio_samples)
    voice = process_audio(audio)
    if voice.jitter_pct is None:
        return submission

    return submission.model_copy(
        update={
            "voice_jitter_pct": voice.jitter_pct,
            "voice_shimmer_pct": voice.shimmer_pct,
            "audio_snr_db": voice.snr_db if voice.snr_db is not None else submission.audio_snr_db,
        }
    )


def _apply_extracted_vitals(
    submission: ScanResultSubmit,
    extracted_vitals: ExtractedVitals | None,
) -> tuple[ScanResultSubmit, float | None]:
    if extracted_vitals is None:
        return submission, None

    updated_submission = submission.model_copy(
        update={
            "hr_bpm": submission.hr_bpm if submission.hr_bpm is not None else extracted_vitals.heart_rate,
            "hrv_ms": submission.hrv_ms if submission.hrv_ms is not None else extracted_vitals.hrv,
        }
    )
    return updated_submission, extracted_vitals.spo2
