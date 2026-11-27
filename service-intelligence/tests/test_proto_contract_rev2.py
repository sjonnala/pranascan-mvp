"""Backward-compatibility checks for scan_intelligence.proto contract revision 2 (T-401/T-403).

Rev 1 is pinned as the serialized FileDescriptorProto that protoc emitted into the
checked-in ``scan_intelligence_pb2.py`` before rev 2 (tests/fixtures/...rev1_descriptor.bin).
Rev 2 is the current ``scan_intelligence_pb2``. Both are loaded into separate descriptor
pools so an "old peer" and a "new peer" can talk to each other over real wire bytes.
"""

from pathlib import Path

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

import scan_intelligence_pb2 as rev2

FIXTURE = Path(__file__).parent / "fixtures" / "scan_intelligence_rev1_descriptor.bin"
PKG = "pranapulse.intelligence.scan.v1"

NEW_REQUEST_FIELDS = {
    "capture_timing": 21,
    "device_profile": 22,
    "conjunctival_roi": 23,
    "processing_context": 24,
    "contract_revision": 25,
}
NEW_RESPONSE_FIELDS = {
    "quality": 22,
    "rppg": 23,
    "anemia": 24,
    "voice": 25,
    "contract_revision": 26,
}
NEW_ENUMS = {
    "FrameTimestampSource",
    "DevicePlatform",
    "CapturePath",
    "ColorRange",
    "LockState",
    "ProcessingPurpose",
    "QualityScoreBasis",
    "HrStatus",
    "HrAbstentionReason",
    "AnemiaApplicability",
    "AnemiaNotApplicableReason",
    "VoiceStatus",
    "VoiceAbstentionReason",
}


@pytest.fixture(scope="module")
def rev1_file() -> descriptor_pb2.FileDescriptorProto:
    return descriptor_pb2.FileDescriptorProto.FromString(FIXTURE.read_bytes())


@pytest.fixture(scope="module")
def rev1_classes(rev1_file):
    pool = descriptor_pool.DescriptorPool()
    pool.Add(rev1_file)
    request = message_factory.GetMessageClass(
        pool.FindMessageTypeByName(f"{PKG}.ScanEvaluationRequest")
    )
    response = message_factory.GetMessageClass(
        pool.FindMessageTypeByName(f"{PKG}.ScanEvaluationResponse")
    )
    return request, response


def _rev2_file() -> descriptor_pb2.FileDescriptorProto:
    proto = descriptor_pb2.FileDescriptorProto()
    rev2.DESCRIPTOR.CopyToProto(proto)
    return proto


def _fields(file_proto, message_name):
    msg = next(m for m in file_proto.message_type if m.name == message_name)
    return {f.name: f for f in msg.field}


@pytest.mark.parametrize(
    "message_name", ["FrameSample", "ScanEvaluationRequest", "ScanEvaluationResponse"]
)
def test_every_rev1_field_is_unchanged(rev1_file, message_name):
    old = _fields(rev1_file, message_name)
    new = _fields(_rev2_file(), message_name)
    for name, field in old.items():
        assert name in new, f"{message_name}.{name} was removed"
        got = new[name]
        assert (got.number, got.type, got.label, got.type_name, got.proto3_optional) == (
            field.number,
            field.type,
            field.label,
            field.type_name,
            field.proto3_optional,
        ), f"{message_name}.{name} changed"


def test_rev1_enum_and_service_are_unchanged(rev1_file):
    new = _rev2_file()
    old_scan_type = next(e for e in rev1_file.enum_type if e.name == "ScanType")
    new_scan_type = next(e for e in new.enum_type if e.name == "ScanType")
    assert old_scan_type == new_scan_type
    assert list(rev1_file.service) == list(new.service)
    assert rev1_file.package == new.package == PKG
    assert rev1_file.options == new.options


def test_new_field_numbers_follow_rev1_maximum(rev1_file):
    new = _rev2_file()
    for message_name, expected in (
        ("ScanEvaluationRequest", NEW_REQUEST_FIELDS),
        ("ScanEvaluationResponse", NEW_RESPONSE_FIELDS),
    ):
        old_max = max(f.number for f in _fields(rev1_file, message_name).values())
        fields = _fields(new, message_name)
        numbers = [f.number for f in fields.values()]
        assert len(numbers) == len(set(numbers)), f"duplicate number in {message_name}"
        for name, number in expected.items():
            assert fields[name].number == number
            assert number > old_max


def test_all_new_enums_start_with_prefixed_unspecified_zero():
    new = _rev2_file()
    enums = {e.name: e for e in new.enum_type}
    assert NEW_ENUMS <= set(enums)
    seen_values: set[str] = set()
    for enum in enums.values():
        assert enum.value[0].number == 0
        assert enum.value[0].name.endswith("_UNSPECIFIED")
        for value in enum.value:
            assert value.name not in seen_values, f"value name clash: {value.name}"
            seen_values.add(value.name)


def _rev2_request() -> rev2.ScanEvaluationRequest:
    return rev2.ScanEvaluationRequest(
        frame_data=[rev2.FrameSample(t_ms=0.0, r_mean=0.4, g_mean=0.5, b_mean=0.3)],
        hr_bpm=72.0,
        quality_score=0.81,
        flags=["low_lighting"],
        scan_type=rev2.SCAN_TYPE_STANDARD,
        capture_timing=rev2.CaptureTiming(
            delivered_fps=29.7,
            fps_jitter_ms=2.1,
            frame_timestamp_source=rev2.FRAME_TIMESTAMP_SOURCE_HARDWARE,
        ),
        device_profile=rev2.DeviceProfile(
            device_model="Pixel 7a",
            platform=rev2.DEVICE_PLATFORM_ANDROID,
            capture_path=rev2.CAPTURE_PATH_YUV_PLUGIN,
            ae_lock=rev2.LOCK_STATE_CONFIRMED,
        ),
        conjunctival_roi=rev2.ConjunctivalRoiMeans(r_mean=0.6, g_mean=0.3, b_mean=0.2),
        processing_context=rev2.ProcessingContext(
            granted_purposes=[rev2.PROCESSING_PURPOSE_SCAN_ONEOFF],
            consent_notice_version="2027.1",
        ),
        contract_revision=2,
    )


def test_old_intelligence_reads_rev2_request(rev1_classes):
    old_request_cls, _ = rev1_classes
    old = old_request_cls.FromString(_rev2_request().SerializeToString())
    assert old.hr_bpm == 72.0
    assert old.quality_score == pytest.approx(0.81)
    assert list(old.flags) == ["low_lighting"]
    assert len(old.frame_data) == 1
    assert old.scan_type == 1


def test_rev2_fields_survive_an_old_hop(rev1_classes):
    old_request_cls, _ = rev1_classes
    original = _rev2_request()
    hopped = old_request_cls.FromString(original.SerializeToString()).SerializeToString()
    again = rev2.ScanEvaluationRequest.FromString(hopped)
    assert again.contract_revision == 2
    assert again.capture_timing.delivered_fps == pytest.approx(29.7)
    assert again.device_profile.platform == rev2.DEVICE_PLATFORM_ANDROID
    assert list(again.processing_context.granted_purposes) == [
        rev2.PROCESSING_PURPOSE_SCAN_ONEOFF
    ]
    assert again == original


def test_rev2_intelligence_reads_rev1_request(rev1_classes):
    old_request_cls, _ = rev1_classes
    legacy = old_request_cls(hr_bpm=65.0, quality_score=0.7, flags=["motion_detected"])
    new = rev2.ScanEvaluationRequest.FromString(legacy.SerializeToString())
    assert new.contract_revision == 0
    for name in ("capture_timing", "device_profile", "conjunctival_roi", "processing_context"):
        assert not new.HasField(name)
    assert new.hr_bpm == 65.0


def test_old_core_reads_rev2_abstained_response(rev1_classes):
    _, old_response_cls = rev1_classes
    response = rev2.ScanEvaluationResponse(
        quality_score=0.18,
        quality_gate_passed=True,
        flags=["low_lighting"],
        quality=rev2.QualityBreakdown(
            mobile_quality_score=0.83,
            spectral_quality_score=0.18,
            quality_score_basis=rev2.QUALITY_SCORE_BASIS_SPECTRAL,
        ),
        rppg=rev2.RppgAssessment(
            hr_status=rev2.HR_STATUS_ABSTAINED,
            abstention_reason=rev2.HR_ABSTENTION_REASON_LOW_SPECTRAL_SNR,
        ),
        anemia=rev2.AnemiaAssessment(
            applicability=rev2.ANEMIA_APPLICABILITY_NOT_APPLICABLE,
            not_applicable_reason=rev2.ANEMIA_NOT_APPLICABLE_REASON_NO_CONJUNCTIVAL_ROI,
        ),
        voice=rev2.VoiceAssessment(
            status=rev2.VOICE_STATUS_ABSTAINED,
            abstention_reasons=[rev2.VOICE_ABSTENTION_REASON_HIGH_NOISE],
            client_values_cleared=True,
        ),
        contract_revision=2,
    )
    old = old_response_cls.FromString(response.SerializeToString())
    assert not old.HasField("hr_bpm")
    assert old.quality_gate_passed is True
    assert list(old.flags) == ["low_lighting"]
    assert old.quality_score == pytest.approx(0.18)


def test_rev2_core_reads_rev1_response_without_false_measured(rev1_classes):
    _, old_response_cls = rev1_classes
    legacy = old_response_cls(
        quality_score=0.4, quality_gate_passed=True, flags=["hr_abstained"]
    )
    new = rev2.ScanEvaluationResponse.FromString(legacy.SerializeToString())
    assert new.contract_revision == 0
    assert not new.HasField("rppg")
    # Reading an absent sub-message yields defaults: UNSPECIFIED, never MEASURED.
    assert new.rppg.hr_status == rev2.HR_STATUS_UNSPECIFIED
    assert new.quality.quality_score_basis == rev2.QUALITY_SCORE_BASIS_UNSPECIFIED
    assert new.voice.status == rev2.VOICE_STATUS_UNSPECIFIED
