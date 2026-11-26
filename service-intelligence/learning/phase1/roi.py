"""Offline ROI extraction experiments for saved selfie videos."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from app.services.rppg_processor import FrameSample, process_frames

from .common import ensure_output_dir, write_frame_samples_csv, write_json

PATCH_LAYOUTS: dict[str, tuple[float, float, float, float]] = {
    "forehead": (0.28, 0.12, 0.72, 0.30),
    "left_cheek": (0.14, 0.45, 0.36, 0.70),
    "right_cheek": (0.64, 0.45, 0.86, 0.70),
}


class OptionalDependencyError(RuntimeError):
    """Raised when optional ROI dependencies are missing."""


def extract_patch_trace_from_video(
    video_path: str | Path,
    patch_name: str = "forehead",
    roi_mode: str = "mediapipe",
    max_frames: int | None = None,
) -> list[FrameSample]:
    """Extract one patch trace from a saved video."""
    traces = extract_multi_patch_traces_from_video(
        video_path,
        patch_names=[patch_name],
        roi_mode=roi_mode,
        max_frames=max_frames,
    )
    return traces[patch_name]


def extract_multi_patch_traces_from_video(
    video_path: str | Path,
    patch_names: list[str] | tuple[str, ...] = ("forehead", "left_cheek", "right_cheek"),
    roi_mode: str = "mediapipe",
    max_frames: int | None = None,
) -> dict[str, list[FrameSample]]:
    """Extract RGB traces for multiple patches from a saved video."""
    if roi_mode != "mediapipe":
        raise ValueError("Only roi_mode='mediapipe' is supported in the current lab.")

    try:
        import cv2
    except ImportError as exc:
        raise OptionalDependencyError(
            "OpenCV is required for ROI extraction. Install service-intelligence/requirements-phase1.txt."
        ) from exc

    try:
        import mediapipe as mp
    except ImportError as exc:
        raise OptionalDependencyError(
            "MediaPipe is required for ROI extraction. Install service-intelligence/requirements-phase1.txt."
        ) from exc

    for patch_name in patch_names:
        if patch_name not in PATCH_LAYOUTS:
            available = ", ".join(sorted(PATCH_LAYOUTS))
            raise ValueError(f"Unknown patch '{patch_name}'. Available patches: {available}")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video '{video_path}'.")

    traces = {patch_name: [] for patch_name in patch_names}
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frame_index = 0
    try:
        while True:
            if max_frames is not None and frame_index >= max_frames:
                break

            success, frame_bgr = capture.read()
            if not success:
                break

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(frame_rgb)
            if not results.multi_face_landmarks:
                frame_index += 1
                continue

            h, w, _ = frame_rgb.shape
            landmarks = results.multi_face_landmarks[0].landmark
            xs = np.array([landmark.x * w for landmark in landmarks], dtype=np.float64)
            ys = np.array([landmark.y * h for landmark in landmarks], dtype=np.float64)

            x_min = max(0, int(np.floor(np.min(xs))))
            x_max = min(w, int(np.ceil(np.max(xs))))
            y_min = max(0, int(np.floor(np.min(ys))))
            y_max = min(h, int(np.ceil(np.max(ys))))
            if x_max <= x_min or y_max <= y_min:
                frame_index += 1
                continue

            timestamp_ms = float(
                capture.get(cv2.CAP_PROP_POS_MSEC) or ((frame_index / fps) * 1000.0)
            )
            for patch_name in patch_names:
                patch = _extract_relative_patch(
                    frame_rgb,
                    (x_min, y_min, x_max, y_max),
                    PATCH_LAYOUTS[patch_name],
                )
                if patch.size == 0:
                    continue
                mean_rgb = patch.reshape(-1, 3).mean(axis=0)
                traces[patch_name].append(
                    FrameSample(
                        t_ms=timestamp_ms,
                        r_mean=float(mean_rgb[0]),
                        g_mean=float(mean_rgb[1]),
                        b_mean=float(mean_rgb[2]),
                    )
                )

            frame_index += 1
    finally:
        face_mesh.close()
        capture.release()

    return traces


def summarize_patch_stability(
    traces: dict[str, list[FrameSample]],
) -> dict[str, dict[str, float | str | list[str] | None]]:
    """Score each patch using the existing production processor."""
    summary: dict[str, dict[str, float | str | list[str] | None]] = {}
    for patch_name, patch_frames in traces.items():
        result = process_frames(patch_frames)
        summary[patch_name] = {
            "frame_count": len(patch_frames),
            "hr_bpm": result.hr_bpm,
            "hrv_ms": result.hrv_ms,
            "respiratory_rate": result.respiratory_rate,
            "quality_score": result.quality_score,
            "flags": result.flags,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--patches",
        nargs="+",
        default=["forehead", "left_cheek", "right_cheek"],
    )
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    traces = extract_multi_patch_traces_from_video(
        args.video_path,
        patch_names=args.patches,
        max_frames=args.max_frames,
    )
    summary = summarize_patch_stability(traces)
    for patch_name, patch_frames in traces.items():
        write_frame_samples_csv(output_dir / f"{patch_name}_trace.csv", patch_frames)
    write_json(output_dir / "roi_summary.json", summary)
    return 0


def _extract_relative_patch(
    frame_rgb: np.ndarray,
    face_bbox: tuple[int, int, int, int],
    relative_box: tuple[float, float, float, float],
) -> np.ndarray:
    x_min, y_min, x_max, y_max = face_bbox
    face_width = max(x_max - x_min, 1)
    face_height = max(y_max - y_min, 1)
    rel_x0, rel_y0, rel_x1, rel_y1 = relative_box
    patch_x0 = max(0, int(x_min + face_width * rel_x0))
    patch_y0 = max(0, int(y_min + face_height * rel_y0))
    patch_x1 = min(frame_rgb.shape[1], int(x_min + face_width * rel_x1))
    patch_y1 = min(frame_rgb.shape[0], int(y_min + face_height * rel_y1))
    if patch_x1 <= patch_x0 or patch_y1 <= patch_y0:
        return np.empty((0, 0, 3), dtype=frame_rgb.dtype)
    return frame_rgb[patch_y0:patch_y1, patch_x0:patch_x1]


if __name__ == "__main__":
    raise SystemExit(main())
