"""Export windowed rPPG traces as fast.ai-ready images: spectrograms and 6-channel STMaps.

For every sliding window (default 10 s, hop 2 s) of a session's per-patch RGB traces:

- ``spec/<id>.png``: 64x64 grayscale log-power spectrogram of the windowed-POS
  signal (STFT 4 s window, 0.25 s hop, 0.5-4.5 Hz; low frequencies at the bottom).
  Loads directly with ``ImageDataLoaders.from_df``.
- ``stmap/<id>.npy``: float32 STMap of shape ``(6, P, T)``. Channels 0-2 are
  per-patch RGB normalised by their own 1 s moving mean; channels 3-5 are per-patch
  windowed POS, windowed CHROM and green. ``P`` = patches, ``T`` = samples on a
  uniform 30 Hz grid built from the true timestamps.
- ``stmap_png/<id>_rgb.png`` and ``stmap_png/<id>_sig.png``: 8-bit previews of the
  two channel triplets (rows min-max normalised), for eyeballing and for 3-channel
  baselines.
- ``labels.csv``: one row per window. ``label`` is the class (quality classes, or
  HR bins), with ``no_pulse`` as the negative class in both schemes.

Usage on Kaggle (no flips or rotations: the axes are time and frequency)::

    from fastai.vision.all import *
    df = pd.read_csv(path/'labels.csv')
    dls = ImageDataLoaders.from_df(df, path, fn_col='fname', label_col='label',
                                   valid_col='is_valid', item_tfms=Resize(64), batch_tfms=[])
    learn = vision_learner(dls, resnet18, metrics=[accuracy, F1Score(average='macro')])

    # 6-channel STMaps:
    def get_x(r): return TensorImage(torch.from_numpy(np.load(path/r['stmap_npy'])))
    dblock = DataBlock(blocks=(TransformBlock(), CategoryBlock), get_x=get_x,
                       get_y=ColReader('label'), splitter=ColSplitter('is_valid'))
    learn = vision_learner(dblock.dataloaders(df, bs=64), resnet18, n_in=6)

Licence guard: ``export_corpus(..., purpose="commercial_training")`` refuses any
``bench_only`` or non-commercial session, and ``load_labels_for_training``
re-checks every row against the pinned licence registry before training.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal

from app.services.rppg_processor import FrameSample
from learning.phase1.dataset_model import (
    CaptureContext,
    DatasetSessionV2,
    LicenceViolationError,
    Purpose,
    SubjectContext,
    check_commercial_training,
)

from .phone_degradation import DegradationEvent, degrade_patch_traces, get_preset

GRID_FS = 30.0
WINDOW_S = 10.0
HOP_S = 2.0
POS_WINDOW_S = 1.6
SPEC_WINDOW_S = 4.0
SPEC_HOP_S = 0.25
SPEC_BAND_HZ = (0.5, 4.5)
SPEC_SIZE = 64
GAP_FACTOR = 1.5
NO_PULSE = "no_pulse"
QUALITY_CLASSES = ("good", "low_snr", "motion", "exposure_event", NO_PULSE)
HR_BIN_WIDTH = 10
HR_RANGE = (40, 180)
STMAP_CHANNELS = ("r_norm", "g_norm", "b_norm", "pos", "chrom", "green")

LABEL_FIELDS = (
    "fname",
    "stmap_npy",
    "stmap_rgb_png",
    "stmap_sig_png",
    "label",
    "quality_label",
    "hr_bin",
    "hr_bpm",
    "has_pulse",
    "pos_hr_bpm",
    "is_valid",
    "session_id",
    "subject_id",
    "dataset",
    "licence",
    "split",
    "window_index",
    "window_start_ms",
    "window_end_ms",
    "n_patches",
    "valid_fraction",
    "delivered_fps",
    "fitzpatrick",
    "events",
)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def moving_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Centred moving mean along axis 0 with edge-aware normalisation."""
    window = max(1, int(window))
    kernel = np.ones(window) / window
    counts = np.convolve(np.ones(x.shape[0]), kernel, mode="same")
    if x.ndim == 1:
        return np.convolve(x, kernel, mode="same") / counts
    return np.column_stack(
        [np.convolve(x[:, i], kernel, mode="same") / counts for i in range(x.shape[1])]
    )


def temporal_normalise(rgb: np.ndarray, fs: float, window_s: float = 1.0) -> np.ndarray:
    """``x / moving_mean(x) - 1`` per channel. Removes slow AE/AWB drift."""
    mean = moving_mean(rgb, int(round(window_s * fs)))
    mean = np.where(np.abs(mean) < 1e-9, 1.0, mean)
    return rgb / mean - 1.0


def _overlap_add(rgb: np.ndarray, fs: float, window_s: float, project: Callable) -> np.ndarray:
    n = rgb.shape[0]
    length = min(n, max(2, int(math.ceil(window_s * fs))))
    out = np.zeros(n)
    for start in range(0, n - length + 1):
        block = rgb[start : start + length]
        mean = block.mean(axis=0)
        mean = np.where(np.abs(mean) < 1e-9, 1.0, mean)
        h = project(block / mean)
        out[start : start + length] += h - h.mean()
    return out


def _pos_projection(cn: np.ndarray) -> np.ndarray:
    s1 = cn[:, 1] - cn[:, 2]
    s2 = -2.0 * cn[:, 0] + cn[:, 1] + cn[:, 2]
    std2 = float(np.std(s2))
    return s1 + (float(np.std(s1)) / std2 if std2 > 1e-12 else 0.0) * s2


def _chrom_projection(cn: np.ndarray) -> np.ndarray:
    x = 3.0 * cn[:, 0] - 2.0 * cn[:, 1]
    y = 1.5 * cn[:, 0] + cn[:, 1] - 1.5 * cn[:, 2]
    std_y = float(np.std(y))
    return x - (float(np.std(x)) / std_y if std_y > 1e-12 else 0.0) * y


def windowed_pos(rgb: np.ndarray, fs: float, window_s: float = POS_WINDOW_S) -> np.ndarray:
    """POS with per-window temporal normalisation and overlap-add (Wang et al. 2017)."""
    return _overlap_add(rgb, fs, window_s, _pos_projection)


def windowed_chrom(rgb: np.ndarray, fs: float, window_s: float = POS_WINDOW_S) -> np.ndarray:
    """CHROM (de Haan and Jeanne 2013) with the same windowing as ``windowed_pos``."""
    return _overlap_add(rgb, fs, window_s, _chrom_projection)


def green_signal(rgb: np.ndarray, fs: float) -> np.ndarray:
    g = temporal_normalise(rgb[:, 1:2], fs)[:, 0]
    return signal.detrend(g)


def _bandpass(x: np.ndarray, fs: float, low: float = 0.7, high: float = 4.0) -> np.ndarray:
    nyquist = fs / 2.0
    sos = signal.butter(
        3, [low / nyquist, min(high, 0.95 * nyquist) / nyquist], btype="band", output="sos"
    )
    return signal.sosfiltfilt(sos, x, padlen=min(x.size - 1, int(3 * fs)))


def dominant_hr_bpm(x: np.ndarray, fs: float) -> float | None:
    """Spectral-peak HR of a pulse signal in 0.7-4 Hz, or None for a flat signal."""
    if float(np.std(x)) < 1e-12:
        return None
    filtered = _bandpass(x, fs)
    freqs, power = signal.periodogram(filtered, fs=fs, nfft=max(4096, filtered.size))
    band = (freqs >= 0.7) & (freqs <= 4.0)
    if not np.any(band) or float(np.max(power[band])) <= 0:
        return None
    return round(float(freqs[band][np.argmax(power[band])]) * 60.0, 2)


# ---------------------------------------------------------------------------
# Windowing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResampledWindow:
    """One window of every patch on a shared uniform grid."""

    grid_ms: np.ndarray
    rgb: np.ndarray  # (P, T, 3)
    valid: np.ndarray  # (P, T) bool: False where the grid bridges a delivery gap
    patch_names: tuple[str, ...]


def resample_window(
    patch_traces: Mapping[str, Sequence[FrameSample]],
    start_ms: float,
    window_s: float = WINDOW_S,
    grid_fs: float = GRID_FS,
) -> ResampledWindow:
    """Linear resampling onto a uniform grid using each sample's true timestamp."""
    n = int(round(window_s * grid_fs))
    grid_ms = start_ms + np.arange(n) * 1000.0 / grid_fs
    names = tuple(patch_traces)
    rgb = np.zeros((len(names), n, 3))
    valid = np.zeros((len(names), n), dtype=bool)
    for p, name in enumerate(names):
        frames = patch_traces[name]
        t = np.array([f.t_ms for f in frames], dtype=np.float64)
        values = np.array([[f.r_mean, f.g_mean, f.b_mean] for f in frames], dtype=np.float64)
        order = np.argsort(t, kind="stable")
        t, values = t[order], values[order]
        for c in range(3):
            rgb[p, :, c] = np.interp(grid_ms, t, values[:, c])
        diffs = np.diff(t)
        nominal = float(np.median(diffs[diffs > 0])) if np.any(diffs > 0) else 1000.0 / grid_fs
        right = np.clip(np.searchsorted(t, grid_ms, side="left"), 1, t.size - 1)
        gap = t[right] - t[right - 1]
        inside = (grid_ms >= t[0]) & (grid_ms <= t[-1])
        valid[p] = inside & (gap <= GAP_FACTOR * nominal)
    return ResampledWindow(grid_ms=grid_ms, rgb=rgb, valid=valid, patch_names=names)


def build_stmap(window: ResampledWindow, grid_fs: float = GRID_FS) -> np.ndarray:
    """6-channel STMap ``(6, P, T)``: RGB normalised + windowed POS, CHROM, green."""
    n_patches, n_samples, _ = window.rgb.shape
    stmap = np.zeros((len(STMAP_CHANNELS), n_patches, n_samples), dtype=np.float32)
    for p in range(n_patches):
        rgb = window.rgb[p]
        stmap[0:3, p, :] = temporal_normalise(rgb, grid_fs).T
        stmap[3, p, :] = _standardise(windowed_pos(rgb, grid_fs))
        stmap[4, p, :] = _standardise(windowed_chrom(rgb, grid_fs))
        stmap[5, p, :] = _standardise(green_signal(rgb, grid_fs))
    return stmap


def _standardise(x: np.ndarray) -> np.ndarray:
    std = float(np.std(x))
    return (x - float(np.mean(x))) / std if std > 1e-12 else np.zeros_like(x)


def spectrogram_image(
    pulse: np.ndarray,
    fs: float = GRID_FS,
    size: int = SPEC_SIZE,
    window_s: float = SPEC_WINDOW_S,
    hop_s: float = SPEC_HOP_S,
    band_hz: tuple[float, float] = SPEC_BAND_HZ,
) -> np.ndarray:
    """``size x size`` uint8 log-power spectrogram; row 0 is the highest frequency."""
    nperseg = min(pulse.size, int(round(window_s * fs)))
    hop = max(1, int(round(hop_s * fs)))
    nfft = max(1024, nperseg)
    freqs, times, z = signal.stft(
        pulse - np.mean(pulse),
        fs=fs,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg - hop,
        nfft=nfft,
        boundary=None,
        padded=False,
    )
    band = (freqs >= band_hz[0]) & (freqs <= band_hz[1])
    power = np.log10(np.abs(z[band]) ** 2 + 1e-12)
    band_freqs = freqs[band]
    target_f = np.linspace(band_hz[0], band_hz[1], size)
    by_freq = np.array(
        [np.interp(target_f, band_freqs, power[:, i]) for i in range(power.shape[1])]
    ).T
    if by_freq.shape[1] == 1:
        by_time = np.repeat(by_freq, size, axis=1)
    else:
        src_t = np.linspace(0.0, 1.0, by_freq.shape[1])
        dst_t = np.linspace(0.0, 1.0, size)
        by_time = np.array([np.interp(dst_t, src_t, row) for row in by_freq])
    image = _to_uint8(by_time)
    return image[::-1]  # low frequency at the bottom


def _to_uint8(x: np.ndarray, axis: int | None = None) -> np.ndarray:
    lo = np.min(x, axis=axis, keepdims=axis is not None)
    hi = np.max(x, axis=axis, keepdims=axis is not None)
    span = np.where(hi - lo < 1e-12, 1.0, hi - lo)
    return np.clip(np.rint((x - lo) / span * 255.0), 0, 255).astype(np.uint8)


def stmap_preview_images(stmap: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two ``(P, T, 3)`` uint8 images (RGB triplet, signal triplet), rows min-max scaled."""
    rgb = np.stack([_to_uint8(stmap[c], axis=1) for c in range(0, 3)], axis=-1)
    sig = np.stack([_to_uint8(stmap[c], axis=1) for c in range(3, 6)], axis=-1)
    return rgb, sig


# ---------------------------------------------------------------------------
# PNG writing (no imaging dependency needed)
# ---------------------------------------------------------------------------


def write_png(path: str | Path, image: np.ndarray) -> None:
    """Write an 8-bit grayscale ``(H, W)`` or RGB ``(H, W, 3)`` array as PNG."""
    array = np.asarray(image)
    if array.dtype != np.uint8:
        raise ValueError("write_png expects uint8 data.")
    if array.ndim == 2:
        color_type, channels = 0, 1
    elif array.ndim == 3 and array.shape[2] == 3:
        color_type, channels = 2, 3
    else:
        raise ValueError(f"Unsupported image shape {array.shape}.")
    height, width = array.shape[:2]
    rows = array.reshape(height, width * channels)
    raw = b"".join(b"\x00" + rows[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def hr_bin_label(hr_bpm: float | None, has_pulse: bool = True) -> str:
    """``hr_070_079`` style bin, or ``no_pulse`` for negatives."""
    if not has_pulse or hr_bpm is None:
        return NO_PULSE
    low = int(np.clip(hr_bpm, HR_RANGE[0], HR_RANGE[1] - 1e-6) // HR_BIN_WIDTH * HR_BIN_WIDTH)
    return f"hr_{low:03d}_{low + HR_BIN_WIDTH - 1:03d}"


def quality_label(
    *,
    has_pulse: bool,
    reference_hr_bpm: float | None,
    estimated_hr_bpm: float | None,
    events: Iterable[DegradationEvent] = (),
    error_tolerance_bpm: float = 5.0,
) -> str:
    """Stage (a) class from the audit: no_pulse > motion > exposure_event > good/low_snr."""
    if not has_pulse:
        return NO_PULSE
    kinds = {event.kind for event in events}
    if "motion" in kinds:
        return "motion"
    if "exposure_event" in kinds:
        return "exposure_event"
    if (
        reference_hr_bpm is not None
        and estimated_hr_bpm is not None
        and abs(estimated_hr_bpm - reference_hr_bpm) <= error_tolerance_bpm
    ):
        return "good"
    return "low_snr"


def is_validation_subject(subject_id: str, valid_pct: float = 0.2) -> bool:
    """Deterministic, subject-disjoint split from a hash of the subject id."""
    digest = hashlib.sha256(subject_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < valid_pct


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@dataclass
class ExportSession:
    """Everything needed to export one session's windows."""

    session: DatasetSessionV2
    patch_traces: Mapping[str, Sequence[FrameSample]]
    has_pulse: bool = True
    reference_hr_bpm: Callable[[float, float], float | None] | float | None = None
    events: Sequence[DegradationEvent] = field(default_factory=tuple)


def _reference_for_window(
    reference: Callable[[float, float], float | None] | float | None, start_ms: float, end_ms: float
) -> float | None:
    if reference is None:
        return None
    if callable(reference):
        return reference(start_ms, end_ms)
    return float(reference)


def export_session_windows(
    item: ExportSession,
    out_dir: str | Path,
    *,
    window_s: float = WINDOW_S,
    hop_s: float = HOP_S,
    label_scheme: str = "quality",
    valid_pct: float = 0.2,
    min_valid_fraction: float = 0.5,
) -> list[dict[str, Any]]:
    """Write spectrogram, STMap and previews for every window; return label rows."""
    if label_scheme not in ("quality", "hr_bin"):
        raise ValueError("label_scheme must be 'quality' or 'hr_bin'.")
    root = Path(out_dir)
    session = item.session
    names = list(item.patch_traces)
    first = item.patch_traces[names[0]]
    t_start = max(min(f.t_ms for f in item.patch_traces[n]) for n in names)
    t_end = min(max(f.t_ms for f in item.patch_traces[n]) for n in names)
    span_s = (t_end - t_start) / 1000.0
    delivered_fps = (len(first) - 1) / span_s if span_s > 0 else 0.0
    is_valid = is_validation_subject(session.subject.subject_id, valid_pct)

    rows: list[dict[str, Any]] = []
    window_index = 0
    start = t_start
    while start + window_s * 1000.0 <= t_end + 1e-6:
        end = start + window_s * 1000.0
        window = resample_window(item.patch_traces, start, window_s)
        valid_fraction = float(np.mean(window.valid))
        if valid_fraction < min_valid_fraction:
            start += hop_s * 1000.0
            window_index += 1
            continue

        stmap = build_stmap(window)
        pulse = np.mean(stmap[3], axis=0)  # patch-averaged windowed POS
        spec = spectrogram_image(pulse)
        rgb_preview, sig_preview = stmap_preview_images(stmap)

        stem = f"{_safe(session.session_id)}_w{window_index:04d}"
        spec_rel = Path("spec") / f"{stem}.png"
        npy_rel = Path("stmap") / f"{stem}.npy"
        rgb_rel = Path("stmap_png") / f"{stem}_rgb.png"
        sig_rel = Path("stmap_png") / f"{stem}_sig.png"
        write_png(root / spec_rel, spec)
        (root / npy_rel).parent.mkdir(parents=True, exist_ok=True)
        np.save(root / npy_rel, stmap)
        write_png(root / rgb_rel, rgb_preview)
        write_png(root / sig_rel, sig_preview)

        reference_hr = _reference_for_window(item.reference_hr_bpm, start, end)
        pos_hr = dominant_hr_bpm(pulse, GRID_FS)
        window_events = [e for e in item.events if e.start_ms < end and e.end_ms > start]
        window_events = [e for e in window_events if e.kind != "flicker"]
        quality = quality_label(
            has_pulse=item.has_pulse,
            reference_hr_bpm=reference_hr,
            estimated_hr_bpm=pos_hr,
            events=window_events,
        )
        hr_bin = hr_bin_label(reference_hr, item.has_pulse)
        rows.append(
            {
                "fname": spec_rel.as_posix(),
                "stmap_npy": npy_rel.as_posix(),
                "stmap_rgb_png": rgb_rel.as_posix(),
                "stmap_sig_png": sig_rel.as_posix(),
                "label": quality if label_scheme == "quality" else hr_bin,
                "quality_label": quality,
                "hr_bin": hr_bin,
                "hr_bpm": (
                    "" if reference_hr is None or not item.has_pulse else round(reference_hr, 2)
                ),
                "has_pulse": int(item.has_pulse),
                "pos_hr_bpm": "" if pos_hr is None else pos_hr,
                "is_valid": is_valid,
                "session_id": session.session_id,
                "subject_id": session.subject.subject_id,
                "dataset": session.dataset,
                "licence": session.effective_licence,
                "split": session.split,
                "window_index": window_index,
                "window_start_ms": round(start, 3),
                "window_end_ms": round(end, 3),
                "n_patches": len(names),
                "valid_fraction": round(valid_fraction, 4),
                "delivered_fps": round(delivered_fps, 3),
                "fitzpatrick": (
                    "" if session.subject.fitzpatrick is None else session.subject.fitzpatrick
                ),
                "events": ";".join(sorted({e.kind for e in window_events})),
            }
        )
        start += hop_s * 1000.0
        window_index += 1
    return rows


def export_corpus(
    items: Sequence[ExportSession],
    out_dir: str | Path,
    *,
    purpose: Purpose = "research",
    window_s: float = WINDOW_S,
    hop_s: float = HOP_S,
    label_scheme: str = "quality",
    valid_pct: float = 0.2,
) -> Path:
    """Export every session and write ``labels.csv`` plus ``export_manifest.json``.

    With ``purpose="commercial_training"`` the whole export is refused before any
    file is written if a single session is bench_only or non-commercial.
    """
    if purpose not in ("commercial_training", "research"):
        raise ValueError(f"Unknown purpose '{purpose}'.")
    if purpose == "commercial_training":
        for item in items:
            check_commercial_training(
                dataset=item.session.dataset,
                licence=item.session.licence,
                split=item.session.split,
                session_id=item.session.session_id,
            )

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.extend(
            export_session_windows(
                item,
                root,
                window_s=window_s,
                hop_s=hop_s,
                label_scheme=label_scheme,
                valid_pct=valid_pct,
            )
        )

    with (root / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LABEL_FIELDS))
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    manifest = {
        "purpose": purpose,
        "label_scheme": label_scheme,
        "window_s": window_s,
        "hop_s": hop_s,
        "grid_fs": GRID_FS,
        "stmap_channels": list(STMAP_CHANNELS),
        "stmap_layout": "(C, P, T) float32",
        "spectrogram": {
            "size": SPEC_SIZE,
            "band_hz": list(SPEC_BAND_HZ),
            "stft_window_s": SPEC_WINDOW_S,
            "stft_hop_s": SPEC_HOP_S,
            "orientation": "row 0 = highest frequency",
        },
        "n_windows": len(rows),
        "label_counts": dict(sorted(counts.items())),
        "datasets": sorted({item.session.dataset for item in items}),
        "augmentation_note": "Do not flip or rotate: axes are time and frequency.",
    }
    (root / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root / "labels.csv"


def load_labels_for_training(
    labels_csv: str | Path, purpose: Purpose = "commercial_training"
) -> list[dict[str, str]]:
    """Read ``labels.csv`` and re-check every row before it can reach a DataLoader.

    The check uses each row's dataset name against the pinned licence registry, so a
    hand-edited ``licence`` or ``split`` column cannot smuggle in a non-commercial set.
    """
    with Path(labels_csv).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if purpose == "commercial_training":
        for row in rows:
            check_commercial_training(
                dataset=row["dataset"],
                licence=row["licence"],
                split=row["split"],
                session_id=row["session_id"],
            )
    elif purpose != "research":
        raise ValueError(f"Unknown purpose '{purpose}'.")
    return rows


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)


# ---------------------------------------------------------------------------
# Synthetic corpus (commercially usable: generated here, no third-party data)
# ---------------------------------------------------------------------------

SYNTHETIC_PATCHES = ("forehead", "left_cheek", "right_cheek")
DEFAULT_SYNTHETIC_PRESETS = (
    "flagship_reference",
    "budget_bright",
    "budget_india_indoor",
    "budget_dim_darker_skin",
    "budget_tubelight_flicker",
    "budget_motion",
    "budget_worst_case",
)


def synthetic_export_sessions(
    n_sessions: int,
    seed: int = 0,
    *,
    duration_s: float = 30.0,
    no_pulse_fraction: float = 0.25,
    presets: Sequence[str] = DEFAULT_SYNTHETIC_PRESETS,
) -> list[ExportSession]:
    """Deterministic synthetic sessions, degraded through the phone simulator.

    Each session draws an HR (50-120 BPM), a preset and pulse/no-pulse from the seed.
    Patch amplitudes differ (forehead strongest), as in real faces.
    """
    from learning.phase1.common import SyntheticScenarioConfig, generate_synthetic_frames

    rng = np.random.default_rng(seed)
    sessions: list[ExportSession] = []
    for index in range(n_sessions):
        hr = float(rng.uniform(50.0, 120.0))
        has_pulse = bool(rng.random() >= no_pulse_fraction)
        preset = presets[int(rng.integers(0, len(presets)))]
        session_seed = int(rng.integers(0, 2**31 - 1))
        patch_traces = {}
        for p, patch in enumerate(SYNTHETIC_PATCHES):
            scale = (1.0, 0.75, 0.75)[p] if has_pulse else 0.0
            patch_traces[patch] = generate_synthetic_frames(
                SyntheticScenarioConfig(
                    hr_bpm=hr,
                    fps=60.0,
                    duration_s=duration_s,
                    noise_std=0.05,
                    signal_scale=scale,
                    illumination_amplitude=0.25,
                    brightness_offset=float(rng.uniform(-10.0, 10.0)),
                    seed=session_seed + p,
                )
            )
        degraded = degrade_patch_traces(patch_traces, get_preset(preset), seed=session_seed)
        fitzpatrick = 5 if get_preset(preset).skin_ac_attenuation < 1.0 else 3
        session_id = f"synth_{seed}_{index:05d}"
        session = DatasetSessionV2(
            session_id=session_id,
            dataset="PranaScan-Synthetic",
            licence="synthetic_owned",
            capture=CaptureContext(
                device=f"simulated:{preset}",
                is_smartphone=True,
                codec="simulated_roi_means",
                nominal_fps=round(degraded.base_fps, 3),
                resolution=(1280, 720),
                lighting=preset,
            ),
            subject=SubjectContext(subject_id=session_id, fitzpatrick=fitzpatrick),
            split="train",
            metadata={"preset": preset, "seed": session_seed},
        )
        sessions.append(
            ExportSession(
                session=session,
                patch_traces=degraded.patch_frames,
                has_pulse=has_pulse,
                reference_hr_bpm=hr if has_pulse else None,
                events=degraded.events,
            )
        )
    return sessions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--synthetic-sessions", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-pulse-fraction", type=float, default=0.25)
    parser.add_argument("--label-scheme", choices=["quality", "hr_bin"], default="quality")
    parser.add_argument(
        "--purpose", choices=["research", "commercial_training"], default="research"
    )
    args = parser.parse_args()

    sessions = synthetic_export_sessions(
        args.synthetic_sessions, args.seed, no_pulse_fraction=args.no_pulse_fraction
    )
    try:
        labels = export_corpus(
            sessions, args.output_dir, purpose=args.purpose, label_scheme=args.label_scheme
        )
    except LicenceViolationError as exc:
        print(f"Refused: {exc}")
        return 2
    print(f"Wrote {labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
