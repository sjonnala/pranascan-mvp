"""Tests for scripts/check_privacy_boundaries.py (the privacy CI check)."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_privacy_boundaries.py"


@pytest.fixture(scope="module")
def pb():
    spec = importlib.util.spec_from_file_location("check_privacy_boundaries", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _scan(pb, tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return pb.scan(tmp_path, ("mobile", "service-intelligence"))


def _rules(findings):
    return sorted(f.rule for f in findings)


def test_repository_is_clean(pb):
    findings = pb.scan(REPO_ROOT)
    assert findings == [], "\n".join(f.format() for f in findings)


def test_main_exit_codes(pb, tmp_path, capsys):
    assert pb.main(["--root", str(REPO_ROOT)]) == 0
    _scan(
        pb,
        tmp_path,
        {"service-intelligence/app/a.py": "logger.info('x %s', raw_frames)\n"},
    )
    assert pb.main(["--root", str(tmp_path)]) == 1
    assert "PB001" in capsys.readouterr().out
    assert pb.main(["--root", str(tmp_path / "missing")]) == 2


@pytest.mark.parametrize(
    "line",
    [
        "logger.info('frames %s', raw_frames)",
        "logging.debug('pcm=%s', pcm)",
        "log_event(db, action='scan', detail=str(audio_samples))",
        "audit_service.log_event(db, detail=json.dumps({'mel': mel_spec.tolist()}))",
        "sentry_sdk.set_extra('landmarks', face.landmarks)",
        "analytics.track('scan', frames)",
        "AuditLog(detail=repr(frame_buffer))",
    ],
)
def test_python_raw_buffers_in_sinks_are_flagged(pb, tmp_path, line):
    findings = _scan(pb, tmp_path, {"service-intelligence/app/x.py": line + "\n"})
    assert _rules(findings) == ["PB001"], findings


@pytest.mark.parametrize(
    "line",
    [
        "logger.info('n=%d', len(frames))",
        "logger.info('snr=%.1f', audio_snr_db)",
        "logger.warning('shape %s', frames.shape)",
        "logger.info('dropped=%d', n_frames)",
        "log_event(db, action='scan', detail=decision.reason)",
        "process(raw_frames)",
    ],
)
def test_python_scalars_and_non_sinks_pass(pb, tmp_path, line):
    assert _scan(pb, tmp_path, {"service-intelligence/app/x.py": line + "\n"}) == []


def test_python_fitzpatrick_needs_consent(pb, tmp_path):
    bad = "analytics.track('scan', fitzpatrick_type=skin.fitzpatrick)\n"
    good = (
        "if user.consent.fairness_analytics:\n"
        "    analytics.track('scan', fitzpatrick_type=skin.fitzpatrick)\n"
    )
    assert _rules(_scan(pb, tmp_path, {"service-intelligence/app/bad.py": bad})) == ["PB002"]
    assert _scan(pb, tmp_path / "g", {"service-intelligence/app/good.py": good}) == []


def test_python_log_model_fields(pb, tmp_path):
    src = (
        "class ScanAnalyticsEvent(Base):\n"
        "    fitzpatrick_type: Mapped[int]\n"
        "    raw_frames = Column(LargeBinary)\n"
        "    hr_bpm: Mapped[float]\n"
        "class ScanResult(Base):\n"
        "    fitzpatrick_type: Mapped[int]\n"
    )
    findings = _scan(pb, tmp_path, {"service-intelligence/app/models/m.py": src})
    assert _rules(findings) == ["PB003", "PB003"]
    assert {f.line for f in findings} == {2, 3}


@pytest.mark.parametrize(
    "line",
    [
        "console.log('frame', frame.toArrayBuffer());",
        "analytics.track('voice', { pcmFrames });",
        "Sentry.setExtra('samples', audioSamples);",
        "crashlytics().log(JSON.stringify(landmarks));",
        "logger.info(`mel ${melSpectrogram}`);",
    ],
)
def test_js_raw_buffers_in_sinks_are_flagged(pb, tmp_path, line):
    findings = _scan(pb, tmp_path, {"mobile/src/x.tsx": line + "\n"})
    assert _rules(findings) == ["PB001"], findings


@pytest.mark.parametrize(
    "line",
    [
        "console.log('frames dropped', droppedFrames.length);",
        "console.warn('audio buffer too short');",
        "// console.log(frame.toArrayBuffer());",
        "const data = new Uint8Array(frame.toArrayBuffer());",
        "analytics.track('scan_done', { audio_snr_db: snrDb, frameCount });",
    ],
)
def test_js_scalars_comments_and_non_sinks_pass(pb, tmp_path, line):
    assert _scan(pb, tmp_path, {"mobile/src/x.ts": line + "\n"}) == []


def test_js_fitzpatrick_needs_consent(pb, tmp_path):
    bad = "analytics.track('scan', { fitzpatrickType });\n"
    good = "if (consent.fairnessAnalytics) {\n  analytics.track('scan', { fitzpatrickType });\n}\n"
    assert _rules(_scan(pb, tmp_path, {"mobile/src/bad.ts": bad})) == ["PB002"]
    assert _scan(pb, tmp_path / "g", {"mobile/src/good.ts": good}) == []


def test_suppression_requires_reason(pb, tmp_path):
    ok = (
        "logger.debug('x', raw_frames)  # privacy-ok: local-only debug build, stripped in release\n"
    )
    bare = "logger.debug('x', raw_frames)  # privacy-ok\n"
    assert _scan(pb, tmp_path / "a", {"service-intelligence/app/a.py": ok}) == []
    assert _rules(_scan(pb, tmp_path / "b", {"service-intelligence/app/b.py": bare})) == ["PB900"]


def test_tests_mocks_and_vendored_dirs_are_skipped(pb, tmp_path):
    line = "logger.info('x', raw_frames)\n"
    files = {
        "service-intelligence/tests/test_x.py": line,
        "mobile/node_modules/pkg/index.js": "console.log(frame.toArrayBuffer())\n",
        "mobile/__tests__/a.test.tsx": "console.log(pcmFrames)\n",
    }
    assert _scan(pb, tmp_path, files) == []


def test_identifier_classifier(pb):
    raw = [
        "raw_frames",
        "toArrayBuffer",
        "pcmFrames",
        "mel_spec",
        "landmarks",
        "yuvPlane",
        "frames",
    ]
    scalar = ["n_frames", "audio_snr_db", "frameCount", "melody", "rgb", "frame_rate"]
    assert all(pb.is_raw_identifier(n) for n in raw)
    assert not any(pb.is_raw_identifier(n) for n in scalar)
