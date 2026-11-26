"""Deterministic synthetic manifest for smoke runs and tests of the eval kit.

Builds clean 30 Hz ROI-mean traces with a slowly drifting, known heart rate, passes them through
the Phase 2 budget-phone simulator (``phone_degradation``), and writes a ``DatasetSessionV2``
manifest with trace CSVs and per-second reference CSVs.

Skin tone is modelled only as pulsatile (AC) attenuation plus a darker DC, never as a change of
frequency. The per-type factors below are assumptions for exercising the stratified metrics
(the audit's A7 uses x0.45 for V-VI); they are not measured constants. Numbers from this data
show that the harness works, not how any method performs on real phones.
"""

from __future__ import annotations

import csv
import math
from dataclasses import replace
from pathlib import Path

import numpy as np

from app.services.rppg_processor import FrameSample
from learning.phase1.common import ensure_output_dir, write_frame_samples_csv, write_json
from learning.phase2_fastai.phone_degradation import degrade_trace, get_preset

# (AC attenuation, DC scale) per Fitzpatrick type. Assumed, for synthetic strata only.
SKIN_FACTORS: dict[int, tuple[float, float]] = {
    1: (1.0, 1.0),
    2: (0.95, 0.95),
    3: (0.85, 0.88),
    4: (0.7, 0.78),
    5: (0.5, 0.68),
    6: (0.42, 0.6),
}
CAPTURES: dict[str, tuple[str, str, str]] = {
    # name -> (phone_degradation preset, lighting label, motion label)
    "bright": ("budget_bright", "bright", "still"),
    "indoor": ("budget_india_indoor", "indoor", "still"),
    "dim": ("budget_dim_darker_skin", "dim", "still"),
    "motion": ("budget_motion", "indoor", "motion"),
}
DC_RGB = np.array([176.0, 126.0, 101.0])
PULSE_SIGNATURE = np.array([0.33, 0.77, 0.53]) / 0.77


def clean_trace(
    hr_bpm: float,
    duration_s: float = 30.0,
    fs: float = 30.0,
    ac_relative: float = 0.006,
    dc_scale: float = 1.0,
    has_pulse: bool = True,
    hr_drift_bpm: float = 3.0,
    seed: int = 0,
) -> tuple[list[FrameSample], np.ndarray, np.ndarray]:
    """Clean trace plus the instantaneous reference ``(t_s, hr_bpm)`` used to make it."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, duration_s, 1.0 / fs)
    hr_t = hr_bpm + hr_drift_bpm * np.sin(2 * math.pi * t / 40.0 + rng.uniform(0, 2 * math.pi))
    phase = 2 * math.pi * np.cumsum(hr_t / 60.0) / fs
    wave = np.sin(phase) + 0.35 * np.sin(2 * phase + 0.6)
    ac = ac_relative * PULSE_SIGNATURE * (1.0 if has_pulse else 0.0)
    dc = DC_RGB * dc_scale
    rgb = dc[None, :] * (1.0 + ac[None, :] * wave[:, None])
    frames = [
        FrameSample(
            t_ms=float(ti * 1000.0), r_mean=float(c[0]), g_mean=float(c[1]), b_mean=float(c[2])
        )
        for ti, c in zip(t, rgb, strict=True)
    ]
    return frames, t, hr_t


def write_synthetic_manifest(
    output_dir: str | Path,
    n_subjects_per_type: int = 3,
    captures: tuple[str, ...] = ("bright", "indoor"),
    fitzpatrick_types: tuple[int, ...] = (1, 2, 3, 4, 5, 6),
    no_pulse_every: int = 3,
    duration_s: float = 30.0,
    seed: int = 7,
) -> Path:
    """Write traces, references and ``manifest.json``; return the manifest path."""
    root = ensure_output_dir(output_dir)
    rng = np.random.default_rng(seed)
    sessions = []
    counter = 0
    for fitz in fitzpatrick_types:
        ac_att, dc_scale = SKIN_FACTORS[fitz]
        for s in range(n_subjects_per_type):
            subject_id = f"syn_f{fitz}_s{s:02d}"
            hr0 = float(rng.uniform(58.0, 105.0))
            plan = [(c, True) for c in captures]
            if no_pulse_every and (counter % no_pulse_every == 0):
                plan.append((captures[0], False))
            for capture, has_pulse in plan:
                preset, lighting, motion = CAPTURES[capture]
                sess_seed = int(rng.integers(0, 2**31 - 1))
                frames, ref_t, ref_hr = clean_trace(
                    hr0,
                    duration_s=duration_s,
                    ac_relative=0.006 * ac_att,
                    dc_scale=dc_scale,
                    has_pulse=has_pulse,
                    seed=sess_seed,
                )
                cfg = get_preset(preset)
                # Skin optics already applied in the clean trace; keep the preset's lighting.
                cfg = replace(cfg, skin_ac_attenuation=1.0, skin_dc_scale=1.0)
                degraded = degrade_trace(frames, cfg, seed=sess_seed)
                session_id = f"{subject_id}_{capture}{'' if has_pulse else '_nopulse'}"
                trace_rel = f"traces/{session_id}.csv"
                write_frame_samples_csv(root / trace_rel, degraded.frames)
                entry: dict = {
                    "session_id": session_id,
                    "trace_csv": trace_rel,
                    "metadata": {
                        "dataset": "PranaScan-Synthetic",
                        "licence": "synthetic_owned",
                        "split": "test",
                        "has_pulse": has_pulse,
                        "scenario": capture,
                        "preset": preset,
                        "seed": sess_seed,
                        "capture": {
                            "device": f"sim_{preset}",
                            "is_smartphone": True,
                            "codec": "preview_rgb",
                            "nominal_fps": 30.0,
                            "resolution": [1280, 720],
                            "lighting": lighting,
                            "motion": motion,
                        },
                        "subject": {"subject_id": subject_id, "fitzpatrick": fitz},
                    },
                }
                if has_pulse:
                    ref_rel = f"references/{session_id}.csv"
                    _write_reference(root / ref_rel, ref_t, ref_hr)
                    entry["reference_csv"] = ref_rel
                    entry["metadata"]["reference"] = {
                        "kind": "hr_series",
                        "sensor": "synthetic_ground_truth",
                        "fs_hz": 1.0,
                    }
                sessions.append(entry)
            counter += 1
    manifest_path = root / "manifest.json"
    write_json(manifest_path, {"dataset_name": "PranaScan-Synthetic", "sessions": sessions})
    return manifest_path


def _write_reference(path: Path, t_s: np.ndarray, hr_bpm: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seconds = np.arange(0.0, float(t_s[-1]) + 1e-9, 1.0)
    hr = np.interp(seconds, t_s, hr_bpm)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_ms", "hr_bpm"])
        for s, h in zip(seconds, hr, strict=True):
            writer.writerow([round(s * 1000.0, 1), round(float(h), 3)])
