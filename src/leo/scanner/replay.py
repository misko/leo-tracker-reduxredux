"""Contracts and in-process values for deterministic scanner replay datasets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Protocol, Self

import numpy as np
import numpy.typing as npt
from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.radio import RadioSettingsV1
from leo.contracts.recording import CompressionSettingsV1, Identifier
from leo.contracts.states import SampleFormat, SampleLayout
from leo.scanner.models import ScannerConfiguration, ScannerModel, ScanTarget


class ScannerReplaySplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class ScannerReferenceLabel(StrEnum):
    ACTIVE = "active"
    QUIET = "quiet"
    AMBIGUOUS = "ambiguous"


class ScannerReplayLabelEvidenceV1(ScannerModel):
    """Immutable reference to the evidence used to assign one silver label."""

    schema_version: Literal[1] = 1
    method: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    digest: Sha256Digest
    uri: Annotated[str | None, StringConstraints(min_length=1, max_length=1024)] = None


class ScannerReplayFrameRecipeV1(ScannerModel):
    """Selection of one exact dwell from an immutable recording stream."""

    schema_version: Literal[1] = 1
    target_index: Annotated[int, Field(ge=0)]
    source_session_id: Identifier
    source_stream_id: Identifier
    source_sample_start: Annotated[int, Field(ge=0)]
    label: ScannerReferenceLabel
    evidence: ScannerReplayLabelEvidenceV1


class ScannerReplaySweepRecipeV1(ScannerModel):
    schema_version: Literal[1] = 1
    sweep_id: Identifier
    split: ScannerReplaySplit
    frames: tuple[ScannerReplayFrameRecipeV1, ...]


class ScannerReplayDatasetRecipeV1(ScannerModel):
    """Deterministic recipe whose source groups may not cross dataset splits."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_replay_recipe"] = "starlink_scanner_replay_recipe"
    dataset_id: Identifier
    generator_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    configuration: ScannerConfiguration
    sweeps: tuple[ScannerReplaySweepRecipeV1, ...]

    @model_validator(mode="after")
    def _dataset_is_consistent(self) -> Self:
        if not self.sweeps:
            raise ValueError("scanner replay recipe requires at least one sweep")
        sweep_ids = tuple(sweep.sweep_id for sweep in self.sweeps)
        if len(set(sweep_ids)) != len(sweep_ids):
            raise ValueError("scanner replay sweep IDs must be unique")
        source_splits: dict[str, ScannerReplaySplit] = {}
        expected_targets = tuple(range(len(self.configuration.targets)))
        for sweep in self.sweeps:
            actual_targets = tuple(frame.target_index for frame in sweep.frames)
            if actual_targets != expected_targets:
                raise ValueError("scanner replay sweep must cover the ordered target plan exactly")
            for frame in sweep.frames:
                previous = source_splits.setdefault(frame.source_session_id, sweep.split)
                if previous is not sweep.split:
                    raise ValueError("one source recording session cannot cross dataset splits")
        return self


class ScannerReplaySourceV1(ScannerModel):
    """Verified source coordinates for one materialized replay frame."""

    schema_version: Literal[1] = 1
    session_id: Identifier
    recording_uri: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    recording_manifest_sha256: Sha256Digest
    stream_id: Identifier
    radio_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    source_receiver_ids: tuple[int, ...]
    source_sample_start: Annotated[int, Field(ge=0)]
    source_sample_count: Annotated[int, Field(gt=0)]
    requested_settings: RadioSettingsV1
    applied_settings: RadioSettingsV1

    @model_validator(mode="after")
    def _source_is_consistent(self) -> Self:
        if (
            self.source_receiver_ids != self.requested_settings.receiver_ids
            or self.source_receiver_ids != self.applied_settings.receiver_ids
        ):
            raise ValueError("replay source receivers disagree with radio settings")
        return self


class ScannerReplayIqFrameV1(ScannerModel):
    """One source-provenanced fixed-tuning frame in a replay payload."""

    schema_version: Literal[1] = 1
    frame_index: Annotated[int, Field(ge=0)]
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    source: ScannerReplaySourceV1
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest


class ScannerReplayIqBundleManifestV1(ScannerModel):
    """Commit record for one synthetic sweep with PR #5-compatible IQ bytes."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_replay_iq_bundle"] = "starlink_scanner_replay_iq_bundle"
    dataset_id: Identifier
    sweep_id: Identifier
    split: ScannerReplaySplit
    generator_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    configuration: ScannerConfiguration
    frames: tuple[ScannerReplayIqFrameV1, ...]
    total_sample_count: Annotated[int, Field(gt=0)]
    payload_relative_path: Literal["iq.ci16.zst"] = "iq.ci16.zst"
    sample_format: Literal[SampleFormat.CI16_LE] = SampleFormat.CI16_LE
    sample_layout: Literal[SampleLayout.SAMPLE_RECEIVER_IQ] = SampleLayout.SAMPLE_RECEIVER_IQ
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    compressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest
    compressed_sha256: Sha256Digest
    compression: CompressionSettingsV1

    @model_validator(mode="after")
    def _bundle_is_consistent(self) -> Self:
        if len(self.frames) != len(self.configuration.targets):
            raise ValueError("scanner replay bundle must contain every configured target")
        receiver_count = len(self.configuration.receiver_ids)
        expected_sample_start = 0
        for frame_index, frame in enumerate(self.frames):
            if frame.frame_index != frame_index or frame.target_index != frame_index:
                raise ValueError("scanner replay frames must retain scan-plan order")
            if frame.target != self.configuration.targets[frame.target_index]:
                raise ValueError("scanner replay frame target disagrees with the scan plan")
            if frame.sample_start != expected_sample_start:
                raise ValueError("scanner replay frame sample ranges must be contiguous")
            if frame.sample_count != self.configuration.dwell_samples:
                raise ValueError("scanner replay frame sample count disagrees with dwell plan")
            if frame.source.source_sample_count != frame.sample_count:
                raise ValueError("scanner replay source count disagrees with its frame")
            if frame.source.source_receiver_ids != self.configuration.receiver_ids:
                raise ValueError("scanner replay source receivers disagree with scanner plan")
            requested = frame.source.requested_settings
            applied = frame.source.applied_settings
            if requested.center_frequency_hz != frame.target.if_center_hz:
                raise ValueError("scanner replay requested source IF disagrees with target")
            if applied.sample_rate_hz != self.configuration.sample_rate_hz:
                raise ValueError("scanner replay source sample rate disagrees with scanner plan")
            if applied.bandwidth_hz != self.configuration.bandwidth_hz:
                raise ValueError("scanner replay source bandwidth disagrees with scanner plan")
            expected_frame_bytes = frame.sample_count * receiver_count * 4
            if frame.uncompressed_bytes != expected_frame_bytes:
                raise ValueError("scanner replay frame bytes disagree with CI16 geometry")
            expected_sample_start += frame.sample_count
        if expected_sample_start != self.total_sample_count:
            raise ValueError("scanner replay total sample count disagrees with frames")
        if self.uncompressed_bytes != self.total_sample_count * receiver_count * 4:
            raise ValueError("scanner replay payload bytes disagree with CI16 geometry")
        return self


class ScannerReplayTruthItemV1(ScannerModel):
    schema_version: Literal[1] = 1
    sweep_id: Identifier
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    label: ScannerReferenceLabel
    evidence: ScannerReplayLabelEvidenceV1


class ScannerReplayTruthV1(ScannerModel):
    """Labels held outside replay bundles so the scanner cannot consume them."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_replay_truth"] = "starlink_scanner_replay_truth"
    dataset_id: Identifier
    items: tuple[ScannerReplayTruthItemV1, ...]

    @model_validator(mode="after")
    def _items_are_unique(self) -> Self:
        identities = tuple((item.sweep_id, item.target_index) for item in self.items)
        if not identities or len(set(identities)) != len(identities):
            raise ValueError("scanner replay truth items must be non-empty and unique")
        return self


class ScannerReplayDatasetEntryV1(ScannerModel):
    schema_version: Literal[1] = 1
    sweep_id: Identifier
    split: ScannerReplaySplit
    bundle_relative_path: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    manifest_sha256: Sha256Digest

    @field_validator("bundle_relative_path")
    @classmethod
    def _path_is_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "." in path.parts or str(path) != value:
            raise ValueError("replay bundle path must be normalized and relative")
        return value


class ScannerReplayDatasetManifestV1(ScannerModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_replay_dataset"] = "starlink_scanner_replay_dataset"
    dataset_id: Identifier
    generator_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    configuration: ScannerConfiguration
    entries: tuple[ScannerReplayDatasetEntryV1, ...]
    recipe_relative_path: Literal["recipe.v1.json"] = "recipe.v1.json"
    recipe_sha256: Sha256Digest
    truth_relative_path: Literal["truth.v1.json"] = "truth.v1.json"
    truth_sha256: Sha256Digest

    @model_validator(mode="after")
    def _entries_are_unique(self) -> Self:
        identities = tuple(entry.sweep_id for entry in self.entries)
        paths = tuple(entry.bundle_relative_path for entry in self.entries)
        if not identities or len(set(identities)) != len(identities):
            raise ValueError("scanner replay dataset entries must be non-empty and unique")
        if len(set(paths)) != len(paths):
            raise ValueError("scanner replay dataset bundle paths must be unique")
        return self


@dataclass(frozen=True, slots=True)
class PreparedScannerReplayFrame:
    recipe: ScannerReplayFrameRecipeV1
    source: ScannerReplaySourceV1
    samples: npt.NDArray[np.int16]

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        expected = (self.source.source_sample_count, len(self.source.source_receiver_ids), 2)
        if values.dtype != np.dtype("<i2") or values.shape != expected:
            raise ValueError(f"prepared replay CI16 shape/dtype is {values.shape}/{values.dtype}")
        if not values.flags.c_contiguous:
            raise ValueError("prepared replay CI16 must be C-contiguous")
        if (
            self.source.session_id != self.recipe.source_session_id
            or self.source.stream_id != self.recipe.source_stream_id
            or self.source.source_sample_start != self.recipe.source_sample_start
        ):
            raise ValueError("prepared replay provenance disagrees with its recipe")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


@dataclass(frozen=True, slots=True)
class PreparedScannerReplaySweep:
    recipe: ScannerReplaySweepRecipeV1
    frames: tuple[PreparedScannerReplayFrame, ...]


@dataclass(frozen=True, slots=True)
class PreparedScannerReplayDataset:
    recipe: ScannerReplayDatasetRecipeV1
    sweeps: tuple[PreparedScannerReplaySweep, ...]


class ScannerReplaySourcePort(Protocol):
    def read_frame(
        self,
        recipe: ScannerReplayFrameRecipeV1,
        target: ScanTarget,
        configuration: ScannerConfiguration,
    ) -> PreparedScannerReplayFrame: ...


def prepare_scanner_replay_dataset(
    recipe: ScannerReplayDatasetRecipeV1,
    source: ScannerReplaySourcePort,
) -> PreparedScannerReplayDataset:
    """Resolve and verify every source slice without writing dataset state."""

    sweeps = tuple(
        PreparedScannerReplaySweep(
            recipe=sweep,
            frames=tuple(
                source.read_frame(frame, recipe.configuration.targets[index], recipe.configuration)
                for index, frame in enumerate(sweep.frames)
            ),
        )
        for sweep in recipe.sweeps
    )
    return PreparedScannerReplayDataset(recipe=recipe, sweeps=sweeps)
