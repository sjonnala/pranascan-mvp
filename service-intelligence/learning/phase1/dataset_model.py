"""Dataset domain model for the rPPG learning track, with a hard licence guard.

Ubiquitous language
-------------------
- ``CaptureContext``: what the camera saw (device, codec, fps, lighting, motion).
- ``SubjectContext``: who was in front of it (Fitzpatrick type, occluders).
- ``ReferenceSignal``: the contact sensor the labels come from (PPG or ECG waveform,
  or a ready-made HR series).
- ``DatasetSessionV2``: one recording, carrying its dataset, licence and split.
- ``FrameSource``: a port that yields ``(t_ms, HxWx3 uint8 RGB)`` frames with the
  source's own timing. Adapters live in ``frame_sources.py``.

Licence guard
-------------
PranaScan is intended to be a commercial product. Datasets whose terms only allow
non-commercial research may be used to learn and to benchmark, never to train
weights that ship. The guard turns that obligation into code:

1. ``DATASET_LICENCES`` pins the licence of every public dataset the Cycle-1
   dossier reviewed. A manifest cannot relabel a pinned dataset as more permissive.
2. A non-commercial licence forces ``split == "bench_only"``. Constructing a
   ``DatasetSessionV2`` that breaks this raises ``LicenceViolationError``.
3. ``NON_COMMERCIAL_DATASETS`` (UBFC-rPPG, PURE, COHFACE, MMPD, SCAMPS,
   CelebAMask-HQ) are refused by name in ``assert_commercial_training_allowed``,
   regardless of what licence or split a caller claims.
4. ``LicenceGuardedDataset`` and ``build_commercial_training_dataloader`` re-check
   every session at construction and again on every ``__getitem__``, so a
   ``bench_only`` session can never be yielded by a commercial training loader.

Licence findings come from ``rPPG-Datasets-and-Ethics-Dossier.md`` (Cycle 1,
26 Nov 2026). Only LGI-PPGI and MCD-rPPG (both CC BY 4.0) allow commercial use.
This is an engineering control, not legal advice.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, get_args, runtime_checkable

import numpy as np

ReferenceKind = Literal["ppg_waveform", "ecg_waveform", "hr_series"]
LicenceTag = Literal[
    "research_only",
    "non_commercial_eula",
    "no_licence",
    "unknown",
    "cc_by_4_0",
    "own_consented",
    "synthetic_owned",
]
Split = Literal["train", "val", "test", "bench_only"]
Purpose = Literal["commercial_training", "research"]

REFERENCE_KINDS: frozenset[str] = frozenset(get_args(ReferenceKind))
LICENCE_TAGS: frozenset[str] = frozenset(get_args(LicenceTag))
SPLITS: frozenset[str] = frozenset(get_args(Split))

COMMERCIAL_LICENCES: frozenset[str] = frozenset({"cc_by_4_0", "own_consented", "synthetic_owned"})
"""Licences that permit training weights that ship in a commercial product."""

# Licence ranking used to stop a manifest from claiming more than the pinned licence.
_PERMISSIVENESS: dict[str, int] = {
    "no_licence": 0,
    "unknown": 0,
    "research_only": 0,
    "non_commercial_eula": 0,
    "cc_by_4_0": 1,
    "own_consented": 1,
    "synthetic_owned": 1,
}


def canonical_dataset_name(name: str) -> str:
    """Normalise a dataset name so aliases like 'ubfc_rppg' and 'UBFC-rPPG' match."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass(frozen=True)
class DatasetLicence:
    """Pinned licence finding for one public dataset."""

    name: str
    licence: LicenceTag
    commercial_use: bool
    note: str


_REGISTERED: tuple[DatasetLicence, ...] = (
    DatasetLicence(
        "UBFC-rPPG",
        "no_licence",
        False,
        "No licence text published; shared for research. No licence = all rights reserved.",
    ),
    DatasetLicence(
        "PURE",
        "research_only",
        False,
        "Academic requests only; requests from companies are not considered.",
    ),
    DatasetLicence(
        "COHFACE",
        "non_commercial_eula",
        False,
        "Non-commercial EULA on a restricted Zenodo record.",
    ),
    DatasetLicence(
        "MMPD",
        "research_only",
        False,
        "Academic use; any commercial usage is banned by the release agreement.",
    ),
    DatasetLicence(
        "SCAMPS",
        "non_commercial_eula",
        False,
        "R-UDA v1.0: models trained on the data are Results and may not be used commercially.",
    ),
    DatasetLicence(
        "CelebAMask-HQ",
        "research_only",
        False,
        "Non-commercial research only, including any portion of derived data.",
    ),
    DatasetLicence(
        "LGI-PPGI",
        "cc_by_4_0",
        True,
        "CC BY 4.0 on the GitHub repo; attribution required; consent scope undocumented.",
    ),
    DatasetLicence(
        "MCD-rPPG",
        "cc_by_4_0",
        True,
        "CC BY 4.0 on the Hugging Face card (kyegorov/mcd_rppg); attribution required.",
    ),
    DatasetLicence(
        "VitalVideo",
        "unknown",
        False,
        "Dataset licence not found; the paper's CC BY covers the paper, not the data.",
    ),
    DatasetLicence(
        "M3PD",
        "unknown",
        False,
        "No dataset licence or access route found.",
    ),
)

DATASET_LICENCES: dict[str, DatasetLicence] = {
    canonical_dataset_name(entry.name): entry for entry in _REGISTERED
}
"""Pinned licences, keyed by ``canonical_dataset_name``."""

_ALIASES: dict[str, str] = {
    "ubfc": "ubfcrppg",
    "ubfc2": "ubfcrppg",
    "ubfcrppg2": "ubfcrppg",
    "celebamask": "celebamaskhq",
    "lgippgidb": "lgippgi",
    "mcdrppgdataset": "mcdrppg",
    "vitalvideos": "vitalvideo",
    "vitalvideosworldwide": "vitalvideo",
    "scampsdataset": "scamps",
    "mmpddataset": "mmpd",
}

NON_COMMERCIAL_DATASETS: frozenset[str] = frozenset(
    canonical_dataset_name(name)
    for name in ("UBFC-rPPG", "PURE", "COHFACE", "MMPD", "SCAMPS", "CelebAMask-HQ")
)
"""Datasets that must never reach a commercial training DataLoader, whatever is claimed."""


class LicenceViolationError(ValueError):
    """Raised when a session's licence does not allow the requested use."""


def resolve_registered_licence(dataset: str) -> DatasetLicence | None:
    """Return the pinned licence for a dataset name or alias, if it is registered."""
    key = canonical_dataset_name(dataset)
    key = _ALIASES.get(key, key)
    return DATASET_LICENCES.get(key)


def is_non_commercial_dataset(dataset: str) -> bool:
    """True when the dataset is on the hard non-commercial list (aliases included)."""
    key = canonical_dataset_name(dataset)
    key = _ALIASES.get(key, key)
    if key in NON_COMMERCIAL_DATASETS:
        return True
    # Catch derived names such as "mmpd_mini" or "ubfc_rppg_subset".
    return any(key.startswith(blocked) for blocked in NON_COMMERCIAL_DATASETS)


@dataclass(frozen=True)
class CaptureContext:
    """What the camera saw. Drives stratified evaluation."""

    device: str
    is_smartphone: bool
    codec: str
    nominal_fps: float
    resolution: tuple[int, int]
    lighting: str | None = None
    motion: str | None = None

    def __post_init__(self) -> None:
        if self.nominal_fps <= 0:
            raise ValueError("nominal_fps must be positive.")
        if len(self.resolution) != 2 or min(self.resolution) <= 0:
            raise ValueError("resolution must be (width, height) with positive values.")


@dataclass(frozen=True)
class SubjectContext:
    """Who was in front of the camera. Used for parity analysis, never for correction."""

    subject_id: str
    fitzpatrick: int | None = None
    sex: str | None = None
    glasses: bool | None = None
    facial_hair: bool | None = None
    forehead_occluder: str | None = None

    def __post_init__(self) -> None:
        if self.fitzpatrick is not None and not 1 <= self.fitzpatrick <= 6:
            raise ValueError("fitzpatrick must be in 1..6 or None.")


@dataclass(frozen=True)
class ReferenceSignal:
    """The contact reference a session's labels come from."""

    kind: ReferenceKind
    sensor: str
    fs_hz: float | None = None
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.kind not in REFERENCE_KINDS:
            raise ValueError(f"Unknown reference kind '{self.kind}'.")
        if self.fs_hz is not None and self.fs_hz <= 0:
            raise ValueError("fs_hz must be positive.")


@dataclass(frozen=True)
class DatasetSessionV2:
    """One recording with the provenance needed to decide how it may be used."""

    session_id: str
    dataset: str
    licence: LicenceTag
    capture: CaptureContext
    subject: SubjectContext
    reference: ReferenceSignal | None = None
    split: Split = "bench_only"
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.licence not in LICENCE_TAGS:
            raise ValueError(f"Unknown licence tag '{self.licence}'.")
        if self.split not in SPLITS:
            raise ValueError(f"Unknown split '{self.split}'.")

        pinned = resolve_registered_licence(self.dataset)
        if pinned is not None and _PERMISSIVENESS[self.licence] > _PERMISSIVENESS[pinned.licence]:
            raise LicenceViolationError(
                f"Session '{self.session_id}' claims licence '{self.licence}' for dataset "
                f"'{self.dataset}', but its pinned licence is '{pinned.licence}'."
            )
        if is_non_commercial_dataset(self.dataset) and self.split != "bench_only":
            raise LicenceViolationError(
                f"Session '{self.session_id}' is from non-commercial dataset "
                f"'{self.dataset}' and must use split='bench_only', not '{self.split}'."
            )
        if self.effective_licence not in COMMERCIAL_LICENCES and self.split != "bench_only":
            raise LicenceViolationError(
                f"Session '{self.session_id}' has licence '{self.effective_licence}', which "
                f"does not allow commercial training; split must be 'bench_only'."
            )

    @property
    def effective_licence(self) -> LicenceTag:
        """The stricter of the claimed and the pinned licence."""
        pinned = resolve_registered_licence(self.dataset)
        if pinned is None:
            return self.licence
        if _PERMISSIVENESS[pinned.licence] < _PERMISSIVENESS[self.licence]:
            return pinned.licence
        return self.licence

    @property
    def commercial_training_allowed(self) -> bool:
        return (
            self.split != "bench_only"
            and self.effective_licence in COMMERCIAL_LICENCES
            and not is_non_commercial_dataset(self.dataset)
        )


@runtime_checkable
class FrameSource(Protocol):
    """Port: anything that yields ``(t_ms, HxWx3 uint8 RGB)`` with the source's own timing."""

    def frames(self) -> Iterator[tuple[float, np.ndarray]]: ...


def assert_commercial_training_allowed(sessions: Iterable[DatasetSessionV2]) -> None:
    """Raise ``LicenceViolationError`` if any session may not train commercial weights."""
    for session in sessions:
        check_commercial_training(
            dataset=session.dataset,
            licence=session.licence,
            split=session.split,
            session_id=session.session_id,
        )


def check_commercial_training(
    *,
    dataset: str,
    licence: str,
    split: str,
    session_id: str = "<unknown>",
) -> None:
    """Row-level guard usable on plain records (for example a labels.csv row).

    The decision never trusts a caller's flags alone: the dataset name is checked
    against the hard non-commercial list and the pinned licence registry.
    """
    if is_non_commercial_dataset(dataset):
        raise LicenceViolationError(
            f"Session '{session_id}' comes from non-commercial dataset '{dataset}' and can "
            "never enter a commercial training DataLoader."
        )
    if split == "bench_only":
        raise LicenceViolationError(
            f"Session '{session_id}' is bench_only and can never enter a commercial training "
            "DataLoader."
        )
    pinned = resolve_registered_licence(dataset)
    effective = licence
    if pinned is not None and _PERMISSIVENESS.get(pinned.licence, 0) < _PERMISSIVENESS.get(
        licence, 0
    ):
        effective = pinned.licence
    if effective not in COMMERCIAL_LICENCES:
        raise LicenceViolationError(
            f"Session '{session_id}' has licence '{effective}', which does not allow "
            "commercial training."
        )


T = TypeVar("T")


class LicenceGuardedDataset(Sequence[T]):
    """A map-style dataset (``__len__`` + ``__getitem__``) that enforces the guard.

    It is compatible with ``torch.utils.data.DataLoader`` without importing torch.
    The guard runs once at construction and again for every item, so swapping a
    session in after construction still cannot leak a ``bench_only`` sample.
    """

    def __init__(
        self,
        sessions: Sequence[DatasetSessionV2],
        load_item: Callable[[DatasetSessionV2], T],
        purpose: Purpose = "commercial_training",
    ) -> None:
        if purpose not in ("commercial_training", "research"):
            raise ValueError(f"Unknown purpose '{purpose}'.")
        self.purpose = purpose
        self.sessions = list(sessions)
        self._load_item = load_item
        if purpose == "commercial_training":
            assert_commercial_training_allowed(self.sessions)

    def __len__(self) -> int:
        return len(self.sessions)

    def __getitem__(self, index: int) -> T:  # type: ignore[override]
        session = self.sessions[index]
        if self.purpose == "commercial_training":
            assert_commercial_training_allowed([session])
        return self._load_item(session)


def build_commercial_training_dataloader(
    sessions: Sequence[DatasetSessionV2],
    load_item: Callable[[DatasetSessionV2], Any],
    loader_factory: Callable[..., Any] | None = None,
    **loader_kwargs: Any,
) -> Any:
    """Build a training DataLoader that can only ever see commercially licensed sessions.

    ``loader_factory`` defaults to ``torch.utils.data.DataLoader`` (imported lazily).
    Pass any callable taking ``(dataset, **kwargs)`` to use another framework.
    """
    dataset = LicenceGuardedDataset(sessions, load_item, purpose="commercial_training")
    if loader_factory is None:
        try:
            from torch.utils.data import DataLoader
        except ImportError as exc:  # pragma: no cover - torch is optional here
            raise RuntimeError("torch is not installed; pass loader_factory explicitly.") from exc
        loader_factory = DataLoader
    return loader_factory(dataset, **loader_kwargs)


def session_v2_from_manifest(session: dict[str, Any], dataset_name: str) -> DatasetSessionV2:
    """Build a ``DatasetSessionV2`` from a manifest entry's ``metadata`` block.

    Expected shape (all keys inside ``metadata``)::

        {"licence": "research_only", "split": "bench_only",
         "capture": {...CaptureContext fields...},
         "subject": {...SubjectContext fields...},
         "reference": {"kind": "ppg_waveform", "sensor": "...", "fs_hz": 60}}

    A pinned dataset's licence is used when the manifest omits ``licence``.
    """
    metadata: dict[str, Any] = dict(session.get("metadata") or {})
    dataset = str(metadata.get("dataset", dataset_name))
    pinned = resolve_registered_licence(dataset)
    licence = metadata.get("licence") or (pinned.licence if pinned else "unknown")

    capture_raw = dict(metadata.get("capture") or {})
    capture = CaptureContext(
        device=str(capture_raw.get("device", "unknown")),
        is_smartphone=bool(capture_raw.get("is_smartphone", False)),
        codec=str(capture_raw.get("codec", "unknown")),
        nominal_fps=float(capture_raw.get("nominal_fps", 30.0)),
        resolution=tuple(capture_raw.get("resolution", (640, 480))),  # type: ignore[arg-type]
        lighting=capture_raw.get("lighting"),
        motion=capture_raw.get("motion"),
    )

    subject_raw = dict(metadata.get("subject") or {})
    subject = SubjectContext(
        subject_id=str(subject_raw.get("subject_id", session["session_id"])),
        fitzpatrick=subject_raw.get("fitzpatrick"),
        sex=subject_raw.get("sex"),
        glasses=subject_raw.get("glasses"),
        facial_hair=subject_raw.get("facial_hair"),
        forehead_occluder=subject_raw.get("forehead_occluder"),
    )

    reference: ReferenceSignal | None = None
    reference_raw = metadata.get("reference")
    if reference_raw:
        reference = ReferenceSignal(
            kind=reference_raw["kind"],
            sensor=str(reference_raw.get("sensor", "unknown")),
            fs_hz=reference_raw.get("fs_hz"),
            path=Path(reference_raw["path"]) if reference_raw.get("path") else None,
        )

    extras = {
        key: value
        for key, value in metadata.items()
        if key not in {"dataset", "licence", "split", "capture", "subject", "reference"}
    }
    return DatasetSessionV2(
        session_id=str(session["session_id"]),
        dataset=dataset,
        licence=licence,
        capture=capture,
        subject=subject,
        reference=reference,
        split=metadata.get("split", "bench_only"),
        metadata=extras,
    )


def session_v2_to_dict(session: DatasetSessionV2) -> dict[str, Any]:
    """JSON-friendly view, used in summaries and labels."""
    return {
        "session_id": session.session_id,
        "dataset": session.dataset,
        "licence": session.licence,
        "effective_licence": session.effective_licence,
        "split": session.split,
        "commercial_training_allowed": session.commercial_training_allowed,
        "capture": {
            "device": session.capture.device,
            "is_smartphone": session.capture.is_smartphone,
            "codec": session.capture.codec,
            "nominal_fps": session.capture.nominal_fps,
            "resolution": list(session.capture.resolution),
            "lighting": session.capture.lighting,
            "motion": session.capture.motion,
        },
        "subject": {
            "subject_id": session.subject.subject_id,
            "fitzpatrick": session.subject.fitzpatrick,
            "sex": session.subject.sex,
            "glasses": session.subject.glasses,
            "facial_hair": session.subject.facial_hair,
            "forehead_occluder": session.subject.forehead_occluder,
        },
        "reference": (
            None
            if session.reference is None
            else {
                "kind": session.reference.kind,
                "sensor": session.reference.sensor,
                "fs_hz": session.reference.fs_hz,
                "path": str(session.reference.path) if session.reference.path else None,
            }
        ),
        "metadata": session.metadata,
    }
