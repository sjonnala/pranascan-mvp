"""Frame-source adapters for the ``FrameSource`` port (dossier gaps G5 and G6).

Every adapter yields ``(t_ms, frame)`` where ``frame`` is an ``HxWx3`` ``uint8`` RGB
array and ``t_ms`` is the source's own timestamp. Real timing always wins over
synthesised timing: an adapter only falls back to ``index / fps`` when the source
carries no timestamps at all.

Adapters
--------
- ``VideoFileSource``: any cv2-readable video (UBFC, COHFACE, MCD-rPPG phone stream).
- ``TimestampedVideoSource``: a video plus a stored per-frame timestamp list
  (LGI-PPGI, phone captures with variable frame rate).
- ``PngSequenceSource``: a folder of images whose file names carry timestamps (PURE).
- ``ArrayFrameSource``: an in-memory ``(T, H, W, 3)`` array, e.g. MMPD/SCAMPS ``.mat``
  content, with explicit timestamps or a nominal fps.
- ``MatArraySource``: loads a ``.mat`` array with ``scipy.io.loadmat`` then behaves
  like ``ArrayFrameSource``.

File-format details for public datasets are unverified conventions ([U] in the
dossier). Check them against the files you download.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class OptionalDependencyError(RuntimeError):
    """Raised when an optional decoding dependency (OpenCV) is missing."""


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise OptionalDependencyError(
            "OpenCV is required for this frame source. "
            "Install service-intelligence/requirements-phase1.txt."
        ) from exc
    return cv2


def _as_rgb_uint8(frame: np.ndarray) -> np.ndarray:
    array = np.asarray(frame)
    if array.ndim == 2:
        array = np.repeat(array[:, :, None], 3, axis=2)
    if array.ndim != 3 or array.shape[2] < 3:
        raise ValueError(f"Expected an HxWx3 frame, got shape {array.shape}.")
    array = array[:, :, :3]
    if array.dtype != np.uint8:
        if np.issubdtype(array.dtype, np.floating) and float(np.nanmax(array)) <= 1.0 + 1e-6:
            array = array * 255.0
        array = np.clip(np.rint(array), 0, 255).astype(np.uint8)
    return array


@dataclass
class VideoFileSource:
    """A cv2-readable video. Uses the container timestamp, then ``index / fps``."""

    path: Path
    max_frames: int | None = None

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        cv2 = _require_cv2()
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            raise ValueError(f"Unable to open video '{self.path}'.")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
        index = 0
        try:
            while self.max_frames is None or index < self.max_frames:
                success, frame_bgr = capture.read()
                if not success:
                    break
                position_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
                t_ms = position_ms if (position_ms > 0.0 or index == 0) else index * 1000.0 / fps
                yield t_ms, cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                index += 1
        finally:
            capture.release()


@dataclass
class TimestampedVideoSource:
    """A video whose true per-frame timestamps are stored separately (LGI-PPGI)."""

    path: Path
    timestamps_ms: Sequence[float]

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        cv2 = _require_cv2()
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            raise ValueError(f"Unable to open video '{self.path}'.")
        try:
            for t_ms in self.timestamps_ms:
                success, frame_bgr = capture.read()
                if not success:
                    break
                yield float(t_ms), cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        finally:
            capture.release()


_DIGITS = re.compile(r"(\d+)")


def timestamp_from_filename(name: str, unit_ms: float = 1e-6) -> float:
    """Return the last digit run in a file name, scaled to milliseconds.

    PURE names frames by a nanosecond timestamp [U], hence ``unit_ms=1e-6``.
    """
    matches = _DIGITS.findall(Path(name).stem)
    if not matches:
        raise ValueError(f"No timestamp digits in file name '{name}'.")
    return float(int(matches[-1])) * unit_ms


@dataclass
class PngSequenceSource:
    """A folder of frames named by timestamp (PURE). Sorted by the parsed timestamp."""

    directory: Path
    pattern: str = "*.png"
    unit_ms: float = 1e-6

    def sorted_files(self) -> list[tuple[float, Path]]:
        files = [
            (timestamp_from_filename(path.name, self.unit_ms), path)
            for path in Path(self.directory).glob(self.pattern)
        ]
        files.sort(key=lambda item: item[0])
        return files

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        cv2 = _require_cv2()
        for t_ms, path in self.sorted_files():
            frame_bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if frame_bgr is None:
                raise ValueError(f"Unable to read frame '{path}'.")
            yield t_ms, cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)


@dataclass
class ArrayFrameSource:
    """An in-memory video array ``(T, H, W, 3)`` with timestamps or a nominal fps."""

    video: np.ndarray
    timestamps_ms: Sequence[float] | None = None
    fps: float | None = None
    channel_order: str = "rgb"

    def __post_init__(self) -> None:
        if self.video.ndim != 4:
            raise ValueError(f"Expected a (T, H, W, C) array, got shape {self.video.shape}.")
        if self.timestamps_ms is None and (self.fps is None or self.fps <= 0):
            raise ValueError("Provide timestamps_ms or a positive fps.")
        if self.timestamps_ms is not None and len(self.timestamps_ms) != self.video.shape[0]:
            raise ValueError("timestamps_ms must have one entry per frame.")
        if self.channel_order not in ("rgb", "bgr"):
            raise ValueError("channel_order must be 'rgb' or 'bgr'.")

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        for index in range(self.video.shape[0]):
            t_ms = (
                float(self.timestamps_ms[index])
                if self.timestamps_ms is not None
                else index * 1000.0 / float(self.fps)  # type: ignore[arg-type]
            )
            frame = self.video[index]
            if self.channel_order == "bgr":
                frame = frame[:, :, ::-1]
            yield t_ms, _as_rgb_uint8(frame)


def MatArraySource(  # noqa: N802 - factory named like the adapter it returns
    path: str | Path,
    key: str,
    fps: float | None = 30.0,
    timestamps_ms: Sequence[float] | None = None,
    layout: str = "thwc",
) -> ArrayFrameSource:
    """Load a ``.mat`` video array (MMPD ``video``, SCAMPS ``RawFrames``) into a source.

    ``layout`` names the stored axis order. MMPD documents ``[t, w, h, c]`` [V];
    pass ``layout="twhc"`` for it. SCAMPS ``RawFrames`` layout is unverified.
    MATLAB v7.3 files are HDF5 and need ``h5py``; this loader handles v5 files.
    """
    from scipy.io import loadmat

    content = loadmat(str(path))
    if key not in content:
        raise KeyError(f"Key '{key}' not found in '{path}'.")
    video = np.asarray(content[key])
    order = layout.lower()
    if sorted(order) != sorted("thwc"):
        raise ValueError("layout must be a permutation of 'thwc'.")
    video = np.transpose(video, [order.index(axis) for axis in "thwc"])
    return ArrayFrameSource(video=video, timestamps_ms=timestamps_ms, fps=fps)
