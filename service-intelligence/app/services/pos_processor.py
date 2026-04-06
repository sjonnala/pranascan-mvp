"""Compatibility wrapper around the canonical POS rPPG processor."""

from __future__ import annotations

from collections.abc import Sequence

from app.services.rppg_processor import (
    FrameSample,
    RppgResult,
    extract_bvp,
    process_frames,
)
from app.services.rppg_processor import (
    RppgBvpSignal as PosBvpSignal,
)


def process_rgb_traces(frames: Sequence[FrameSample]) -> RppgResult:
    """Backward-compatible alias for the POS-capable rPPG processor."""
    return process_frames(frames)


__all__ = [
    "FrameSample",
    "PosBvpSignal",
    "RppgResult",
    "extract_bvp",
    "process_rgb_traces",
]
