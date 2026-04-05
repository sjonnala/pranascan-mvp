"""
Quality gate service — validates scan quality before accepting results.

D26 Bug bash hardening
----------------------
Previously the gate was binary pass/fail — any threshold violation rejected
the scan. This caused unnecessary rejections for common real-world conditions:

  • Slight facial hair / glasses lower face_confidence by ~0.05–0.10.
  • Indirect or slightly dim indoor light scores 0.37–0.40.
  • Borderline audio SNR (~12 dB) in a quiet but not silent room.

The updated gate introduces two severity levels:

  ERROR   — hard failure, scan rejected (original behaviour for clear violations)
  WARNING — borderline, scan proceeds with a flag attached to the result

Borderline ranges (WARNING zone):
  lighting_score    : (min_lighting_score - 0.07, min_lighting_score]  → default (0.33, 0.40]
  face_confidence   : (min_face_confidence - 0.12, min_face_confidence] → default (0.68, 0.80]
  audio_snr_db      : (min_audio_snr_db - 5.0, min_audio_snr_db]       → default (10.0, 15.0]
  motion_score      : no warning zone — motion is always a hard gate

Partial occlusion
-----------------
When face_confidence falls in the warning zone, a `partial_occlusion_suspected`
flag is added. This covers glasses, thick-framed spectacles, and beards that
reduce the JPEG face-size signature without hiding the face entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.config import settings
from app.schemas.scan import ScanResultSubmit

# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

# Width of the warning zone below each hard threshold
_LIGHTING_WARNING_DELTA = 0.07  # (threshold - 0.07, threshold] = warning
_FACE_WARNING_DELTA = 0.12  # (threshold - 0.12, threshold] = warning
_AUDIO_WARNING_DELTA = 5.0  # (threshold - 5.0,  threshold] = warning


class QualityFlagSeverity(str, Enum):
    WARNING = "warning"  # borderline — scan proceeds, flag attached
    ERROR = "error"  # hard failure — scan rejected


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class QualityGateResult:
    passed: bool
    flags: list[str]  # all flags (warning + error)
    warnings: list[str] = field(default_factory=list)  # warning-only flags
    rejection_reason: str | None = None  # set on ERROR-level failures


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_metric(
    value: float | None,
    hard_threshold: float,
    warning_delta: float,
    low_flag: str,
    warning_flag: str,
    compare: str = "lt",  # "lt" = value < threshold means bad
) -> tuple[QualityFlagSeverity | None, str | None]:
    """
    Returns (severity, flag) for one metric, or (None, None) if OK.

    Parameters
    ----------
    compare : "lt" — bad when value < threshold (default for all current metrics)
    """
    if value is None:
        return None, None

    if compare == "lt":
        hard_limit = hard_threshold - warning_delta
        if value <= hard_limit:
            return QualityFlagSeverity.ERROR, low_flag
        if value < hard_threshold:
            return QualityFlagSeverity.WARNING, warning_flag
    return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_quality_gate(payload: ScanResultSubmit) -> QualityGateResult:
    """
    Validate scan quality metrics against configured thresholds.

    Hard failures (ERROR) cause scan rejection.
    Borderline cases (WARNING) allow the scan to proceed with a flag.

    Returns a QualityGateResult with:
      passed           — False only when at least one ERROR-level violation found
      flags            — all raised flags (both WARNING and ERROR severities)
      warnings         — WARNING-level flags only (scan proceeded despite these)
      rejection_reason — human-readable description of ERROR violations
    """
    if settings.skip_quality_gate:
        return QualityGateResult(
            passed=True,
            flags=list(dict.fromkeys(payload.flags)),
            warnings=[],
            rejection_reason=None,
        )

    accumulated_flags: list[str] = list(payload.flags)
    warnings: list[str] = []
    hard_failures: list[str] = []

    # ── Lighting ─────────────────────────────────────────────────────────────
    lighting_severity, lighting_flag = _check_metric(
        payload.lighting_score,
        hard_threshold=settings.min_lighting_score,
        warning_delta=_LIGHTING_WARNING_DELTA,
        low_flag="low_lighting",
        warning_flag="borderline_lighting",
    )
    if lighting_flag:
        accumulated_flags.append(lighting_flag)
        if lighting_severity == QualityFlagSeverity.ERROR:
            hard_failures.append(
                f"Lighting score {payload.lighting_score:.2f} too low "
                f"(threshold {settings.min_lighting_score - _LIGHTING_WARNING_DELTA:.2f}). "
                "Find a brighter spot and try again."
            )
        else:
            warnings.append(lighting_flag)

    # ── Motion ───────────────────────────────────────────────────────────────
    # Motion has no warning zone — always a hard gate.
    if payload.motion_score is not None and payload.motion_score < settings.min_motion_score:
        accumulated_flags.append("motion_detected")
        hard_failures.append(
            f"Motion score {payload.motion_score:.2f} below threshold "
            f"{settings.min_motion_score}. Hold still during the scan."
        )

    # ── Face confidence ───────────────────────────────────────────────────────
    face_severity, face_flag = _check_metric(
        payload.face_confidence,
        hard_threshold=settings.min_face_confidence,
        warning_delta=_FACE_WARNING_DELTA,
        low_flag="face_not_detected",
        warning_flag="partial_occlusion_suspected",
    )
    if face_flag:
        accumulated_flags.append(face_flag)
        if face_severity == QualityFlagSeverity.ERROR:
            hard_failures.append(
                f"Face confidence {payload.face_confidence:.2f} too low "
                f"(threshold {settings.min_face_confidence - _FACE_WARNING_DELTA:.2f}). "
                "Centre your face in the camera."
            )
        else:
            # borderline face_confidence = likely partial occlusion (glasses/beard)
            warnings.append(face_flag)

    # ── Audio SNR ─────────────────────────────────────────────────────────────
    audio_severity, audio_flag = _check_metric(
        payload.audio_snr_db,
        hard_threshold=settings.min_audio_snr_db,
        warning_delta=_AUDIO_WARNING_DELTA,
        low_flag="high_noise",
        warning_flag="borderline_noise",
    )
    if audio_flag:
        accumulated_flags.append(audio_flag)
        if audio_severity == QualityFlagSeverity.ERROR:
            hard_failures.append(
                f"Audio SNR {payload.audio_snr_db:.1f} dB too low "
                f"(threshold {settings.min_audio_snr_db - _AUDIO_WARNING_DELTA:.1f} dB). "
                "Try in a quieter environment."
            )
        else:
            warnings.append(audio_flag)

    # De-duplicate flags (preserve insertion order)
    accumulated_flags = list(dict.fromkeys(accumulated_flags))

    if hard_failures:
        return QualityGateResult(
            passed=False,
            flags=accumulated_flags,
            warnings=warnings,
            rejection_reason="; ".join(hard_failures),
        )

    return QualityGateResult(passed=True, flags=accumulated_flags, warnings=warnings)
