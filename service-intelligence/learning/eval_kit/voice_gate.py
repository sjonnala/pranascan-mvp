"""Voice Mel gate: a "is there a sustained vowel?" check in front of the jitter/shimmer pipeline.

Port of the T-203 winner (``Cycle-2/Voice-and-Cascade-Experiments``): a 61.5 KB static-QDQ INT8
``TinyMelCNN4`` ONNX model that reads a 3 x 64 x 101 log-Mel image and outputs two logits
(class 1 = speech). On the synthetic Cycle-1 voice harness it cut street-horn (N4) false accepts
from 38% (classical reference fix) to 0% at 100% speech recall. **Every number came from
synthetic data**; nothing was checked on real phone recordings.

Ubiquitous language
-------------------
- ``VoiceGateDecision``: one clip's verdict. ``accepted`` means "a sustained vowel is present",
  not "the jitter is trustworthy". Ship the gate *in front of* the voice reference fix: the gate
  rejects horns and machinery, the reference fix still abstains on short, clipped or low-HNR
  vowels.
- ``log_mel_features``: the frozen front end (64 log-Mel bands 30-2205 Hz, n_fft 512, hop 220 at
  4.41 kHz over a 5 s buffer, zero-padded; per-clip standardised; delta and delta-delta with a
  9-frame regression). It must match training exactly, so its constants are frozen here.

Privacy: features and audio stay in memory. Nothing here logs, persists or returns PCM or Mel
arrays; ``VoiceGateDecision`` carries only scalars (see ``scripts/check_privacy_boundaries.py``).
onnxruntime is imported lazily so the module imports without it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

SAMPLE_RATE_HZ = 4410
BUFFER_S = 5.0
N_BUFFER = int(BUFFER_S * SAMPLE_RATE_HZ)  # 22050 samples
N_MELS = 64
N_FRAMES = 101
N_FFT = 512
HOP = 220
F_MIN_HZ = 30.0
DELTA_HALF_WIDTH = 4  # 9-frame regression
INPUT_SHAPE = (3, N_MELS, N_FRAMES)
SPEECH_CLASS = 1
THRESHOLD_DEFAULT = 0.5  # chosen on VAL in T-203; kept for both nets


def _hz_to_mel(f: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_to_hz(m: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(m) / 2595.0) - 1.0)


def mel_filterbank(
    n_mels: int = N_MELS,
    n_fft: int = N_FFT,
    sr: int = SAMPLE_RATE_HZ,
    f_min: float = F_MIN_HZ,
) -> np.ndarray:
    """Triangular HTK-mel filterbank ``(n_mels, n_fft // 2 + 1)`` used in training."""
    mels = np.linspace(_hz_to_mel(f_min), _hz_to_mel(sr / 2.0), n_mels + 2)
    hz = _mel_to_hz(mels)
    bins = np.fft.rfftfreq(n_fft, 1.0 / sr)
    fb = np.zeros((n_mels, bins.size))
    for m in range(n_mels):
        lo, c, hi = hz[m], hz[m + 1], hz[m + 2]
        fb[m] = np.clip(np.minimum((bins - lo) / (c - lo), (hi - bins) / (hi - c)), 0.0, None)
    return fb


_FB = mel_filterbank()
_WINDOW = np.hanning(N_FFT)


def _delta(x: np.ndarray, w: int = DELTA_HALF_WIDTH) -> np.ndarray:
    pad = np.pad(x, ((0, 0), (w, w)), mode="edge")
    n = x.shape[1]
    num = sum(k * (pad[:, w + k : w + k + n] - pad[:, w - k : w - k + n]) for k in range(1, w + 1))
    return num / (2.0 * sum(k * k for k in range(1, w + 1)))


def log_mel_features(audio: np.ndarray, sample_rate_hz: int = SAMPLE_RATE_HZ) -> np.ndarray:
    """Return the ``(3, 64, 101)`` float32 log-Mel + delta + delta-delta image for one clip.

    ``audio`` is mono PCM at 4.41 kHz (the client rate). Longer clips are cut to 5 s, shorter
    ones zero-padded, exactly as in training.
    """
    if sample_rate_hz != SAMPLE_RATE_HZ:
        raise ValueError(
            f"Voice gate expects {SAMPLE_RATE_HZ} Hz audio, got {sample_rate_hz} Hz. "
            "Resample (anti-aliased) before calling."
        )
    pcm = np.asarray(audio, dtype=np.float64).ravel()
    if pcm.size == 0 or not np.all(np.isfinite(pcm)):
        raise ValueError("audio must be a non-empty, finite 1-D array")
    x = np.zeros(N_BUFFER)
    x[: min(pcm.size, N_BUFFER)] = pcm[:N_BUFFER]
    x = np.pad(x, N_FFT // 2)
    idx = np.arange(N_FRAMES)[:, None] * HOP + np.arange(N_FFT)[None, :]
    spec = np.abs(np.fft.rfft(x[idx] * _WINDOW, axis=1)) ** 2  # (101, 257)
    lm = np.log10(spec @ _FB.T + 1e-10).T  # (64, 101)
    lm = (lm - lm.mean()) / (lm.std() + 1e-3)  # level-invariant
    d1 = _delta(lm)
    d2 = _delta(d1)
    return np.stack([lm, d1, d2]).astype(np.float32)


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - np.max(z)
    e = np.exp(z)
    return e / np.sum(e)


@dataclass(frozen=True)
class VoiceGateDecision:
    """Scalars only: never carries PCM or Mel arrays."""

    accepted: bool
    p_speech: float
    threshold: float
    reason: str

    def to_log_dict(self) -> dict[str, Any]:
        """Safe for audit/analytics logs."""
        return {
            "voice_gate_accepted": self.accepted,
            "voice_gate_p_speech": round(self.p_speech, 4),
            "voice_gate_reason": self.reason,
        }


class VoiceGateError(RuntimeError):
    """Raised when the model output does not match the gate contract."""


@dataclass
class VoiceMelGate:
    """Adapter around any ``predict(x) -> logits`` for an ``(N, 3, 64, 101)`` input.

    Use ``VoiceMelGate.from_onnx(path)`` for the shipped INT8 model, or pass a callable (a torch
    module wrapper, a test double) as ``predict``.
    """

    predict: Callable[[np.ndarray], Any]
    threshold: float = THRESHOLD_DEFAULT
    from_logits: bool = True

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold < 1.0:
            raise ValueError(f"threshold must be in (0, 1), got {self.threshold}")

    def p_speech(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float32)
        if x.shape == INPUT_SHAPE:
            x = x[None]
        if x.shape != (1, *INPUT_SHAPE):
            raise ValueError(f"Expected features of shape {INPUT_SHAPE}, got {x.shape}")
        out = np.asarray(self.predict(x), dtype=np.float64)
        if out.size != 2:
            raise VoiceGateError(f"Voice gate must output 2 scores, got shape {out.shape}")
        scores = out.ravel()
        probs = _softmax(scores) if self.from_logits else scores / max(scores.sum(), 1e-12)
        p = float(probs[SPEECH_CLASS])
        if not math.isfinite(p):
            raise VoiceGateError("Voice gate produced a non-finite probability")
        return p

    def decide(self, audio: np.ndarray, sample_rate_hz: int = SAMPLE_RATE_HZ) -> VoiceGateDecision:
        """Run the front end and the model on one clip and return the verdict."""
        try:
            features = log_mel_features(audio, sample_rate_hz)
        except ValueError:
            return VoiceGateDecision(False, 0.0, self.threshold, "invalid_audio")
        p = self.p_speech(features)
        if p >= self.threshold:
            return VoiceGateDecision(True, p, self.threshold, "sustained_vowel")
        return VoiceGateDecision(False, p, self.threshold, "no_sustained_vowel")

    @classmethod
    def from_onnx(
        cls,
        model_path: str,
        threshold: float = THRESHOLD_DEFAULT,
        intra_op_threads: int = 1,
    ) -> VoiceMelGate:
        """Load the INT8 ONNX gate (input ``x`` ``(N, 3, 64, 101)``, output logits)."""
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("onnxruntime is not installed.") from exc
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = intra_op_threads
        session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        inputs = session.get_inputs()
        if len(inputs) != 1:
            raise VoiceGateError(f"Expected a one-input model, got {len(inputs)} inputs")
        shape = list(inputs[0].shape)
        fixed_dims_ok = all(
            not isinstance(d, int) or d == want
            for d, want in zip(shape[1:], INPUT_SHAPE, strict=False)
        )
        if len(shape) != 4 or not fixed_dims_ok:
            raise VoiceGateError(f"Model input shape {shape} does not match (N, {INPUT_SHAPE})")
        input_name = inputs[0].name

        def _predict(x: np.ndarray) -> Any:
            return session.run(None, {input_name: x.astype(np.float32)})[0]

        return cls(predict=_predict, threshold=threshold)
