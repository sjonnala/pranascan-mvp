import csv
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from app.services.rppg_processor import FrameSample
from learning.phase1.common import SyntheticScenarioConfig, generate_synthetic_frames
from learning.phase1.dataset_model import (
    CaptureContext,
    DatasetSessionV2,
    LicenceViolationError,
    SubjectContext,
)
from learning.phase2_fastai.phone_degradation import DegradationEvent
from learning.phase2_fastai.stmap_export import (
    LABEL_FIELDS,
    NO_PULSE,
    QUALITY_CLASSES,
    SPEC_SIZE,
    STMAP_CHANNELS,
    ExportSession,
    build_stmap,
    dominant_hr_bpm,
    export_corpus,
    hr_bin_label,
    is_validation_subject,
    load_labels_for_training,
    quality_label,
    resample_window,
    spectrogram_image,
    synthetic_export_sessions,
    windowed_chrom,
    windowed_pos,
    write_png,
)


def _read_png(path: Path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, chunks = 8, {}
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        tag = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        (crc,) = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF
        chunks.setdefault(tag, b"")
        chunks[tag] += body
        offset += 12 + length
    width, height, depth, color_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    channels = 1 if color_type == 0 else 3
    raw = zlib.decompress(chunks[b"IDAT"])
    stride = width * channels + 1
    rows = [raw[y * stride + 1 : (y + 1) * stride] for y in range(height)]
    assert all(raw[y * stride] == 0 for y in range(height))
    pixels = np.frombuffer(b"".join(rows), dtype=np.uint8).reshape(height, width, channels)
    return width, height, depth, color_type, pixels


def _traces(hr=72.0, scale=1.0, duration_s=30.0, fps=30.0, patches=("forehead", "cheek")):
    return {
        name: generate_synthetic_frames(
            SyntheticScenarioConfig(
                hr_bpm=hr,
                fps=fps,
                duration_s=duration_s,
                noise_std=0.05,
                signal_scale=scale,
                seed=10 + i,
            )
        )
        for i, name in enumerate(patches)
    }


def _session(dataset="PranaScan-Synthetic", licence="synthetic_owned", split="train", sid="s1"):
    return DatasetSessionV2(
        session_id=sid,
        dataset=dataset,
        licence=licence,
        capture=CaptureContext(
            device="test", is_smartphone=True, codec="raw", nominal_fps=30.0, resolution=(640, 480)
        ),
        subject=SubjectContext(subject_id=f"subj_{sid}", fitzpatrick=4),
        split=split,
    )


def test_write_png_produces_valid_grayscale_and_rgb(tmp_path: Path):
    gray = np.arange(64 * 32, dtype=np.uint8).reshape(32, 64)
    write_png(tmp_path / "g.png", gray)
    width, height, depth, color_type, pixels = _read_png(tmp_path / "g.png")
    assert (width, height, depth, color_type) == (64, 32, 8, 0)
    assert np.array_equal(pixels[:, :, 0], gray)

    rgb = np.random.default_rng(0).integers(0, 255, (5, 7, 3), dtype=np.uint8)
    write_png(tmp_path / "c.png", rgb)
    assert np.array_equal(_read_png(tmp_path / "c.png")[4], rgb)

    with pytest.raises(ValueError):
        write_png(tmp_path / "bad.png", gray.astype(np.float32))


def test_windowed_pos_and_chrom_recover_the_pulse():
    window = resample_window(_traces(hr=84.0), start_ms=0.0)
    rgb = window.rgb[0]
    assert abs(dominant_hr_bpm(windowed_pos(rgb, 30.0), 30.0) - 84.0) <= 3.0
    assert abs(dominant_hr_bpm(windowed_chrom(rgb, 30.0), 30.0) - 84.0) <= 3.0


def test_resample_window_marks_delivery_gaps_invalid():
    traces = _traces(patches=("forehead",))
    frames = traces["forehead"]
    gapped = [f for f in frames if not 3000.0 < f.t_ms < 4500.0]
    window = resample_window({"forehead": gapped}, start_ms=0.0)
    assert window.rgb.shape == (1, 300, 3)
    in_gap = (window.grid_ms > 3100.0) & (window.grid_ms < 4400.0)
    assert not window.valid[0, in_gap].any()
    outside = (window.grid_ms < 2990.0) | (window.grid_ms > 4510.0)
    assert window.valid[0, outside].all()


def test_stmap_shape_channels_and_spectrogram_peak():
    window = resample_window(_traces(hr=90.0, patches=("a", "b", "c")), start_ms=0.0)
    stmap = build_stmap(window)
    assert stmap.shape == (len(STMAP_CHANNELS), 3, 300)
    assert stmap.dtype == np.float32
    assert np.allclose(stmap[3:].mean(axis=2), 0.0, atol=1e-5)

    spec = spectrogram_image(stmap[3].mean(axis=0))
    assert spec.shape == (SPEC_SIZE, SPEC_SIZE) and spec.dtype == np.uint8
    # Row 0 is the highest frequency; 1.5 Hz in a 0.5-4.5 Hz band sits 25% up from the bottom.
    peak_row = int(np.argmax(spec.astype(float).mean(axis=1)))
    expected_row = round((1 - (1.5 - 0.5) / 4.0) * (SPEC_SIZE - 1))
    assert abs(peak_row - expected_row) <= 3


def test_hr_bins_and_quality_priority():
    assert hr_bin_label(72.4) == "hr_070_079"
    assert hr_bin_label(30.0) == "hr_040_049"
    assert hr_bin_label(250.0) == "hr_170_179"
    assert hr_bin_label(80.0, has_pulse=False) == NO_PULSE
    assert hr_bin_label(None) == NO_PULSE

    motion = DegradationEvent("motion", 0, 1, 1.0)
    exposure = DegradationEvent("exposure_event", 0, 1, 0.1)
    assert (
        quality_label(has_pulse=False, reference_hr_bpm=None, estimated_hr_bpm=70, events=[motion])
        == NO_PULSE
    )
    assert (
        quality_label(
            has_pulse=True, reference_hr_bpm=70, estimated_hr_bpm=70, events=[exposure, motion]
        )
        == "motion"
    )
    assert (
        quality_label(has_pulse=True, reference_hr_bpm=70, estimated_hr_bpm=70, events=[exposure])
        == "exposure_event"
    )
    assert quality_label(has_pulse=True, reference_hr_bpm=70, estimated_hr_bpm=74) == "good"
    assert quality_label(has_pulse=True, reference_hr_bpm=70, estimated_hr_bpm=90) == "low_snr"
    assert quality_label(has_pulse=True, reference_hr_bpm=None, estimated_hr_bpm=90) == "low_snr"


def test_validation_split_is_deterministic_and_roughly_sized():
    subjects = [f"subject_{i}" for i in range(2000)]
    flags = [is_validation_subject(s) for s in subjects]
    assert flags == [is_validation_subject(s) for s in subjects]
    assert 0.17 < np.mean(flags) < 0.23


def test_export_corpus_writes_fastai_ready_files(tmp_path: Path):
    items = [
        ExportSession(
            _session(sid="pulse"), _traces(hr=75.0), has_pulse=True, reference_hr_bpm=75.0
        ),
        ExportSession(_session(sid="nopulse"), _traces(scale=0.0), has_pulse=False),
    ]
    labels_csv = export_corpus(items, tmp_path, purpose="commercial_training")
    with labels_csv.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert tuple(reader.fieldnames) == LABEL_FIELDS
    # 30 s traces, 10 s windows, 2 s hop -> 11 windows per session at most.
    assert 18 <= len(rows) <= 22
    labels = {row["label"] for row in rows}
    assert NO_PULSE in labels
    assert labels <= set(QUALITY_CLASSES)
    pulse_rows = [r for r in rows if r["session_id"] == "pulse"]
    assert sum(r["label"] == "good" for r in pulse_rows) >= 0.8 * len(pulse_rows)
    assert all(r["hr_bin"] == "hr_070_079" for r in pulse_rows)
    assert all(
        r["hr_bpm"] == "" and r["has_pulse"] == "0" for r in rows if r["session_id"] == "nopulse"
    )
    for row in rows[:3]:
        assert _read_png(tmp_path / row["fname"])[:2] == (SPEC_SIZE, SPEC_SIZE)
        assert np.load(tmp_path / row["stmap_npy"]).shape == (6, 2, 300)
        assert (tmp_path / row["stmap_rgb_png"]).exists()
        assert (tmp_path / row["stmap_sig_png"]).exists()
    manifest = json.loads((tmp_path / "export_manifest.json").read_text())
    assert manifest["n_windows"] == len(rows)
    assert manifest["purpose"] == "commercial_training"
    assert manifest["stmap_channels"] == list(STMAP_CHANNELS)


def test_commercial_export_refuses_a_non_commercial_session_before_writing(tmp_path: Path):
    items = [
        ExportSession(_session(sid="ok"), _traces(), reference_hr_bpm=72.0),
        ExportSession(
            _session(dataset="MMPD", licence="research_only", split="bench_only", sid="mmpd"),
            _traces(),
            reference_hr_bpm=72.0,
        ),
    ]
    out = tmp_path / "out"
    with pytest.raises(LicenceViolationError):
        export_corpus(items, out, purpose="commercial_training")
    assert not out.exists()
    # The same corpus is fine for research benchmarking.
    export_corpus(items, out, purpose="research")
    assert (out / "labels.csv").exists()


def test_training_loader_rechecks_rows_against_the_registry(tmp_path: Path):
    items = [ExportSession(_session(sid="ok"), _traces(), reference_hr_bpm=72.0)]
    labels_csv = export_corpus(items, tmp_path, purpose="commercial_training")
    assert load_labels_for_training(labels_csv)

    with labels_csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0].update({"dataset": "UBFC-rPPG", "licence": "cc_by_4_0", "split": "train"})
    with labels_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LABEL_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(LicenceViolationError):
        load_labels_for_training(labels_csv)
    assert len(load_labels_for_training(labels_csv, purpose="research")) == len(rows)


def test_irregular_low_fps_input_is_handled():
    frames = generate_synthetic_frames(
        SyntheticScenarioConfig(hr_bpm=66.0, fps=15.0, irregular_timestamps=True, noise_std=0.05)
    )
    window = resample_window({"forehead": frames}, start_ms=frames[0].t_ms)
    stmap = build_stmap(window)
    assert np.isfinite(stmap).all()
    assert abs(dominant_hr_bpm(stmap[3, 0], 30.0) - 66.0) <= 4.0


def test_synthetic_sessions_are_deterministic_and_commercially_clean(tmp_path: Path):
    a = synthetic_export_sessions(4, seed=7, duration_s=20.0)
    b = synthetic_export_sessions(4, seed=7, duration_s=20.0)
    assert [s.session.session_id for s in a] == [s.session.session_id for s in b]
    assert a[0].patch_traces == b[0].patch_traces
    assert all(s.session.commercial_training_allowed for s in a)
    assert all(len(s.patch_traces) == 3 for s in a)
    labels_csv = export_corpus(a, tmp_path, purpose="commercial_training")
    rows = load_labels_for_training(labels_csv)
    assert {r["dataset"] for r in rows} == {"PranaScan-Synthetic"}
    assert all(r["n_patches"] == "3" for r in rows)


def test_frame_sample_input_type_is_the_production_one():
    traces = _traces(patches=("forehead",))
    assert isinstance(traces["forehead"][0], FrameSample)
