"""Compatibility wrapper around the canonical POS rPPG processor."""

from __future__ import annotations

from collections.abc import Sequence

from app.services.rppg_processor import (
    FrameSample,
    RppgBvpSignal as PosBvpSignal,
    RppgResult,
    extract_bvp,
    process_frames,
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
