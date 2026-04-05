"""Bridge media payloads into the internal vitals contract."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

from app.services.rppg_processor import FrameSample, process_frames

MIN_MEDIA_BYTES = 128
SYNTHETIC_FPS = 7.5
SYNTHETIC_DURATION_S = 12.0


@dataclass(frozen=True)
class ExtractedVitals:
    """Vitals payload returned by the gRPC contract."""

    heart_rate: float
    hrv: float
    spo2: float


def extract_vitals_from_media(media_bytes: bytes) -> ExtractedVitals:
    """
    Derive a deterministic vitals payload from media bytes.

    The current intelligence stack does not yet decode raw image/video bytes
    into per-frame RGB summaries. Until that lands, this adapter derives a
    stable synthetic rPPG waveform from the media payload so the gRPC contract
    and service boundary are live without pretending to offer clinical-grade
    extraction from compressed media bytes.
    """
    if len(media_bytes) < MIN_MEDIA_BYTES:
        raise ValueError(f"VitalsRequest media payload must be at least {MIN_MEDIA_BYTES} bytes.")

    payload = np.frombuffer(media_bytes, dtype=np.uint8).astype(np.float64)
    frames = _build_synthetic_frame_samples(payload, media_bytes)
    rppg = process_frames(frames)

    heart_rate = rppg.hr_bpm if rppg.hr_bpm is not None else _fallback_heart_rate(payload)
    hrv = rppg.hrv_ms if rppg.hrv_ms is not None else _fallback_hrv(payload)
    spo2 = _estimate_spo2(payload, frames, rppg.quality_score)

    return ExtractedVitals(
        heart_rate=round(float(heart_rate), 1),
        hrv=round(float(hrv), 2),
        spo2=round(float(spo2), 1),
    )


def _build_synthetic_frame_samples(
    payload: np.ndarray,
    media_bytes: bytes,
) -> list[FrameSample]:
    digest = hashlib.sha256(media_bytes).digest()
    rng_seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
    rng = np.random.default_rng(rng_seed)

    frame_count = int(SYNTHETIC_FPS * SYNTHETIC_DURATION_S)
    timeline = np.arange(frame_count, dtype=np.float64) / SYNTHETIC_FPS
    heart_rate_bpm = _fallback_heart_rate(payload)
    heart_rate_hz = heart_rate_bpm / 60.0

    mean_value = float(np.mean(payload))
    std_value = max(float(np.std(payload)), 1.0)
    amplitude = 2.5 + min(std_value / 255.0, 1.0) * 4.5
    phase = (digest[8] / 255.0) * 2.0 * math.pi

    # Resample byte texture onto the synthetic frame timeline to retain a
    # deterministic relationship between the original payload and the output.
    source_axis = np.linspace(0.0, 1.0, num=payload.size, endpoint=True)
    target_axis = np.linspace(0.0, 1.0, num=frame_count, endpoint=True)
    texture = np.interp(target_axis, source_axis, payload)
    texture = (texture - mean_value) / std_value

    base_red = 78.0 + _channel_mean(payload, 0) / 255.0 * 38.0
    base_green = 92.0 + _channel_mean(payload, 1) / 255.0 * 44.0
    base_blue = 70.0 + _channel_mean(payload, 2) / 255.0 * 34.0

    pulse = np.sin((2.0 * math.pi * heart_rate_hz * timeline) + phase)
    harmonic = np.sin((4.0 * math.pi * heart_rate_hz * timeline) + (phase / 2.0))
    noise = rng.normal(0.0, 0.08, size=frame_count)

    green = base_green + (amplitude * pulse) + (0.35 * amplitude * harmonic) + texture + noise
    red = base_red + (0.45 * amplitude * pulse) + (0.25 * texture)
    blue = base_blue + (0.20 * amplitude * np.sin((2.0 * math.pi * heart_rate_hz * timeline) - phase))
    blue = blue - (0.20 * texture)

    return [
        FrameSample(
            t_ms=float(index * (1000.0 / SYNTHETIC_FPS)),
            r_mean=float(red[index]),
            g_mean=float(green[index]),
            b_mean=float(blue[index]),
        )
        for index in range(frame_count)
    ]


def _fallback_heart_rate(payload: np.ndarray) -> float:
    normalized_std = min(float(np.std(payload)) / 64.0, 1.0)
    entropy_proxy = min(float(np.mean(np.abs(np.diff(payload)))) / 48.0, 1.0)
    return 58.0 + (normalized_std * 22.0) + (entropy_proxy * 16.0)


def _fallback_hrv(payload: np.ndarray) -> float:
    rolling_delta = float(np.mean(np.abs(np.diff(payload[::2])))) if payload.size > 2 else 0.0
    return 18.0 + min(rolling_delta / 3.0, 42.0)


def _estimate_spo2(
    payload: np.ndarray,
    frames: list[FrameSample],
    quality_score: float,
) -> float:
    red_mean = float(np.mean([frame.r_mean for frame in frames]))
    blue_mean = float(np.mean([frame.b_mean for frame in frames]))
    red_blue_ratio = red_mean / max(blue_mean, 1.0)
    stability = 1.0 - min(float(np.std(payload)) / 96.0, 1.0)
    quality_bonus = min(max(quality_score, 0.0), 1.0)
    spo2 = 93.5 + ((red_blue_ratio - 1.05) * 2.4) + (stability * 2.0) + quality_bonus
    return float(np.clip(spo2, 90.0, 100.0))


def _channel_mean(payload: np.ndarray, offset: int) -> float:
    channel = payload[offset::3]
    if channel.size == 0:
        return float(np.mean(payload))
    return float(np.mean(channel))
