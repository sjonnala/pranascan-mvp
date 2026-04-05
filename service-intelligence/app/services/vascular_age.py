"""
Vascular age heuristic (v1).

Estimates the population age-bracket whose cardiovascular norms (resting HR and
HRV RMSSD) best match the user's current scan values.

Output is a wellness indicator — not a clinical age estimate, not a diagnosis.
A user's vascular age estimate may differ from their chronological age; that
difference is purely informational.

Reference population norms (Shaffer & Ginsberg 2017; Nunan et al. 2010):
  Each bracket is the midpoint age; HR/HRV values are approximate means ± 1 SD.

Privacy: no chronological age or personal data is used or stored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Population reference brackets
# (midpoint_age, hr_mean, hr_std, hrv_rmssd_mean, hrv_rmssd_std)
# ---------------------------------------------------------------------------
_BRACKETS: list[tuple[int, float, float, float, float]] = [
    (25, 62.0, 8.5, 55.0, 16.0),
    (35, 65.0, 8.0, 45.0, 13.0),
    (45, 68.0, 8.0, 35.0, 10.0),
    (55, 71.0, 7.5, 27.0, 9.0),
    (65, 73.0, 7.5, 21.0, 7.5),
    (75, 76.0, 7.0, 15.0, 6.5),
]

# Minimum STD floor to avoid division by zero on extreme inputs
_MIN_STD = 1e-3


@dataclass(frozen=True)
class VascularAgeResult:
    """Vascular age wellness indicator. Not a clinical estimate."""

    estimate_years: float | None
    """Age-bracket midpoint (years) whose norms best match HR + HRV."""

    confidence: float | None
    """Confidence score 0–1: 1 = clear bracket match, 0 = ambiguous."""

    used_hrv: bool
    """True when HRV was available and included in the distance calculation."""


def estimate_vascular_age(
    hr_bpm: float | None,
    hrv_ms: float | None,
) -> VascularAgeResult:
    """
    Estimate vascular age bracket from resting HR and/or HRV (RMSSD).

    Returns null estimate if neither metric is available or both are
    physiologically implausible.
    """
    if hr_bpm is None and hrv_ms is None:
        return VascularAgeResult(estimate_years=None, confidence=None, used_hrv=False)

    # Validate ranges
    hr_valid = hr_bpm is not None and 30.0 <= hr_bpm <= 220.0
    hrv_valid = hrv_ms is not None and 0.0 <= hrv_ms <= 500.0

    if not hr_valid and not hrv_valid:
        return VascularAgeResult(estimate_years=None, confidence=None, used_hrv=False)

    distances: list[float] = []
    for _midpoint, hr_mean, hr_std, hrv_mean, hrv_std in _BRACKETS:
        d = 0.0
        n = 0
        if hr_valid:
            d += ((hr_bpm - hr_mean) / max(hr_std, _MIN_STD)) ** 2  # type: ignore[operator]
            n += 1
        if hrv_valid:
            d += ((hrv_ms - hrv_mean) / max(hrv_std, _MIN_STD)) ** 2  # type: ignore[operator]
            n += 1
        distances.append(math.sqrt(d / n) if n > 0 else float("inf"))

    best_idx = int(min(range(len(distances)), key=lambda i: distances[i]))
    best_dist = distances[best_idx]

    # Confidence: softmax-style inverse distance (bounded 0–1)
    # A distance of 0 = perfect match (confidence 1.0)
    # A distance of 3+ standard deviations = very low confidence
    confidence = round(1.0 / (1.0 + best_dist), 3)

    return VascularAgeResult(
        estimate_years=float(_BRACKETS[best_idx][0]),
        confidence=confidence,
        used_hrv=hrv_valid,
    )
