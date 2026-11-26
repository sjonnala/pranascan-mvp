"""Estimator port for the eval kit, with adapters for classical, I30 and learned models.

Ubiquitous language
-------------------
- ``Estimate``: one method's answer for one trace segment. ``hr_bpm is None`` means the method
  abstained. ``raw_hr_bpm`` is what it would have said before abstaining (used for
  risk-coverage and calibration). ``confidence`` is the method's own score in ``[0, 1]``.
- ``EstimatorSpec``: anything that turns ``(t_s, rgb)`` into ``{method: Estimate}``. One spec
  may produce several methods at once (the four classical baselines share preprocessing).

Classical baselines (``green``, ``chrom``, ``pos``, ``ica``) come from
``learning.phase1.baselines.compare_methods`` unchanged. They always answer when a peak exists;
their ``confidence`` is the spectral quality score (cardiac-band power fraction), which is not a
calibrated probability. ``pbv_i30`` is the Cycle-1 DSP-autoresearch winner with its own logistic
confidence and abstention. Learned models plug in through ``ModelEstimator`` (any callable),
``ModelEstimator.from_onnx`` or ``ModelEstimator.from_torch``; torch and onnxruntime are imported
only when used.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

from app.services.rppg_processor import FrameSample

from . import pbv_i30

CLASSICAL_METHODS: tuple[str, ...] = ("green", "chrom", "pos", "ica")
PBV_METHOD = "pbv_i30"
BUILTIN_METHODS: tuple[str, ...] = (*CLASSICAL_METHODS, PBV_METHOD)

HR_BIN_MIN_BPM = 40
HR_BIN_MAX_BPM = 180
N_HR_BINS = HR_BIN_MAX_BPM - HR_BIN_MIN_BPM + 1  # 141 one-BPM bins
N_CLASSES_WITH_ABSTAIN = N_HR_BINS + 1  # 142nd class = no_pulse / abstain


@dataclass(frozen=True)
class Estimate:
    """One method's answer for one segment."""

    method: str
    hr_bpm: float | None
    confidence: float
    raw_hr_bpm: float | None = None
    flags: tuple[str, ...] = ()

    @property
    def abstained(self) -> bool:
        return self.hr_bpm is None


@runtime_checkable
class EstimatorSpec(Protocol):
    """Port: produce estimates for one or more methods from one trace segment."""

    methods: tuple[str, ...]

    def estimate(self, t_s: np.ndarray, rgb: np.ndarray) -> dict[str, Estimate]: ...


def _abstain_all(methods: Iterable[str], flag: str) -> dict[str, Estimate]:
    return {m: Estimate(m, None, float("nan"), None, (flag,)) for m in methods}


def _frames_from_arrays(t_s: np.ndarray, rgb: np.ndarray) -> list[FrameSample]:
    return [
        FrameSample(
            t_ms=float(t * 1000.0), r_mean=float(c[0]), g_mean=float(c[1]), b_mean=float(c[2])
        )
        for t, c in zip(t_s, rgb, strict=True)
    ]


@dataclass(frozen=True)
class ClassicalEstimator:
    """``learning.phase1.baselines.compare_methods`` for a subset of green/chrom/pos/ica."""

    methods: tuple[str, ...] = CLASSICAL_METHODS

    def __post_init__(self) -> None:
        unknown = set(self.methods) - set(CLASSICAL_METHODS)
        if unknown:
            raise ValueError(f"Unknown classical methods: {sorted(unknown)}")

    def estimate(self, t_s: np.ndarray, rgb: np.ndarray) -> dict[str, Estimate]:
        from learning.phase1.baselines import compare_methods

        try:
            report = compare_methods(_frames_from_arrays(t_s, rgb))
        except ValueError as exc:  # insufficient_frames, flat_signal, irregular_timestamps
            return _abstain_all(self.methods, str(exc) or "invalid_trace")
        out: dict[str, Estimate] = {}
        for method in self.methods:
            est = report[method]
            out[method] = Estimate(
                method=method,
                hr_bpm=est.hr_bpm,
                confidence=float(est.quality_score),
                raw_hr_bpm=est.hr_bpm,
                flags=tuple(est.flags),
            )
        return out


@dataclass(frozen=True)
class PbvI30Estimator:
    """Cycle-1 winner I30 (windowed PBV, exposure repair, logistic abstention)."""

    tau: float = pbv_i30.TAU
    methods: tuple[str, ...] = (PBV_METHOD,)

    def estimate(self, t_s: np.ndarray, rgb: np.ndarray) -> dict[str, Estimate]:
        result = pbv_i30.estimate_hr(t_s, rgb, tau=self.tau)
        conf = result.confidence if math.isfinite(result.confidence) else float("nan")
        flags: list[str] = []
        if result.raw_hr_bpm is None:
            flags.append("no_estimate")
        elif result.hr_bpm is None:
            flags.append("low_confidence_abstain")
        if result.n_exposure_steps:
            flags.append(f"exposure_steps:{result.n_exposure_steps}")
        return {
            PBV_METHOD: Estimate(PBV_METHOD, result.hr_bpm, conf, result.raw_hr_bpm, tuple(flags))
        }


# --------------------------------------------------------------------------- #
# Learned models
# --------------------------------------------------------------------------- #


def softmax(logits: np.ndarray) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64)
    z = z - np.max(z)
    e = np.exp(z)
    return e / np.sum(e)


def decode_hr_bins(
    scores: Sequence[float] | np.ndarray,
    *,
    from_logits: bool = True,
    hr_min_bpm: int = HR_BIN_MIN_BPM,
    neighbourhood_bpm: int = 3,
) -> tuple[float | None, float, float]:
    """Decode a 141-bin (+ optional abstain class) HR head into ``(hr, confidence, p_abstain)``.

    Follows the audit's Stage (c) head: HR is the expectation of the softmax within
    ``+-neighbourhood_bpm`` bins of the argmax, and confidence is the probability mass in that
    neighbourhood. With 142 outputs, the last class is ``no_pulse/abstain``; ``hr`` is ``None``
    when it is the argmax.
    """
    arr = np.asarray(scores, dtype=np.float64).ravel()
    if arr.size not in (N_HR_BINS, N_CLASSES_WITH_ABSTAIN):
        raise ValueError(
            f"Expected {N_HR_BINS} or {N_CLASSES_WITH_ABSTAIN} outputs, got {arr.size}"
        )
    probs = softmax(arr) if from_logits else arr / max(float(np.sum(arr)), 1e-12)
    p_abstain = float(probs[N_HR_BINS]) if arr.size == N_CLASSES_WITH_ABSTAIN else 0.0
    bins = probs[:N_HR_BINS]
    peak = int(np.argmax(bins))
    lo, hi = max(0, peak - neighbourhood_bpm), min(N_HR_BINS, peak + neighbourhood_bpm + 1)
    mass = float(np.sum(bins[lo:hi]))
    centres = hr_min_bpm + np.arange(lo, hi, dtype=np.float64)
    hr = float(np.sum(centres * bins[lo:hi]) / mass) if mass > 0 else None
    if p_abstain >= float(bins[peak]):
        return None, mass, p_abstain
    return hr, mass, p_abstain


def default_stmap_input(t_s: np.ndarray, rgb: np.ndarray, window_s: float = 10.0) -> np.ndarray:
    """``(1, 6, P=1, T)`` float32 STMap from the Phase 2 exporter, for single-ROI traces.

    Uses the last ``window_s`` seconds. Multi-patch models should pass their own preprocess.
    """
    from learning.phase2_fastai.stmap_export import GRID_FS, build_stmap, resample_window

    frames = _frames_from_arrays(t_s, rgb)
    span_s = float(t_s[-1] - t_s[0])
    use_s = min(window_s, span_s)
    start_ms = float(t_s[-1] * 1000.0 - use_s * 1000.0)
    window = resample_window({"roi": frames}, start_ms, window_s=use_s, grid_fs=GRID_FS)
    return build_stmap(window)[None].astype(np.float32)


@dataclass
class ModelEstimator:
    """Pluggable learned model. ``predict`` maps a preprocessed input to raw outputs.

    Outputs may be a 141/142-vector of logits (decoded with ``decode_hr_bins``) or a
    ``(hr_bpm, confidence)`` pair. ``tau`` turns low confidence into an abstention.
    """

    name: str
    predict: Callable[[Any], Any]
    preprocess: Callable[[np.ndarray, np.ndarray], Any] = default_stmap_input
    tau: float = 0.0
    from_logits: bool = True
    methods: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.methods = (self.name,)

    def estimate(self, t_s: np.ndarray, rgb: np.ndarray) -> dict[str, Estimate]:
        try:
            outputs = self.predict(self.preprocess(t_s, rgb))
        except (ValueError, IndexError, RuntimeError) as exc:
            return _abstain_all(self.methods, f"model_error:{type(exc).__name__}")
        arr = np.asarray(outputs, dtype=np.float64).ravel()
        flags: list[str] = []
        if arr.size == 2:
            raw = None if not math.isfinite(arr[0]) else float(arr[0])
            conf = float(arr[1])
        else:
            raw, conf, p_abstain = decode_hr_bins(arr, from_logits=self.from_logits)
            if raw is None:
                flags.append("abstain_class")
            flags.append(f"p_abstain:{p_abstain:.3f}")
        hr = raw if raw is not None and conf >= self.tau else None
        if raw is not None and hr is None:
            flags.append("low_confidence_abstain")
        return {self.name: Estimate(self.name, hr, conf, raw, tuple(flags))}

    @classmethod
    def from_onnx(
        cls,
        name: str,
        model_path: str,
        preprocess: Callable[[np.ndarray, np.ndarray], Any] = default_stmap_input,
        tau: float = 0.0,
    ) -> ModelEstimator:
        """Wrap an ONNX model with one input; onnxruntime is imported lazily."""
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("onnxruntime is not installed.") from exc
        session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name

        def _predict(x: Any) -> Any:
            return session.run(None, {input_name: np.asarray(x, dtype=np.float32)})[0]

        return cls(name=name, predict=_predict, preprocess=preprocess, tau=tau)

    @classmethod
    def from_torch(
        cls,
        name: str,
        module: Any,
        preprocess: Callable[[np.ndarray, np.ndarray], Any] = default_stmap_input,
        tau: float = 0.0,
    ) -> ModelEstimator:
        """Wrap a ``torch.nn.Module`` (eval mode, no grad); torch is imported lazily."""
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("torch is not installed.") from exc
        module.eval()

        def _predict(x: Any) -> Any:
            with torch.no_grad():
                return module(torch.as_tensor(np.asarray(x, dtype=np.float32))).cpu().numpy()

        return cls(name=name, predict=_predict, preprocess=preprocess, tau=tau)


def load_plugin(ref: str) -> EstimatorSpec:
    """Load ``package.module:factory`` and call ``factory()`` to get an ``EstimatorSpec``."""
    if ":" not in ref:
        raise ValueError("Plugin reference must look like 'package.module:factory'.")
    module_name, attr = ref.split(":", 1)
    factory = getattr(importlib.import_module(module_name), attr)
    spec = factory() if callable(factory) and not isinstance(factory, EstimatorSpec) else factory
    if not isinstance(spec, EstimatorSpec):
        raise TypeError(f"{ref} did not produce an EstimatorSpec.")
    return spec


def build_estimators(methods: Sequence[str], plugins: Sequence[str] = ()) -> list[EstimatorSpec]:
    """Built-in specs for ``methods`` plus any plugin specs, with duplicate checks."""
    unknown = [m for m in methods if m not in BUILTIN_METHODS]
    if unknown:
        raise ValueError(
            f"Unknown methods {unknown}. Built-ins: {', '.join(BUILTIN_METHODS)}; "
            "use --plugin for models."
        )
    specs: list[EstimatorSpec] = []
    classical = tuple(m for m in methods if m in CLASSICAL_METHODS)
    if classical:
        specs.append(ClassicalEstimator(classical))
    if PBV_METHOD in methods:
        specs.append(PbvI30Estimator())
    specs.extend(load_plugin(ref) for ref in plugins)
    seen: set[str] = set()
    for spec in specs:
        for method in spec.methods:
            if method in seen:
                raise ValueError(f"Method '{method}' is produced by more than one estimator.")
            seen.add(method)
    return specs
