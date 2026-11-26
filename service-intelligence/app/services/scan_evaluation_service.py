"""Compute-only scan evaluation service for internal service-to-service calls."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.scan import ScanResultSubmit, ScanType
from app.services.anemia_screen import AnemiaScreenResult, anemia_not_applicable, screen_anemia
from app.services.morphology_processor import process_morphology_frames
from app.services.quality_gate import run_quality_gate
from app.services.rppg_processor import RppgResult, build_frame_samples, process_frames
from app.services.skin_tone import apply_skin_tone_calibration
from app.services.vascular_age import estimate_vascular_age
from app.services.vitals_extraction import ExtractedVitals
from app.services.voice_processor import build_audio_samples, process_audio


@dataclass(frozen=True)
class ScanEvaluation:
    submission: ScanResultSubmit
    spo2: float | None
    stiffness_index: float | None
    flags: list[str]
    warnings: list[str]
    quality_gate_passed: bool
    rejection_reason: str | None
    vascular_age_estimate: float | None
    vascular_age_confidence: float | None
    hb_proxy_score: float | None
    anemia_wellness_label: str | None
    anemia_confidence: float | None
    # Phase 0: both quality signals are surfaced separately; neither hides the
    # other. ``submission.quality_score`` carries the spectral score whenever
    # server-side rPPG reached spectral analysis.
    mobile_quality_score: float = 0.0
    spectral_quality_score: float | None = None
    spectral_snr_db: float | None = None
    effective_fps: float | None = None
    hr_abstained: bool = False
    hr_abstention_reason: str | None = None
    anemia_applicable: bool = False
    anemia_not_applicable_reason: str | None = None


# Signal-failure flags that, once frame_data was provided, mean the server saw
# no usable pulse. They are treated as abstentions so a client-reported value
# can never stand in for a trace the server could not read.
_SIGNAL_FAILURE_ABSTENTION_FLAGS = ("flat_signal", "insufficient_peaks")


@dataclass(frozen=True)
class _RppgOutcome:
    submission: ScanResultSubmit
    flags: list[str]
    stiffness_index: float | None
    rppg: RppgResult | None = None
    hr_abstained: bool = False
    abstention_reason: str | None = None


def evaluate_scan_submission(
    submission: ScanResultSubmit,
    extracted_vitals: ExtractedVitals | None = None,
) -> ScanEvaluation:
    """Apply deterministic scan processing without persistence or user-state concerns."""
    mobile_quality_score = submission.quality_score
    outcome = _apply_server_side_rppg(submission)
    processed_submission = outcome.submission
    rppg = outcome.rppg
    hr_abstained = outcome.hr_abstained

    processed_submission = _apply_server_side_voice_dsp(processed_submission)
    if not hr_abstained:
        processed_submission, spo2 = _apply_extracted_vitals(processed_submission, extracted_vitals)
    else:
        # Respect the abstention: do not backfill HR/HRV from another source.
        spo2 = extracted_vitals.spo2 if extracted_vitals is not None else None

    gate = run_quality_gate(processed_submission)

    spectral_quality_score = None
    spectral_snr_db = None
    if rppg is not None and rppg.snr_db is not None:
        spectral_quality_score = rppg.quality_score
        spectral_snr_db = rppg.snr_db

    quality_flags = [f"mobile_quality_score:{mobile_quality_score:.4f}"]
    if spectral_quality_score is not None:
        quality_flags.append(f"spectral_quality_score:{spectral_quality_score:.4f}")
        quality_flags.append(f"spectral_snr_db:{spectral_snr_db:.2f}")

    vascular_age = estimate_vascular_age(
        processed_submission.hr_bpm,
        processed_submission.hrv_ms,
    )
    anemia: AnemiaScreenResult | None = None
    if submission.scan_type == ScanType.STANDARD:
        anemia = _screen_anemia_if_applicable(processed_submission)

    anemia_flags = anemia.flags if anemia is not None and not anemia.applicable else []
    combined_flags = list(dict.fromkeys(gate.flags + outcome.flags + quality_flags + anemia_flags))

    return ScanEvaluation(
        submission=processed_submission,
        spo2=spo2,
        stiffness_index=outcome.stiffness_index,
        flags=combined_flags,
        warnings=gate.warnings,
        quality_gate_passed=gate.passed,
        rejection_reason=gate.rejection_reason,
        vascular_age_estimate=vascular_age.estimate_years,
        vascular_age_confidence=vascular_age.confidence,
        hb_proxy_score=anemia.hb_proxy_score if anemia is not None else None,
        anemia_wellness_label=anemia.wellness_label if anemia is not None else None,
        anemia_confidence=(anemia.confidence if anemia is not None and anemia.applicable else None),
        mobile_quality_score=mobile_quality_score,
        spectral_quality_score=spectral_quality_score,
        spectral_snr_db=spectral_snr_db,
        effective_fps=rppg.effective_fps if rppg is not None else None,
        hr_abstained=hr_abstained,
        hr_abstention_reason=outcome.abstention_reason,
        anemia_applicable=bool(anemia is not None and anemia.applicable),
        anemia_not_applicable_reason=(anemia.not_applicable_reason if anemia is not None else None),
    )


def _screen_anemia_if_applicable(submission: ScanResultSubmit) -> AnemiaScreenResult:
    """Run the conjunctival colour heuristic only on explicit conjunctival ROI input.

    Standard facial scans carry face-centre ROI means (``frame_*_mean``), which
    are not a valid input for the heuristic, so they are marked not applicable.
    """
    conjunctival = (
        submission.conjunctival_r_mean,
        submission.conjunctival_g_mean,
        submission.conjunctival_b_mean,
    )
    if any(channel is None for channel in conjunctival):
        return anemia_not_applicable()

    return screen_anemia(
        r_mean=submission.conjunctival_r_mean,
        g_mean=submission.conjunctival_g_mean,
        b_mean=submission.conjunctival_b_mean,
        lighting_score=submission.lighting_score,
        motion_score=submission.motion_score,
    )


def _apply_server_side_rppg(submission: ScanResultSubmit) -> _RppgOutcome:
    if not submission.frame_data:
        return _RppgOutcome(submission=submission, flags=[], stiffness_index=None)

    frames = build_frame_samples([frame.model_dump() for frame in submission.frame_data])
    if submission.scan_type == ScanType.DEEP_DIVE:
        # Contact-PPG morphology path: out of Phase 0 scope, behaviour unchanged.
        morphology = process_morphology_frames(frames, submission.user_height_cm)
        if morphology.hr_bpm is None:
            failure_reason = _signal_failure_reason(morphology.flags)
            if failure_reason is not None:
                return _abstain_on_signal_failure(
                    submission,
                    morphology.flags,
                    failure_reason,
                    stiffness_index=morphology.stiffness_index,
                )
            return _RppgOutcome(submission, morphology.flags, morphology.stiffness_index)

        return _RppgOutcome(
            submission.model_copy(
                update={
                    "hr_bpm": morphology.hr_bpm,
                    "hrv_ms": morphology.hrv_ms,
                    "quality_score": max(submission.quality_score, morphology.quality_score),
                }
            ),
            morphology.flags,
            morphology.stiffness_index,
        )

    rppg = process_frames(frames)
    rppg, _skin_tone_metadata = apply_skin_tone_calibration(rppg, frames)

    failure_reason = _signal_failure_reason(rppg.flags) if rppg.hr_bpm is None else None
    if failure_reason is not None:
        # A flat trace or one with too few peaks: the server saw frames but no
        # pulse, so no client or extracted value may fill the gap. The spectral
        # score is reported when spectral analysis ran.
        return _abstain_on_signal_failure(
            submission,
            rppg.flags,
            failure_reason,
            rppg=rppg,
            quality_score=rppg.quality_score if rppg.snr_db is not None else None,
        )

    if rppg.snr_db is None:
        # The trace never reached spectral analysis (too short, corrupt
        # timestamps). Nothing to override; keep the submission as received.
        return _RppgOutcome(submission, rppg.flags, None, rppg)

    if rppg.abstained:
        # "No pulse": the server's spectral evidence is authoritative, so the
        # scan reports no HR/HRV/respiration rather than any client value.
        return _RppgOutcome(
            submission.model_copy(
                update={
                    "hr_bpm": None,
                    "hrv_ms": None,
                    "respiratory_rate": None,
                    "quality_score": rppg.quality_score,
                }
            ),
            rppg.flags,
            None,
            rppg,
            hr_abstained=True,
            abstention_reason=rppg.abstention_reason,
        )

    if rppg.hr_bpm is None:
        # Spectral analysis ran but produced no HR for another reason: keep the
        # previous behaviour for HR fields, but report the honest spectral quality.
        return _RppgOutcome(
            submission.model_copy(update={"quality_score": rppg.quality_score}),
            rppg.flags,
            None,
            rppg,
        )

    return _RppgOutcome(
        submission.model_copy(
            update={
                "hr_bpm": rppg.hr_bpm,
                # None when withheld (hrv_withheld_low_fps): never keep a client value.
                "hrv_ms": rppg.hrv_ms,
                "respiratory_rate": rppg.respiratory_rate,
                # No max(mobile, spectral): the spectral score is reported as-is
                # and the mobile heuristic is surfaced separately.
                "quality_score": rppg.quality_score,
            }
        ),
        rppg.flags,
        None,
        rppg,
    )


def _signal_failure_reason(flags: list[str]) -> str | None:
    for reason in _SIGNAL_FAILURE_ABSTENTION_FLAGS:
        if reason in flags:
            return reason
    return None


def _abstain_on_signal_failure(
    submission: ScanResultSubmit,
    flags: list[str],
    reason: str,
    *,
    stiffness_index: float | None = None,
    rppg: RppgResult | None = None,
    quality_score: float | None = None,
) -> _RppgOutcome:
    """Clear HR, HRV and respiration and mark the scan as an abstention."""
    update: dict[str, float | None] = {
        "hr_bpm": None,
        "hrv_ms": None,
        "respiratory_rate": None,
    }
    if quality_score is not None:
        update["quality_score"] = quality_score
    abstention_flags = ["hr_abstained", "no_reliable_pulse", f"abstain_reason:{reason}"]
    return _RppgOutcome(
        submission.model_copy(update=update),
        list(dict.fromkeys([*flags, *abstention_flags])),
        stiffness_index,
        rppg,
        hr_abstained=True,
        abstention_reason=reason,
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
            "hr_bpm": (
                submission.hr_bpm if submission.hr_bpm is not None else extracted_vitals.heart_rate
            ),
            "hrv_ms": submission.hrv_ms if submission.hrv_ms is not None else extracted_vitals.hrv,
        }
    )
    return updated_submission, extracted_vitals.spo2
