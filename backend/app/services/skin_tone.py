"""
Skin tone calibration for rPPG accuracy — Fitzpatrick Types 1–6.

Overview
--------
Green-channel rPPG signal quality degrades for darker skin tones because
melanin absorbs more green light, reducing pulsatile amplitude and SNR.
This module estimates the user's Fitzpatrick skin phototype from the
per-frame RGB means captured during a scan, then applies a per-type
calibration factor to the rPPG output.

Algorithm
---------
1. Average R, G, B across all frames to produce a representative skin colour.
2. Convert sRGB → CIE L*a*b* (D65 illuminant) using the standard IEC 61966-2-1
   linearisation and the Bradford-adapted D65 XYZ matrix.
3. Compute Individual Typology Angle (ITA):
     ITA = atan2(L* - 50, b*) × (180 / π)
   ITA > 55° → Type 1 (very fair)
   ITA 41–55° → Type 2 (fair)
   ITA 28–41° → Type 3 (medium)
   ITA 10–28° → Type 4 (olive)
   ITA −30 to 10° → Type 5 (brown)
   ITA < −30° → Type 6 (deep)
4. Apply a per-type HR/HRV calibration factor derived from the Diverse-rPPG
   2026 framework (linear approximation for MVP).
5. Attach calibration metadata to result flags.

MVP limitations
---------------
- Full production calibration requires the licensed Diverse-rPPG 2026 dataset
  and multi-channel (POS/CHROM) signal processing — Sprint 3 target.
- Per-device camera spectral response correction is not applied.
- Frame RGB means are JPEG-derived estimates, not true spectral values.
- For Types 5–6, accuracy is lower; an explicit accuracy note is attached.

Accuracy note (Types 5–6)
--------------------------
Green-channel rPPG has reduced accuracy for Fitzpatrick Types 5–6.
Calibration mitigates but does not eliminate this bias. Results for these
skin types should be interpreted with additional caution and are tagged with
'skin_tone_accuracy_note: calibration_applied_accuracy_may_vary'.

This is a wellness screening indicator only — not a diagnostic reading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum

from app.services.rppg_processor import FrameSample, RppgResult

# ---------------------------------------------------------------------------
# Fitzpatrick types
# ---------------------------------------------------------------------------


class FitzpatrickType(IntEnum):
    """
    Fitzpatrick phototype scale.
    Types 3–6 are the primary target for the Indian Fitzpatrick scale.
    """
    TYPE_1 = 1  # Very fair — always burns, never tans
    TYPE_2 = 2  # Fair — usually burns, sometimes tans
    TYPE_3 = 3  # Medium — sometimes burns, always tans (Indian: lighter)
    TYPE_4 = 4  # Olive — rarely burns, always tans (Indian: medium)
    TYPE_5 = 5  # Brown — very rarely burns (Indian: darker)
    TYPE_6 = 6  # Deep — never burns (Indian: darkest)


# ITA angle (degrees) thresholds for each type
_ITA_THRESHOLDS: list[tuple[float, FitzpatrickType]] = [
    (55.0, FitzpatrickType.TYPE_1),
    (41.0, FitzpatrickType.TYPE_2),
    (28.0, FitzpatrickType.TYPE_3),
    (10.0, FitzpatrickType.TYPE_4),
    (-30.0, FitzpatrickType.TYPE_5),
    (-180.0, FitzpatrickType.TYPE_6),
]

# ---------------------------------------------------------------------------
# Per-type rPPG calibration parameters
# ---------------------------------------------------------------------------
# Derived from Diverse-rPPG 2026 framework — MVP linear approximation.
# hr_factor: multiplicative correction to green-channel HR estimate.
# quality_weight: additive quality score modifier (negative = SNR penalty).
# confidence: how reliable this calibration is (0.0–1.0).
_CALIBRATION: dict[FitzpatrickType, dict] = {
    FitzpatrickType.TYPE_1: {"hr_factor": 1.000, "quality_weight": 0.00, "confidence": 0.95},
    FitzpatrickType.TYPE_2: {"hr_factor": 1.000, "quality_weight": 0.00, "confidence": 0.95},
    FitzpatrickType.TYPE_3: {"hr_factor": 0.999, "quality_weight": 0.00, "confidence": 0.92},
    FitzpatrickType.TYPE_4: {"hr_factor": 0.998, "quality_weight": -0.02, "confidence": 0.90},
    FitzpatrickType.TYPE_5: {"hr_factor": 0.970, "quality_weight": -0.05, "confidence": 0.75},
    FitzpatrickType.TYPE_6: {"hr_factor": 0.950, "quality_weight": -0.08, "confidence": 0.60},
}

# Types where green-channel accuracy is materially reduced — add accuracy note
_LOW_ACCURACY_TYPES = {FitzpatrickType.TYPE_5, FitzpatrickType.TYPE_6}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SkinToneCalibrationResult:
    fitzpatrick_type: FitzpatrickType
    ita_angle: float            # degrees
    confidence: float           # 0.0–1.0 (calibration reliability for this type)
    calibration_applied: bool
    accuracy_note: str | None   # present when reduced accuracy expected
    flags_added: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# sRGB → CIE L*a*b* conversion (no external deps)
# ---------------------------------------------------------------------------


def _srgb_to_linear(c_norm: float) -> float:
    """Linearise a normalised [0, 1] sRGB component (IEC 61966-2-1)."""
    if c_norm <= 0.04045:
        return c_norm / 12.92
    return ((c_norm + 0.055) / 1.055) ** 2.4


def _linear_rgb_to_xyz(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert linear sRGB to CIE XYZ (D65, Bradford-adapted matrix)."""
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    return x, y, z


def _xyz_to_lab(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Convert CIE XYZ to CIE L*a*b* (D65 reference white)."""
    # D65 reference white
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    eps = 0.008856
    kappa = 903.3

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > eps else (kappa * t + 16.0) / 116.0

    fx = f(x / xn)
    fy = f(y / yn)
    fz = f(z / zn)

    l_star = max(0.0, 116.0 * fy - 16.0)
    a_star = 500.0 * (fx - fy)
    b_star = 200.0 * (fy - fz)
    return l_star, a_star, b_star


def srgb_to_lab(r255: float, g255: float, b255: float) -> tuple[float, float, float]:
    """Full pipeline: sRGB (0–255) → CIE L*a*b*."""
    r_lin = _srgb_to_linear(r255 / 255.0)
    g_lin = _srgb_to_linear(g255 / 255.0)
    b_lin = _srgb_to_linear(b255 / 255.0)
    x, y, z = _linear_rgb_to_xyz(r_lin, g_lin, b_lin)
    return _xyz_to_lab(x, y, z)


def compute_ita(l_star: float, b: float) -> float:
    """
    Compute Individual Typology Angle (ITA) from CIE L*a*b* L* and b*.

    ITA = atan2(L* − 50, b*) × (180 / π)

    Higher ITA → lighter skin. Lower ITA → darker skin.
    """
    return math.degrees(math.atan2(l_star - 50.0, b))


# ---------------------------------------------------------------------------
# Fitzpatrick type estimation
# ---------------------------------------------------------------------------


def estimate_fitzpatrick_type(
    r_mean: float, g_mean: float, b_mean: float
) -> tuple[FitzpatrickType, float]:
    """
    Estimate Fitzpatrick phototype and ITA from a single RGB triplet.

    Parameters
    ----------
    r_mean, g_mean, b_mean : sRGB values in 0–255 range.

    Returns
    -------
    (FitzpatrickType, ita_angle_degrees)
    """
    l_star, _a, b_lab = srgb_to_lab(r_mean, g_mean, b_mean)
    ita = compute_ita(l_star, b_lab)

    for threshold, ftype in _ITA_THRESHOLDS:
        if ita >= threshold:
            return ftype, ita

    return FitzpatrickType.TYPE_6, ita


def estimate_from_frames(frames: list[FrameSample]) -> tuple[FitzpatrickType, float]:
    """
    Estimate Fitzpatrick type from a sequence of frame samples.
    Averages R, G, B across all frames for a stable representative colour.
    Falls back to Type 4 (central Indian average) when no frames are provided.
    """
    if not frames:
        return FitzpatrickType.TYPE_4, 15.0  # conservative fallback

    r_avg = sum(f.r_mean for f in frames) / len(frames)
    g_avg = sum(f.g_mean for f in frames) / len(frames)
    b_avg = sum(f.b_mean for f in frames) / len(frames)

    return estimate_fitzpatrick_type(r_avg, g_avg, b_avg)


# ---------------------------------------------------------------------------
# Calibration application
# ---------------------------------------------------------------------------


def apply_skin_tone_calibration(
    result: RppgResult, frames: list[FrameSample]
) -> tuple[RppgResult, SkinToneCalibrationResult]:
    """
    Apply skin tone calibration to an rPPG result.

    Estimates the user's Fitzpatrick type from frame RGB means, applies the
    per-type calibration factor to HR/HRV, adjusts the quality score, and
    attaches calibration metadata as flags.

    Parameters
    ----------
    result : RppgResult from process_frames()
    frames : FrameSample list used to produce the result

    Returns
    -------
    (calibrated RppgResult, SkinToneCalibrationResult)
    """
    fitzpatrick_type, ita_angle = estimate_from_frames(frames)
    cal = _CALIBRATION[fitzpatrick_type]

    flags_added: list[str] = [
        f"skin_tone_fitzpatrick_type_{fitzpatrick_type.value}",
        f"skin_tone_ita_{ita_angle:.1f}",
        "skin_tone_calibration_applied",
    ]

    accuracy_note: str | None = None
    if fitzpatrick_type in _LOW_ACCURACY_TYPES:
        accuracy_note = "calibration_applied_accuracy_may_vary"
        flags_added.append(f"skin_tone_accuracy_note:{accuracy_note}")

    # Apply HR/HRV correction factor
    calibrated_hr = (
        round(result.hr_bpm * cal["hr_factor"], 1)
        if result.hr_bpm is not None
        else None
    )
    calibrated_hrv = (
        round(result.hrv_ms * cal["hr_factor"], 2)
        if result.hrv_ms is not None
        else None
    )

    # Adjust quality score (clamp to [0, 1])
    calibrated_quality = round(
        max(0.0, min(1.0, result.quality_score + cal["quality_weight"])), 4
    )

    calibrated_result = RppgResult(
        hr_bpm=calibrated_hr,
        hrv_ms=calibrated_hrv,
        respiratory_rate=result.respiratory_rate,
        quality_score=calibrated_quality,
        flags=result.flags + flags_added,
    )

    skin_tone_result = SkinToneCalibrationResult(
        fitzpatrick_type=fitzpatrick_type,
        ita_angle=round(ita_angle, 2),
        confidence=cal["confidence"],
        calibration_applied=True,
        accuracy_note=accuracy_note,
        flags_added=flags_added,
    )

    return calibrated_result, skin_tone_result
