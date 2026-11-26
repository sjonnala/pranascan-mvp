import pytest

from learning.phase1.dataset_model import (
    COMMERCIAL_LICENCES,
    NON_COMMERCIAL_DATASETS,
    CaptureContext,
    DatasetSessionV2,
    FrameSource,
    LicenceGuardedDataset,
    LicenceViolationError,
    ReferenceSignal,
    SubjectContext,
    assert_commercial_training_allowed,
    build_commercial_training_dataloader,
    canonical_dataset_name,
    check_commercial_training,
    is_non_commercial_dataset,
    resolve_registered_licence,
    session_v2_from_manifest,
    session_v2_to_dict,
)
from learning.phase1.frame_sources import ArrayFrameSource

NON_COMMERCIAL = ["UBFC-rPPG", "PURE", "COHFACE", "MMPD", "SCAMPS", "CelebAMask-HQ"]
CAPTURE = CaptureContext(
    device="test", is_smartphone=False, codec="raw", nominal_fps=30.0, resolution=(640, 480)
)


def _session(dataset, licence, split="bench_only", session_id="s1"):
    return DatasetSessionV2(
        session_id=session_id,
        dataset=dataset,
        licence=licence,
        capture=CAPTURE,
        subject=SubjectContext(subject_id=f"{session_id}_subject"),
        split=split,
    )


def test_hard_list_covers_the_six_non_commercial_datasets():
    assert {canonical_dataset_name(n) for n in NON_COMMERCIAL} == set(NON_COMMERCIAL_DATASETS)


def test_only_lgi_ppgi_and_mcd_rppg_are_registered_as_commercial():
    commercial = {
        name
        for name in [
            "UBFC-rPPG",
            "PURE",
            "COHFACE",
            "MMPD",
            "SCAMPS",
            "CelebAMask-HQ",
            "LGI-PPGI",
            "MCD-rPPG",
            "VitalVideo",
            "M3PD",
        ]
        if resolve_registered_licence(name).commercial_use
    }
    assert commercial == {"LGI-PPGI", "MCD-rPPG"}


@pytest.mark.parametrize("dataset", NON_COMMERCIAL)
@pytest.mark.parametrize("split", ["train", "val", "test"])
def test_non_commercial_datasets_cannot_leave_bench_only(dataset, split):
    pinned = resolve_registered_licence(dataset).licence
    with pytest.raises(LicenceViolationError):
        _session(dataset, pinned, split=split)


@pytest.mark.parametrize("dataset", NON_COMMERCIAL)
def test_non_commercial_datasets_cannot_be_relabelled_permissive(dataset):
    for licence in COMMERCIAL_LICENCES:
        with pytest.raises(LicenceViolationError):
            _session(dataset, licence, split="bench_only")


@pytest.mark.parametrize("dataset", NON_COMMERCIAL)
def test_non_commercial_bench_sessions_never_reach_commercial_training(dataset):
    session = _session(dataset, resolve_registered_licence(dataset).licence)
    assert session.commercial_training_allowed is False
    with pytest.raises(LicenceViolationError):
        assert_commercial_training_allowed([session])


@pytest.mark.parametrize(
    "alias",
    ["ubfc", "UBFC_rPPG", "ubfc-rppg2", "mmpd_mini", "Scamps", "celebamask", "pure_subset"],
)
def test_aliases_and_derived_names_are_caught(alias):
    assert is_non_commercial_dataset(alias)
    with pytest.raises(LicenceViolationError):
        check_commercial_training(dataset=alias, licence="cc_by_4_0", split="train")


@pytest.mark.parametrize("dataset", ["LGI-PPGI", "MCD-rPPG"])
def test_commercial_datasets_can_train(dataset):
    session = _session(dataset, "cc_by_4_0", split="train")
    assert session.commercial_training_allowed
    assert_commercial_training_allowed([session])


def test_commercial_dataset_in_bench_only_is_still_refused():
    with pytest.raises(LicenceViolationError):
        assert_commercial_training_allowed([_session("LGI-PPGI", "cc_by_4_0")])


@pytest.mark.parametrize(
    "licence", ["unknown", "research_only", "non_commercial_eula", "no_licence"]
)
def test_restrictive_licence_forces_bench_only_for_unregistered_data(licence):
    with pytest.raises(LicenceViolationError):
        _session("SomeNewSet", licence, split="train")
    assert _session("SomeNewSet", licence).split == "bench_only"


def test_unknown_registered_dataset_cannot_claim_commercial():
    with pytest.raises(LicenceViolationError):
        _session("VitalVideo", "cc_by_4_0", split="train")


def test_own_consented_data_can_train():
    session = _session("PranaScan-India-Pilot", "own_consented", split="train")
    assert session.commercial_training_allowed


def test_guarded_dataset_refuses_at_construction():
    sessions = [
        _session("LGI-PPGI", "cc_by_4_0", split="train", session_id="ok"),
        _session("MMPD", "research_only", session_id="bad"),
    ]
    with pytest.raises(LicenceViolationError, match="bad"):
        LicenceGuardedDataset(sessions, load_item=lambda s: s.session_id)


def test_guarded_dataset_rechecks_every_item():
    ok = _session("LGI-PPGI", "cc_by_4_0", split="train", session_id="ok")
    dataset = LicenceGuardedDataset([ok], load_item=lambda s: s.session_id)
    assert dataset[0] == "ok"
    dataset.sessions.append(_session("UBFC-rPPG", "no_licence", session_id="smuggled"))
    with pytest.raises(LicenceViolationError, match="smuggled"):
        dataset[1]


def test_guarded_dataset_allows_research_use_of_bench_sessions():
    bench = _session("MMPD", "research_only")
    dataset = LicenceGuardedDataset([bench], load_item=lambda s: s.dataset, purpose="research")
    assert len(dataset) == 1
    assert dataset[0] == "MMPD"


def test_commercial_dataloader_builder_uses_factory_and_guard():
    calls = {}

    def factory(dataset, **kwargs):
        calls["kwargs"] = kwargs
        return [dataset[i] for i in range(len(dataset))]

    sessions = [_session("MCD-rPPG", "cc_by_4_0", split="train")]
    batch = build_commercial_training_dataloader(
        sessions, load_item=lambda s: s.dataset, loader_factory=factory, batch_size=4
    )
    assert batch == ["MCD-rPPG"]
    assert calls["kwargs"] == {"batch_size": 4}

    with pytest.raises(LicenceViolationError):
        build_commercial_training_dataloader(
            [_session("SCAMPS", "non_commercial_eula")],
            load_item=lambda s: s,
            loader_factory=factory,
        )


def test_effective_licence_is_the_stricter_one():
    session = _session("MMPD", "research_only")
    assert session.effective_licence == "research_only"
    lgi = _session("LGI-PPGI", "own_consented", split="train")  # same rank: kept
    assert lgi.effective_licence == "own_consented"


def test_value_objects_validate_inputs():
    with pytest.raises(ValueError):
        SubjectContext(subject_id="x", fitzpatrick=7)
    with pytest.raises(ValueError):
        CaptureContext(
            device="d", is_smartphone=True, codec="h264", nominal_fps=0, resolution=(1, 1)
        )
    with pytest.raises(ValueError):
        ReferenceSignal(kind="thermal", sensor="x")
    with pytest.raises(ValueError):
        _session("SomeNewSet", "made_up_licence")


def test_manifest_metadata_round_trip():
    session = session_v2_from_manifest(
        {
            "session_id": "mmpd_p1_0",
            "metadata": {
                "split": "bench_only",
                "capture": {
                    "device": "Galaxy S22 Ultra",
                    "is_smartphone": True,
                    "codec": "mat_downsampled",
                    "nominal_fps": 30,
                    "resolution": [320, 240],
                    "lighting": "LED-low",
                },
                "subject": {"subject_id": "mmpd_1", "fitzpatrick": 4, "glasses": True},
                "reference": {"kind": "ppg_waveform", "sensor": "HKG-07C+"},
                "motion_label": "Stationary",
            },
        },
        dataset_name="MMPD",
    )
    assert session.licence == "research_only"  # filled from the pinned registry
    assert session.capture.resolution == (320, 240)
    as_dict = session_v2_to_dict(session)
    assert as_dict["subject"]["fitzpatrick"] == 4
    assert as_dict["metadata"] == {"motion_label": "Stationary"}
    assert as_dict["commercial_training_allowed"] is False


def test_array_source_satisfies_frame_source_protocol():
    import numpy as np

    source = ArrayFrameSource(video=np.zeros((2, 4, 4, 3), dtype=np.uint8), fps=30.0)
    assert isinstance(source, FrameSource)
