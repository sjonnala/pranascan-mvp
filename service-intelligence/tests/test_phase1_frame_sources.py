from pathlib import Path

import numpy as np
import pytest

from learning.phase1.frame_sources import (
    ArrayFrameSource,
    MatArraySource,
    PngSequenceSource,
    timestamp_from_filename,
)
from learning.phase1.roi import PATCH_LAYOUTS, extract_multi_patch_traces_from_source


def _video(n=5, h=40, w=40):
    video = np.zeros((n, h, w, 3), dtype=np.uint8)
    for i in range(n):
        video[i, :, :, 0] = 100 + i
        video[i, :, :, 1] = 120 + i
        video[i, :, :, 2] = 80 + i
    return video


def test_array_source_keeps_true_timestamps():
    stamps = [0.0, 70.0, 120.0, 190.0, 260.0]  # variable frame rate
    source = ArrayFrameSource(video=_video(), timestamps_ms=stamps)
    assert [t for t, _ in source.frames()] == stamps


def test_array_source_falls_back_to_fps_only_without_timestamps():
    source = ArrayFrameSource(video=_video(), fps=20.0)
    assert [t for t, _ in source.frames()] == [0.0, 50.0, 100.0, 150.0, 200.0]


def test_array_source_converts_float_and_bgr_frames():
    video = _video().astype(np.float32) / 255.0
    source = ArrayFrameSource(video=video, fps=30.0, channel_order="bgr")
    _, frame = next(iter(source.frames()))
    assert frame.dtype == np.uint8
    assert frame[0, 0].tolist() == [80, 120, 100]


def test_array_source_validates_inputs():
    with pytest.raises(ValueError):
        ArrayFrameSource(video=np.zeros((4, 4, 3)), fps=30.0)
    with pytest.raises(ValueError):
        ArrayFrameSource(video=_video())
    with pytest.raises(ValueError):
        ArrayFrameSource(video=_video(), timestamps_ms=[0.0, 1.0])


def test_timestamp_from_filename_uses_last_digit_run():
    assert timestamp_from_filename("Image1392643993642815000.png") == pytest.approx(
        1392643993642.815
    )
    assert timestamp_from_filename("frame_12_000250.png", unit_ms=1.0) == 250.0
    with pytest.raises(ValueError):
        timestamp_from_filename("nodigits.png")


def test_png_sequence_source_sorts_by_timestamp(tmp_path: Path):
    cv2 = pytest.importorskip("cv2")
    for stamp in (3_000_000, 1_000_000, 2_000_000):
        frame = np.full((8, 8, 3), stamp // 1_000_000, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / f"Image{stamp}.png"), frame)
    source = PngSequenceSource(tmp_path)
    frames = list(source.frames())
    assert [t for t, _ in frames] == [1.0, 2.0, 3.0]
    assert [int(f[0, 0, 0]) for _, f in frames] == [1, 2, 3]


def test_mat_array_source_reorders_axes(tmp_path: Path):
    from scipy.io import savemat

    video = _video(n=3, h=6, w=10)
    savemat(tmp_path / "p1.mat", {"video": np.transpose(video, (0, 2, 1, 3))})  # [t, w, h, c]
    source = MatArraySource(tmp_path / "p1.mat", key="video", fps=30.0, layout="twhc")
    frames = list(source.frames())
    assert frames[0][1].shape == (6, 10, 3)
    assert frames[2][0] == pytest.approx(2000.0 / 30.0)
    with pytest.raises(KeyError):
        MatArraySource(tmp_path / "p1.mat", key="missing")


def test_roi_extraction_from_source_with_full_frame_mode():
    stamps = [0.0, 40.0, 95.0, 130.0, 170.0]
    source = ArrayFrameSource(video=_video(), timestamps_ms=stamps)
    traces = extract_multi_patch_traces_from_source(source, roi_mode="full_frame")
    assert set(traces) == set(PATCH_LAYOUTS)
    forehead = traces["forehead"]
    assert [s.t_ms for s in forehead] == stamps
    assert forehead[2].r_mean == pytest.approx(102.0)


def test_roi_extraction_skips_frames_without_a_face():
    source = ArrayFrameSource(video=_video(), fps=10.0)
    calls = iter([None, (0, 0, 40, 40), None, (0, 0, 40, 40), (0, 0, 40, 40)])
    traces = extract_multi_patch_traces_from_source(
        source, patch_names=["forehead"], face_box_detector=lambda frame: next(calls)
    )
    assert [s.t_ms for s in traces["forehead"]] == [100.0, 300.0, 400.0]


def test_roi_extraction_rejects_unknown_modes_and_patches():
    source = ArrayFrameSource(video=_video(), fps=10.0)
    with pytest.raises(ValueError):
        extract_multi_patch_traces_from_source(source, roi_mode="provided_mask")
    with pytest.raises(ValueError):
        extract_multi_patch_traces_from_source(source, patch_names=["chin"], roi_mode="full_frame")
