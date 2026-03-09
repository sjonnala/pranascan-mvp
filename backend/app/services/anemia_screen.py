"""
Anemia screening wellness indicator service (v1 color heuristic).

Wellness screening indicator only. Not a diagnostic tool.
Results should not be used to diagnose or treat any medical condition.

Reference: Kirenga et al. 2021, Nkrumah et al. 2011 — conjunctival pallor
as a proxy for haemoglobin level.

Key insight:
- Healthy conjunctiva: highly vascularised → pinkish-red hue, high R channel
- Anaemic conjunctiva: pale → lower R relative to G/B

Privacy: Only scalar indicators computed from on-device frame means are
processed here. No image data ever reaches this function.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnemiaScreenResult:
    """
    Wellness screening indicator result — NOT a diagnostic report.

    hb_proxy_score: 0–1, higher = more likely normal haemoglobin proxy.
                    None when confidence gate is not met.
    wellness_label: wellness category string or None.
    confidence: combined lighting/motion confidence score (0–1).
    flags: list of informational flags.
    """

    hb_proxy_score: float | None
    wellness_label: str | None
    confidence: float
    flags: list[str] = field(default_factory=list)


def screen_anemia(
    r_mean: float | None,
    g_mean: float | None,
    b_mean: float | None,
    lighting_score: float | None,
    motion_score: float | None,
) -> AnemiaScreenResult:
    """
    Compute a wellness haemoglobin proxy from mean conjunctival RGB values.

    Wellness screening indicator only. Not a diagnostic tool.
    Results should not be used to diagnose or treat any medical condition.

    Parameters
    ----------
    r_mean : Mean red channel across scan frames (0–255), or None.
    g_mean : Mean green channel across scan frames (0–255), or None.
    b_mean : Mean blue channel across scan frames (0–255), or None.
    lighting_score : Lighting quality score (0–1), or None.
    motion_score   : Motion quality score (0–1), or None.

    Returns
    -------
    AnemiaScreenResult
    """
    # ── Guard: all colour channels missing ───────────────────────────────────
    if r_mean is None and g_mean is None and b_mean is None:
        return AnemiaScreenResult(
            hb_proxy_score=None,
            wellness_label=None,
            confidence=0.0,
            flags=["insufficient_color_data"],
        )

    # ── Clamp each channel to [0, 255] ────────────────────────────────────────
    r = float(max(0.0, min(255.0, r_mean if r_mean is not None else 0.0)))
    g = float(max(0.0, min(255.0, g_mean if g_mean is not None else 0.0)))
    b = float(max(0.0, min(255.0, b_mean if b_mean is not None else 0.0)))

    rgb_total = r + g + b

    # ── Guard: degenerate pixel values ───────────────────────────────────────
    if rgb_total < 1.0:
        return AnemiaScreenResult(
            hb_proxy_score=None,
            wellness_label=None,
            confidence=0.0,
            flags=["insufficient_color_data"],
        )

    # ── Confidence gate ───────────────────────────────────────────────────────
    ls = float(lighting_score) if lighting_score is not None else 0.0
    ms = float(motion_score) if motion_score is not None else 0.0
    confidence = ls * 0.7 + ms * 0.3

    flags: list[str] = []

    if confidence < 0.5:
        return AnemiaScreenResult(
            hb_proxy_score=None,
            wellness_label=None,
            confidence=confidence,
            flags=["low_confidence_environment"],
        )

    if confidence < 0.7:
        flags.append("borderline_confidence")

    # ── Haemoglobin proxy score ───────────────────────────────────────────────
    r_fraction = r / rgb_total
    raw_score = (r_fraction - 0.25) / (0.40 - 0.25)
    hb_proxy_score = float(min(1.0, max(0.0, raw_score)))

    # ── Wellness label ────────────────────────────────────────────────────────
    if hb_proxy_score >= 0.6:
        wellness_label = "normal_range"
    elif hb_proxy_score >= 0.3:
        wellness_label = "below_typical_range"
    else:
        wellness_label = "consider_followup"

    return AnemiaScreenResult(
        hb_proxy_score=hb_proxy_score,
        wellness_label=wellness_label,
        confidence=confidence,
        flags=flags,
    )
