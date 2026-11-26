"""Tests for the Tiny Mel CNN voice gate adapter (mock ONNX; no onnxruntime needed)."""

import sys
import types

import numpy as np
import pytest

from learning.eval_kit.voice_gate import (
    INPUT_SHAPE,
    N_BUFFER,
    SAMPLE_RATE_HZ,
    THRESHOLD_DEFAULT,
    VoiceGateDecision,
    VoiceGateError,
    VoiceMelGate,
    log_mel_features,
    mel_filterbank,
)

FS = SAMPLE_RATE_HZ


def _vowel(f0=140.0, dur_s=3.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur_s * FS)) / FS
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    return x + 0.01 * rng.standard_normal(t.size)


def _horn(f=450.0, dur_s=5.0):
    t = np.arange(int(dur_s * FS)) / FS
    return np.sign(np.sin(2 * np.pi * f * t))


def test_front_end_shape_dtype_and_standardisation():
    feat = log_mel_features(_vowel())
    assert feat.shape == INPUT_SHAPE and feat.dtype == np.float32
    assert abs(float(feat[0].mean())) < 1e-4
    assert float(feat[0].std()) == pytest.approx(1.0, abs=1e-2)


def test_front_end_is_level_invariant_and_pads_or_truncates():
    x = _vowel(dur_s=5.0)  # full buffer: zero-padding adds a level-dependent floor
    np.testing.assert_allclose(log_mel_features(x), log_mel_features(10.0 * x), atol=2e-3)
    long = np.concatenate([_vowel(dur_s=5.0), np.ones(FS)])
    np.testing.assert_allclose(log_mel_features(long), log_mel_features(long[:N_BUFFER]), atol=1e-6)


def test_front_end_rejects_wrong_rate_and_bad_audio():
    with pytest.raises(ValueError, match="4410"):
        log_mel_features(_vowel(), sample_rate_hz=16000)
    with pytest.raises(ValueError):
        log_mel_features(np.array([]))
    with pytest.raises(ValueError):
        log_mel_features(np.array([0.0, np.nan]))


def test_mel_filterbank_covers_30_to_2205_hz():
    fb = mel_filterbank()
    assert fb.shape == (64, 257)
    bins = np.fft.rfftfreq(512, 1 / FS)
    assert bins[fb[0] > 0].min() >= 30.0
    assert (fb.sum(axis=0)[(bins > 60) & (bins < 2100)] > 0).all()


def test_vowel_and_horn_features_differ():
    assert not np.allclose(log_mel_features(_vowel()), log_mel_features(_horn()), atol=0.1)


def _speech_if_low_band_energy(x):
    """Toy model: logit for speech = mean energy of the lowest 12 Mel bands (where F0 lives)."""
    lowband = float(x[0, 0, :12].mean() - x[0, 0, 30:].mean())
    return np.array([[0.0, 4.0 * lowband]])


def test_decide_accepts_and_rejects_with_scalar_only_decision():
    gate = VoiceMelGate(_speech_if_low_band_energy)
    yes, no = gate.decide(_vowel(f0=120.0)), gate.decide(_horn())
    assert isinstance(yes, VoiceGateDecision)
    assert yes.accepted and yes.reason == "sustained_vowel" and yes.p_speech >= 0.5
    assert not no.accepted and no.reason == "no_sustained_vowel"
    log = yes.to_log_dict()
    assert set(log) == {
        "voice_gate_accepted",
        "voice_gate_p_speech",
        "voice_gate_reason",
    }
    assert all(not isinstance(v, np.ndarray | list) for v in log.values())


def test_invalid_audio_is_rejected_not_raised():
    gate = VoiceMelGate(lambda x: np.array([[0.0, 9.0]]))
    d = gate.decide(np.array([]))
    assert not d.accepted and d.reason == "invalid_audio"


def test_threshold_and_probability_inputs():
    feat = log_mel_features(_vowel())
    probs_gate = VoiceMelGate(lambda x: np.array([[0.3, 0.7]]), threshold=0.8, from_logits=False)
    assert probs_gate.p_speech(feat) == pytest.approx(0.7)
    assert not probs_gate.decide(_vowel()).accepted
    with pytest.raises(ValueError):
        VoiceMelGate(lambda x: x, threshold=1.0)


def test_output_contract_is_enforced():
    feat = log_mel_features(_vowel())
    with pytest.raises(VoiceGateError, match="2 scores"):
        VoiceMelGate(lambda x: np.zeros((1, 3))).p_speech(feat)
    with pytest.raises(ValueError, match="shape"):
        VoiceMelGate(lambda x: np.zeros((1, 2))).p_speech(np.zeros((3, 64, 100)))


class _MockInput:
    def __init__(self, shape):
        self.name = "x"
        self.shape = shape


class _MockSessionOptions:
    intra_op_num_threads = 0


def _mock_ort(shape=("N", 3, 64, 101), n_inputs=1, logits=(0.0, 3.0)):
    seen: dict = {}

    class _Session:
        def __init__(self, path, opts=None, providers=None):
            seen.update(path=path, threads=opts.intra_op_num_threads, providers=providers)

        def get_inputs(self):
            return [_MockInput(shape) for _ in range(n_inputs)]

        def run(self, outputs, feeds):
            x = feeds["x"]
            seen["input_shape"], seen["dtype"] = x.shape, x.dtype
            return [np.array([logits])]

    mod = types.SimpleNamespace(InferenceSession=_Session, SessionOptions=_MockSessionOptions)
    return mod, seen


def test_from_onnx_with_mock_runtime(monkeypatch):
    mod, seen = _mock_ort()
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)
    gate = VoiceMelGate.from_onnx("V1_tinymelcnn4_int8_static_qdq.onnx")
    d = gate.decide(_vowel())
    assert d.accepted and d.threshold == THRESHOLD_DEFAULT
    assert seen["input_shape"] == (1, *INPUT_SHAPE) and seen["dtype"] == np.float32
    assert seen["threads"] == 1 and seen["providers"] == ["CPUExecutionProvider"]


def test_from_onnx_rejects_wrong_model_signature(monkeypatch):
    mod, _ = _mock_ort(shape=[1, 3, 64, 100])
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)
    with pytest.raises(VoiceGateError, match="input shape"):
        VoiceMelGate.from_onnx("wrong.onnx")
    mod, _ = _mock_ort(n_inputs=2)
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)
    with pytest.raises(VoiceGateError, match="one-input"):
        VoiceMelGate.from_onnx("two_inputs.onnx")


def test_from_onnx_rejecting_horn(monkeypatch):
    mod, _ = _mock_ort(logits=(4.0, -4.0))
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)
    d = VoiceMelGate.from_onnx("gate.onnx").decide(_horn())
    assert not d.accepted and d.p_speech < 0.01
