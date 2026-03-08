"""Quality gate service — validates scan quality before accepting results."""

from dataclasses import dataclass

from app.config import settings
from app.schemas.scan import ScanResultSubmit


@dataclass
class QualityGateResult:
    passed: bool
    flags: list[str]
    rejection_reason: str | None = None


def run_quality_gate(payload: ScanResultSubmit) -> QualityGateResult:
    """
    Validate scan quality metrics against configured thresholds.

    Returns a QualityGateResult indicating whether the scan passes
    and which quality flags were raised.

    Thresholds (from config):
        lighting_score  > 0.4
        motion_score    > 0.95
        face_confidence > 0.8
        audio_snr_db    > 15.0
    """
    flags: list[str] = list(payload.flags)
    failures: list[str] = []

    if payload.lighting_score is not None and payload.lighting_score <= settings.min_lighting_score:
        flags.append("low_lighting")
        failures.append(
            f"Lighting score {payload.lighting_score:.2f} below threshold {settings.min_lighting_score}"
        )

    if payload.motion_score is not None and payload.motion_score < settings.min_motion_score:
        flags.append("motion_detected")
        failures.append(
            f"Motion score {payload.motion_score:.2f} below threshold {settings.min_motion_score}"
        )

    if (
        payload.face_confidence is not None
        and payload.face_confidence <= settings.min_face_confidence
    ):
        flags.append("face_not_detected")
        failures.append(
            f"Face confidence {payload.face_confidence:.2f} below threshold {settings.min_face_confidence}"
        )

    if payload.audio_snr_db is not None and payload.audio_snr_db <= settings.min_audio_snr_db:
        flags.append("high_noise")
        failures.append(
            f"Audio SNR {payload.audio_snr_db:.1f} dB below threshold {settings.min_audio_snr_db} dB"
        )

    # De-duplicate flags
    flags = list(dict.fromkeys(flags))

    if failures:
        return QualityGateResult(
            passed=False,
            flags=flags,
            rejection_reason="; ".join(failures),
        )

    return QualityGateResult(passed=True, flags=flags)
