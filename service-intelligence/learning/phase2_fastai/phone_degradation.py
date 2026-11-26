"""Deterministic low-caliber smartphone simulator for rPPG RGB traces.

Takes a clean ROI-mean RGB trace (ideally 30 Hz or faster, from a lab dataset or a
synthetic generator) and returns what a budget Android phone in India would have
delivered for the same scene. Every effect is seeded, so the same input, config
and seed always produce the same output.

Effects, in physical order
--------------------------
1. Skin optics: darker-skin AC attenuation (melanin lowers the pulsatile
   amplitude, not its frequency) and an optional DC scale.
2. Scene: motion bursts (smooth luminance swings with a Hann envelope).
3. Lighting: dim light, and 100 Hz tube-light flicker from 50 Hz mains, sampled
   at the real capture instants and integrated over the exposure time. At 14 or
   17 FPS this aliases to |100 - 7*14| = |100 - 6*17| = 2 Hz, a false 120 BPM peak.
4. Camera: auto-exposure gain (partial compensation of dim light plus sudden
   AE steps) and auto-white-balance drift on the R and B gains.
5. Sensor: shot noise (scales with the pre-gain signal) and read noise, both
   amplified by the gain.
6. ISP: optional temporal noise reduction (first-order IIR).
7. Readout: 8-bit quantisation of a sampled set of ROI pixels, then averaging.
8. Delivery: 12-20 FPS with slow frame-rate wander, capture-time jitter,
   independent and burst frame drops, timestamps rounded to whole milliseconds.

Parameter ranges follow ``PranaScan-LowCaliber-Phone-Audit.md`` (Cycle 1). They
model mechanisms and orders of magnitude, not a specific handset.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

import numpy as np
from scipy import signal
from scipy.interpolate import CubicSpline

from app.services.rppg_processor import FrameSample

PULSE_BAND_HZ = (0.6, 4.5)


@dataclass(frozen=True)
class DegradationConfig:
    """Ranges are ``(low, high)`` and are sampled once per session from the seed."""

    # Delivery
    fps_range: tuple[float, float] = (12.0, 20.0)
    fps_wander: float = 0.12
    jitter_ms: float = 6.0
    drop_prob: float = 0.04
    drop_burst_prob: float = 0.004
    drop_burst_len: tuple[int, int] = (2, 6)
    # Readout
    bit_depth: int = 8
    roi_pixel_samples: int = 48
    pixel_dither_std: float = 0.8
    # Sensor
    shot_noise_coeff: float = 0.004
    read_noise_std: float = 0.2
    # ISP
    tnr_alpha: float = 0.0
    # Camera AE/AWB
    ae_compensation: float = 0.5
    ae_step_count: tuple[int, int] = (0, 3)
    ae_step_magnitude: tuple[float, float] = (0.04, 0.10)
    ae_step_ramp_s: float = 0.2
    awb_drift: tuple[float, float] = (0.0, 0.0)
    # Lighting
    light_scale: tuple[float, float] = (1.0, 1.0)
    flicker_hz: float = 100.0
    flicker_depth: tuple[float, float] = (0.0, 0.0)
    flicker_channel_gains: tuple[float, float, float] = (1.0, 0.95, 1.1)
    exposure_ms: tuple[float, float] = (4.0, 9.0)
    # Skin
    skin_ac_attenuation: float = 1.0
    skin_dc_scale: float = 1.0
    # Motion
    motion_burst_count: tuple[int, int] = (0, 0)
    motion_burst_duration_s: tuple[float, float] = (0.5, 2.0)
    motion_amplitude: float = 6.0

    def __post_init__(self) -> None:
        for name in (
            "fps_range",
            "drop_burst_len",
            "ae_step_count",
            "ae_step_magnitude",
            "awb_drift",
            "light_scale",
            "flicker_depth",
            "exposure_ms",
            "motion_burst_count",
            "motion_burst_duration_s",
        ):
            low, high = getattr(self, name)
            if low > high:
                raise ValueError(f"{name} must be (low, high) with low <= high.")
        if self.fps_range[0] <= 0:
            raise ValueError("fps_range must be positive.")
        if not 0.0 <= self.drop_prob < 1.0 or not 0.0 <= self.drop_burst_prob < 1.0:
            raise ValueError("drop probabilities must be in [0, 1).")
        if not 1 <= self.bit_depth <= 16:
            raise ValueError("bit_depth must be in 1..16.")
        if self.roi_pixel_samples < 1:
            raise ValueError("roi_pixel_samples must be >= 1.")
        if not 0.0 <= self.tnr_alpha < 1.0:
            raise ValueError("tnr_alpha must be in [0, 1).")
        if not 0.0 <= self.ae_compensation <= 1.0:
            raise ValueError("ae_compensation must be in [0, 1].")
        if self.light_scale[0] <= 0:
            raise ValueError("light_scale must be positive.")
        if self.skin_ac_attenuation < 0 or self.skin_dc_scale <= 0:
            raise ValueError("skin factors must be non-negative (DC scale positive).")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PRESETS: dict[str, DegradationConfig] = {
    "flagship_reference": DegradationConfig(
        fps_range=(30.0, 30.0),
        fps_wander=0.0,
        jitter_ms=1.0,
        drop_prob=0.0,
        drop_burst_prob=0.0,
        ae_step_count=(0, 0),
        pixel_dither_std=1.5,
    ),
    "budget_bright": DegradationConfig(),
    "budget_india_indoor": DegradationConfig(
        light_scale=(0.55, 0.8),
        ae_step_count=(1, 3),
        awb_drift=(0.02, 0.05),
        flicker_depth=(0.03, 0.08),
        tnr_alpha=0.3,
    ),
    "budget_dim_darker_skin": DegradationConfig(
        light_scale=(0.35, 0.55),
        skin_ac_attenuation=0.45,
        skin_dc_scale=0.7,
        ae_step_count=(1, 3),
        awb_drift=(0.02, 0.05),
        tnr_alpha=0.4,
    ),
    "budget_tubelight_flicker": DegradationConfig(
        light_scale=(0.6, 0.85),
        flicker_depth=(0.08, 0.15),
        exposure_ms=(2.0, 6.0),
    ),
    "budget_motion": DegradationConfig(
        motion_burst_count=(2, 4),
        motion_amplitude=8.0,
    ),
    "budget_worst_case": DegradationConfig(
        light_scale=(0.35, 0.55),
        skin_ac_attenuation=0.45,
        skin_dc_scale=0.7,
        ae_step_count=(2, 3),
        awb_drift=(0.03, 0.05),
        flicker_depth=(0.05, 0.12),
        exposure_ms=(2.0, 8.0),
        motion_burst_count=(1, 3),
        tnr_alpha=0.5,
        drop_prob=0.08,
    ),
}


def get_preset(name: str, **overrides: Any) -> DegradationConfig:
    """Look up a named preset, optionally overriding fields."""
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown preset '{name}'. Available presets: {available}")
    return replace(PRESETS[name], **overrides) if overrides else PRESETS[name]


@dataclass(frozen=True)
class DegradationEvent:
    """A labelled nuisance event, for window labels such as ``motion`` or ``exposure_event``."""

    kind: str
    start_ms: float
    end_ms: float
    magnitude: float


@dataclass(frozen=True)
class DegradedTrace:
    """Result of one simulated budget-phone capture.

    ``patch_frames`` holds one trace per ROI patch. All patches share the scene-wide
    effects (timing, drops, AE/AWB, flicker, motion) and get independent sensor noise.
    """

    patch_frames: dict[str, list[FrameSample]]
    capture_times_ms: np.ndarray
    base_fps: float
    events: list[DegradationEvent]
    session_params: dict[str, float]
    config: DegradationConfig
    seed: int
    dropped_count: int = 0
    nominal_frame_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def frames(self) -> list[FrameSample]:
        """The first (or only) patch's trace."""
        return next(iter(self.patch_frames.values()))

    @property
    def delivered_fps(self) -> float:
        if len(self.frames) < 2:
            return 0.0
        span_s = (self.frames[-1].t_ms - self.frames[0].t_ms) / 1000.0
        return (len(self.frames) - 1) / span_s if span_s > 0 else 0.0

    def events_overlapping(self, start_ms: float, end_ms: float) -> list[DegradationEvent]:
        return [e for e in self.events if e.start_ms < end_ms and e.end_ms > start_ms]


def frames_to_arrays(frames: Sequence[FrameSample]) -> tuple[np.ndarray, np.ndarray]:
    """``(t_s, rgb)`` arrays from frame samples, sorted and de-duplicated by time."""
    if len(frames) < 8:
        raise ValueError("Need at least 8 frames.")
    t_s = np.array([f.t_ms for f in frames], dtype=np.float64) / 1000.0
    rgb = np.array([[f.r_mean, f.g_mean, f.b_mean] for f in frames], dtype=np.float64)
    order = np.argsort(t_s, kind="stable")
    t_s, rgb = t_s[order], rgb[order]
    keep = np.concatenate([[True], np.diff(t_s) > 0])
    return t_s[keep], rgb[keep]


def degrade_trace(
    frames: Sequence[FrameSample],
    config: DegradationConfig | str = "budget_india_indoor",
    seed: int = 0,
) -> DegradedTrace:
    """Simulate a budget-phone capture of the scene described by a clean trace."""
    return degrade_patch_traces({"roi": frames}, config, seed)


def degrade_patch_traces(
    patch_traces: Mapping[str, Sequence[FrameSample]],
    config: DegradationConfig | str = "budget_india_indoor",
    seed: int = 0,
) -> DegradedTrace:
    """Simulate one capture for several ROI patches of the same face.

    Every patch is resampled onto the first patch's timeline. The result's
    ``patch_frames`` keeps the input patch names and order.
    """
    if not patch_traces:
        raise ValueError("patch_traces must contain at least one patch.")
    cfg = get_preset(config) if isinstance(config, str) else config
    rng = np.random.default_rng(seed)
    names = list(patch_traces)
    clean_t_s, first_rgb = frames_to_arrays(patch_traces[names[0]])
    columns = [first_rgb]
    for name in names[1:]:
        t_other, rgb_other = frames_to_arrays(patch_traces[name])
        columns.append(CubicSpline(t_other, rgb_other, axis=0)(clean_t_s))
    clean_rgb = np.concatenate(columns, axis=1)  # (T, 3P)
    n_patches = len(names)
    t0, t1 = float(clean_t_s[0]), float(clean_t_s[-1])
    duration_s = t1 - t0

    # -- per-session parameters (drawn in a fixed order for determinism) ----------
    base_fps = float(rng.uniform(*cfg.fps_range))
    light_scale = float(rng.uniform(*cfg.light_scale))
    flicker_depth = float(rng.uniform(*cfg.flicker_depth))
    exposure_s = float(rng.uniform(*cfg.exposure_ms)) / 1000.0
    flicker_phase = float(rng.uniform(0.0, 2.0 * math.pi))
    awb_drift = float(rng.uniform(*cfg.awb_drift))
    awb_sign = 1.0 if rng.random() < 0.5 else -1.0
    session_params = {
        "base_fps": base_fps,
        "light_scale": light_scale,
        "flicker_depth": flicker_depth,
        "exposure_ms": exposure_s * 1000.0,
        "awb_drift": awb_drift * awb_sign,
        "skin_ac_attenuation": cfg.skin_ac_attenuation,
    }

    # -- clean scene on a uniform grid ------------------------------------------
    clean_fs = 1.0 / float(np.median(np.diff(clean_t_s)))
    grid_fs = max(clean_fs, 30.0)
    grid = t0 + np.arange(int(math.floor(duration_s * grid_fs)) + 1) / grid_fs
    scene = CubicSpline(clean_t_s, clean_rgb, axis=0)(grid)
    scene = _apply_skin_optics(scene, grid_fs, cfg.skin_ac_attenuation, cfg.skin_dc_scale)

    events: list[DegradationEvent] = []
    scene = _apply_motion_bursts(scene, grid, cfg, rng, events)
    scene_at = CubicSpline(grid, scene, axis=0)

    # -- delivery timing --------------------------------------------------------
    nominal_times = _nominal_capture_times(t0, t1, base_fps, cfg, rng)
    capture_times = nominal_times + rng.normal(0.0, cfg.jitter_ms / 1000.0, nominal_times.size)
    capture_times = np.clip(capture_times, t0, t1)
    capture_times = _enforce_monotonic(np.sort(capture_times), min_gap_s=0.001)
    keep = _drop_mask(capture_times.size, cfg, rng)

    # The ISP sees every captured frame (dropped frames are lost later, in delivery).
    values = scene_at(capture_times)

    # -- lighting ---------------------------------------------------------------
    flicker = _flicker_multiplier(
        capture_times, cfg.flicker_hz, flicker_depth, exposure_s, flicker_phase
    )
    channel_gains = np.tile(np.asarray(cfg.flicker_channel_gains, dtype=np.float64), n_patches)
    illumination = light_scale * (1.0 + (flicker[:, None] - 1.0) * channel_gains[None, :])
    pre_gain = values * illumination

    # -- camera gain: AE compensation, AE steps, AWB -----------------------------
    ae_gain = (1.0 / light_scale) ** cfg.ae_compensation
    ae_profile = _ae_step_profile(capture_times, t0, t1, cfg, rng, events)
    awb = np.tile(_awb_gains(capture_times, t0, duration_s, awb_drift * awb_sign), (1, n_patches))
    gain = ae_gain * ae_profile[:, None] * awb

    # -- sensor noise (pre-gain) then gain ---------------------------------------
    shot_std = np.sqrt(np.clip(pre_gain, 0.0, None) * cfg.shot_noise_coeff)
    noise = rng.normal(0.0, 1.0, pre_gain.shape) * np.sqrt(shot_std**2 + cfg.read_noise_std**2)
    signal_dn = (pre_gain + noise) * gain

    # -- ISP temporal noise reduction ---------------------------------------------
    if cfg.tnr_alpha > 0.0:
        signal_dn = _temporal_noise_reduction(signal_dn, cfg.tnr_alpha)

    # -- 8-bit readout of sampled ROI pixels ------------------------------------
    signal_dn = _quantise_roi_means(signal_dn, cfg, rng)

    if flicker_depth > 0.0:
        events.append(DegradationEvent("flicker", t0 * 1000.0, t1 * 1000.0, flicker_depth))

    delivered_times = capture_times[keep]
    delivered = signal_dn[keep]
    t_ms = np.round(delivered_times * 1000.0)
    patch_frames = {
        name: [
            FrameSample(
                t_ms=float(t_ms[i]),
                r_mean=float(delivered[i, 3 * k]),
                g_mean=float(delivered[i, 3 * k + 1]),
                b_mean=float(delivered[i, 3 * k + 2]),
            )
            for i in range(delivered.shape[0])
        ]
        for k, name in enumerate(names)
    }
    events.sort(key=lambda e: (e.start_ms, e.kind))
    return DegradedTrace(
        patch_frames=patch_frames,
        capture_times_ms=delivered_times * 1000.0,
        base_fps=base_fps,
        events=events,
        session_params=session_params,
        config=cfg,
        seed=seed,
        dropped_count=int(np.sum(~keep)),
        nominal_frame_count=int(capture_times.size),
    )


def alias_frequency_hz(source_hz: float, fps: float) -> float:
    """Apparent frequency of ``source_hz`` when sampled at ``fps`` (folded to [0, fps/2])."""
    folded = math.fmod(source_hz, fps)
    return min(folded, fps - folded)


# ---------------------------------------------------------------------------
# Effect implementations
# ---------------------------------------------------------------------------


def _apply_skin_optics(
    scene: np.ndarray, fs: float, ac_attenuation: float, dc_scale: float
) -> np.ndarray:
    if ac_attenuation == 1.0 and dc_scale == 1.0:
        return scene
    nyquist = fs / 2.0
    high = min(PULSE_BAND_HZ[1], 0.9 * nyquist)
    sos = signal.butter(2, [PULSE_BAND_HZ[0] / nyquist, high / nyquist], btype="band", output="sos")
    pad = min(scene.shape[0] - 1, int(3 * fs))
    ac = signal.sosfiltfilt(sos, scene, axis=0, padlen=pad)
    rest = scene - ac
    return dc_scale * (rest + ac_attenuation * ac)


def _apply_motion_bursts(
    scene: np.ndarray,
    grid: np.ndarray,
    cfg: DegradationConfig,
    rng: np.random.Generator,
    events: list[DegradationEvent],
) -> np.ndarray:
    count = int(rng.integers(cfg.motion_burst_count[0], cfg.motion_burst_count[1] + 1))
    if count == 0:
        return scene
    out = scene.copy()
    t0, t1 = float(grid[0]), float(grid[-1])
    n_patches = scene.shape[1] // 3
    channel_weights = np.tile(np.array([0.8, 1.0, 0.6]), n_patches)
    for _ in range(count):
        duration = float(rng.uniform(*cfg.motion_burst_duration_s))
        start = float(rng.uniform(t0, max(t0, t1 - duration)))
        end = min(t1, start + duration)
        mask = (grid >= start) & (grid <= end)
        if not np.any(mask):
            continue
        local_t = grid[mask] - start
        envelope = np.hanning(int(np.sum(mask)) + 2)[1:-1]
        wobble = np.zeros_like(local_t)
        for _component in range(3):
            freq = float(rng.uniform(0.5, 3.0))
            phase = float(rng.uniform(0.0, 2.0 * math.pi))
            wobble += float(rng.uniform(0.4, 1.0)) * np.sin(2.0 * math.pi * freq * local_t + phase)
        wobble /= max(float(np.max(np.abs(wobble))), 1e-9)
        amplitude = cfg.motion_amplitude * float(rng.uniform(0.6, 1.0))
        out[mask] += (amplitude * envelope * wobble)[:, None] * channel_weights[None, :]
        events.append(DegradationEvent("motion", start * 1000.0, end * 1000.0, amplitude))
    return out


def _nominal_capture_times(
    t0: float, t1: float, base_fps: float, cfg: DegradationConfig, rng: np.random.Generator
) -> np.ndarray:
    n_estimate = int(math.ceil((t1 - t0) * base_fps * 1.5)) + 4
    if cfg.fps_wander > 0.0:
        steps = rng.normal(0.0, 1.0, n_estimate)
        walk = np.cumsum(steps)
        kernel = np.hanning(max(3, int(base_fps * 2)))
        walk = np.convolve(walk - np.mean(walk), kernel / kernel.sum(), mode="same")
        span = float(np.max(np.abs(walk)))
        wander = walk / span if span > 1e-9 else np.zeros_like(walk)
        fps_series = base_fps * (1.0 + cfg.fps_wander * wander)
    else:
        fps_series = np.full(n_estimate, base_fps)
    fps_series = np.clip(fps_series, 0.5 * cfg.fps_range[0], 1.5 * cfg.fps_range[1])
    times = t0 + np.concatenate([[0.0], np.cumsum(1.0 / fps_series)])
    return times[times <= t1]


def _enforce_monotonic(times: np.ndarray, min_gap_s: float) -> np.ndarray:
    out = times.copy()
    for i in range(1, out.size):
        if out[i] - out[i - 1] < min_gap_s:
            out[i] = out[i - 1] + min_gap_s
    return out


def _drop_mask(n: int, cfg: DegradationConfig, rng: np.random.Generator) -> np.ndarray:
    keep = rng.random(n) >= cfg.drop_prob
    if cfg.drop_burst_prob > 0.0:
        starts = np.flatnonzero(rng.random(n) < cfg.drop_burst_prob)
        for start in starts:
            length = int(rng.integers(cfg.drop_burst_len[0], cfg.drop_burst_len[1] + 1))
            keep[start : start + length] = False
    keep[0] = True
    keep[-1] = True
    return keep


def _flicker_multiplier(
    times_s: np.ndarray, flicker_hz: float, depth: float, exposure_s: float, phase: float
) -> np.ndarray:
    """Mean of ``1 + depth*cos(2*pi*f*t + phase)`` over the exposure ``[t - T, t]``."""
    if depth <= 0.0:
        return np.ones_like(times_s)
    attenuation = float(np.sinc(flicker_hz * exposure_s)) if exposure_s > 0 else 1.0
    centre = times_s - exposure_s / 2.0
    return 1.0 + depth * attenuation * np.cos(2.0 * math.pi * flicker_hz * centre + phase)


def _ae_step_profile(
    times_s: np.ndarray,
    t0: float,
    t1: float,
    cfg: DegradationConfig,
    rng: np.random.Generator,
    events: list[DegradationEvent],
) -> np.ndarray:
    profile = np.ones_like(times_s)
    count = int(rng.integers(cfg.ae_step_count[0], cfg.ae_step_count[1] + 1))
    level = 1.0
    step_times = np.sort(rng.uniform(t0 + 0.1 * (t1 - t0), t1 - 0.1 * (t1 - t0), count))
    for step_t in step_times:
        magnitude = float(rng.uniform(*cfg.ae_step_magnitude))
        sign = 1.0 if rng.random() < 0.5 else -1.0
        new_level = level * (1.0 + sign * magnitude)
        ramp = np.clip((times_s - step_t) / max(cfg.ae_step_ramp_s, 1e-6), 0.0, 1.0)
        profile = profile * (1.0 + (new_level / level - 1.0) * ramp)
        events.append(
            DegradationEvent(
                "exposure_event",
                float(step_t) * 1000.0,
                float(step_t + cfg.ae_step_ramp_s) * 1000.0,
                sign * magnitude,
            )
        )
        level = new_level
    return profile


def _awb_gains(times_s: np.ndarray, t0: float, duration_s: float, drift: float) -> np.ndarray:
    progress = (times_s - t0) / max(duration_s, 1e-9)
    gains = np.ones((times_s.size, 3))
    gains[:, 0] = 1.0 + drift * progress
    gains[:, 2] = 1.0 - drift * progress
    return gains


def _temporal_noise_reduction(values: np.ndarray, alpha: float) -> np.ndarray:
    """First-order IIR, like an ISP's temporal NR: y[n] = (1-a)*x[n] + a*y[n-1]."""
    b = np.array([1.0 - alpha])
    a = np.array([1.0, -alpha])
    zi = signal.lfilter_zi(b, a)[:, None] * values[0][None, :]
    filtered, _ = signal.lfilter(b, a, values, axis=0, zi=zi)
    return filtered


def _quantise_roi_means(
    values: np.ndarray, cfg: DegradationConfig, rng: np.random.Generator
) -> np.ndarray:
    max_code = float(2**cfg.bit_depth - 1)
    scale = max_code / 255.0  # values are expressed on an 8-bit scale
    samples = cfg.roi_pixel_samples
    dither = rng.normal(0.0, cfg.pixel_dither_std, (values.shape[0], values.shape[1], samples))
    pixels = np.clip(np.rint((values[:, :, None] + dither) * scale), 0.0, max_code)
    return np.mean(pixels, axis=2) / scale
