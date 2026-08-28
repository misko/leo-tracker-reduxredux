"""Immutable scientific contracts for the Standard GLRT64 receiver hierarchy.

These contracts intentionally contain no catalog, storage, HTTP, or CLI
identities.  They are reusable scientific bytes; run-owned provenance belongs
in the pipeline membership wrapper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import (
    Identifier,
    RecordingManifestV1,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingManifestV5,
)
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ValidityInventoryV1

BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
MethodName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
]

STANDARD_POWER_TIMELINE_KIND = "standard.power-timeline"
STANDARD_NUMERICAL_WATERFALL_KIND = "standard.numerical-waterfall"
STANDARD_PATH_INPUT_BIND_KIND = "standard.path-input-bind"
STANDARD_PROBE_SCHEDULE_KIND = "standard.probe-schedule"
STANDARD_QUALITY_SOURCE_BIND_KIND = "standard.quality-source-bind"
STANDARD_POWER_SOURCE_BIND_KIND = "standard.power-source-bind"
STANDARD_WATERFALL_SOURCE_BIND_KIND = "standard.waterfall-source-bind"
STANDARD_SCHEDULE_SOURCE_BIND_KIND = "standard.schedule-source-bind"
STANDARD_PILOT_SOURCE_BIND_KIND = "standard.pilot-source-bind"
STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND = "standard.trajectory-bank-source-bind"
STANDARD_TRAJECTORY_FEEDBACK_SOURCE_BIND_KIND = "standard.trajectory-feedback-source-bind"
STANDARD_TRAJECTORY_TABLE_SOURCE_BIND_KIND = "standard.trajectory-table-source-bind"


class StandardScientificStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_RESULT = "no_result"
    INSUFFICIENT_DATA = "insufficient_data"


class FrequencyReference(StrEnum):
    CALIBRATED = "calibrated"
    UNCALIBRATED_PRIOR = "uncalibrated_prior"


class AssociationStatus(StrEnum):
    EVALUATED = "evaluated"
    UNAVAILABLE_UNCALIBRATED_PRIOR = "unavailable_uncalibrated_prior"
    INSUFFICIENT_DATA = "insufficient_data"


class StandardProductRefV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=128,
            pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        ),
    ]
    contract_schema: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    content_digest: Sha256Digest
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0)]
    truncated_point_count: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> Self:
        if self.returned_point_count + self.truncated_point_count != self.source_point_count:
            raise ValueError("returned plus truncated points must equal source points")
        return self


class StandardBoundPredecessorV1(ContractModel):
    """One exact reusable predecessor named by product kind and content."""

    schema_version: Literal[1] = 1
    kind: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=128,
            pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        ),
    ]
    content_digest: Sha256Digest


class StandardSourceBindingV1(ContractModel):
    """Release-independent derivation metadata around one reusable product."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-source-binding-v1"]
    stage_key: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=128,
            pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        ),
    ]
    product_kind: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=128,
            pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
        ),
    ]
    product_schema_version: Annotated[int, Field(ge=1)]
    product_content_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    path_input_bind_content_digest: Sha256Digest
    predecessors: tuple[StandardBoundPredecessorV1, ...] = ()

    @model_validator(mode="after")
    def _predecessors_are_canonical(self) -> Self:
        identities = tuple((item.kind, item.content_digest) for item in self.predecessors)
        if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
            raise ValueError("source-bound predecessors must be unique and ordered")
        return self


class PowerWindowV2(ContractModel):
    """One bounded Standard power interval in explicit CI16 full-scale units."""

    schema_version: Literal[2] = 2
    window_index: Annotated[int, Field(ge=0)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_stop: Annotated[int, Field(gt=0)]
    time_start_s: Annotated[float, Field(ge=0)]
    time_stop_s: Annotated[float, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    mean_power_full_scale_squared: Annotated[float | None, Field(ge=0)]
    mean_power_dbfs: float | None

    @field_validator(
        "time_start_s",
        "time_stop_s",
        "mean_power_full_scale_squared",
        "mean_power_dbfs",
    )
    @classmethod
    def _numbers_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("power timeline values must be finite")
        return value

    @model_validator(mode="after")
    def _window_is_consistent(self) -> Self:
        if self.sample_stop <= self.sample_start or self.time_stop_s <= self.time_start_s:
            raise ValueError("power window must have positive extent")
        if self.observed_sample_count > self.sample_stop - self.sample_start:
            raise ValueError("power window observed count exceeds its extent")
        if self.observed_sample_count == 0 and self.mean_power_full_scale_squared is not None:
            raise ValueError("empty power window cannot claim a power measurement")
        if self.observed_sample_count and self.mean_power_full_scale_squared is None:
            raise ValueError("observed power window requires a linear measurement")
        if self.mean_power_dbfs is not None and (
            self.mean_power_full_scale_squared is None or self.mean_power_full_scale_squared <= 0
        ):
            raise ValueError("dBFS power requires positive linear power")
        return self


class StandardPowerTimelineV2(ContractModel):
    """Run-independent bounded power timeline; additive to ``power.summary`` v1."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["bounded-power-timeline-v2"]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    expected_sample_count: Annotated[int, Field(ge=0)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    coverage_fraction: Annotated[float, Field(ge=0, le=1)]
    uncovered_region_count: Annotated[int, Field(ge=0)]
    receiver_ids: tuple[Annotated[int, Field(ge=0, le=255)], ...]
    normalization: Literal["E[I^2+Q^2]/32768^2"]
    logarithmic_unit: Literal["dBFS"]
    window_samples: Annotated[int, Field(gt=0)]
    source_window_count: Annotated[int, Field(ge=0)]
    returned_window_count: Annotated[int, Field(ge=0)]
    truncated_window_count: Annotated[int, Field(ge=0)]
    timeline: tuple[PowerWindowV2, ...]
    maximum_working_set_bytes: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _timeline_is_consistent(self) -> Self:
        if len(self.receiver_ids) != 1:
            raise ValueError("Standard power timeline must contain exactly one receiver")
        if self.observed_sample_count > self.expected_sample_count:
            raise ValueError("power observed count exceeds its declaration")
        if self.missing_sample_count != self.expected_sample_count - self.observed_sample_count:
            raise ValueError("power missing count disagrees with coverage")
        expected_fraction = (
            self.observed_sample_count / self.expected_sample_count
            if self.expected_sample_count
            else 0.0
        )
        if not math.isclose(self.coverage_fraction, expected_fraction, abs_tol=1e-15):
            raise ValueError("power coverage fraction disagrees with counts")
        expected_source = (
            math.ceil(self.expected_sample_count / self.window_samples)
            if self.expected_sample_count
            else 0
        )
        if self.source_window_count != expected_source:
            raise ValueError("power source window count disagrees with geometry")
        if self.returned_window_count != len(self.timeline):
            raise ValueError("power returned window count disagrees with timeline")
        if self.returned_window_count + self.truncated_window_count != self.source_window_count:
            raise ValueError("power window truncation accounting is inconsistent")
        for index, window in enumerate(self.timeline):
            expected_start = index * self.window_samples
            expected_stop = min(
                self.expected_sample_count,
                expected_start + self.window_samples,
            )
            if (
                window.window_index != index
                or window.sample_start != expected_start
                or window.sample_stop != expected_stop
                or not math.isclose(
                    window.time_start_s,
                    expected_start / self.sample_rate_hz,
                    abs_tol=1e-15,
                )
                or not math.isclose(
                    window.time_stop_s,
                    expected_stop / self.sample_rate_hz,
                    abs_tol=1e-15,
                )
            ):
                raise ValueError("power timeline geometry is not canonical")
        if not self.truncated_window_count and (
            sum(item.observed_sample_count for item in self.timeline) != self.observed_sample_count
        ):
            raise ValueError("power timeline coverage disagrees with the report")
        return self


class WaterfallCoverageV2(ContractModel):
    schema_version: Literal[2] = 2
    expected_samples: Annotated[int, Field(ge=0)]
    observed_samples: Annotated[int, Field(ge=0)]
    transformed_samples: Annotated[int, Field(ge=0)]
    missing_samples: Annotated[int, Field(ge=0)]
    gap_count: Annotated[int, Field(ge=0)]
    observed_fraction: Annotated[float, Field(ge=0, le=1)]
    transformed_fraction: Annotated[float, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def _coverage_is_consistent(self) -> Self:
        if self.observed_samples > self.expected_samples:
            raise ValueError("waterfall observed samples exceed declaration")
        if self.transformed_samples > self.observed_samples:
            raise ValueError("waterfall transformed samples exceed observations")
        if self.missing_samples != self.expected_samples - self.observed_samples:
            raise ValueError("waterfall missing samples disagree with coverage")
        denominator = self.expected_samples
        observed = self.observed_samples / denominator if denominator else 0.0
        transformed = self.transformed_samples / denominator if denominator else 0.0
        if not math.isclose(self.observed_fraction, observed, abs_tol=1e-15):
            raise ValueError("waterfall observed fraction disagrees with counts")
        if not math.isclose(self.transformed_fraction, transformed, abs_tol=1e-15):
            raise ValueError("waterfall transformed fraction disagrees with counts")
        return self


class NumericalWaterfallTileV2(ContractModel):
    schema_version: Literal[2] = 2
    time_bin: Annotated[int, Field(ge=0)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_stop: Annotated[int, Field(ge=0)]
    transform_count: Annotated[int, Field(ge=0)]
    receiver_power_dbfs: tuple[tuple[float | None, ...], ...]

    @field_validator("receiver_power_dbfs")
    @classmethod
    def _powers_are_finite(
        cls, value: tuple[tuple[float | None, ...], ...]
    ) -> tuple[tuple[float | None, ...], ...]:
        if any(item is not None and not math.isfinite(item) for row in value for item in row):
            raise ValueError("waterfall power values must be finite")
        return value

    @model_validator(mode="after")
    def _tile_extent_is_ordered(self) -> Self:
        if self.sample_stop < self.sample_start:
            raise ValueError("waterfall tile end precedes its start")
        return self


class StandardNumericalWaterfallV2(ContractModel):
    """Raw numerical waterfall product; additive to image-oriented v1 tiles."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-numerical-waterfall-v2"]
    kernel_algorithm_version: Literal["bounded-waterfall-v1"]
    config_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    fft_samples: Annotated[int, Field(gt=0)]
    frequency_bin_count: Annotated[int, Field(gt=0)]
    time_bin_count: Annotated[int, Field(gt=0)]
    receiver_ids: tuple[Annotated[int, Field(ge=0, le=255)], ...]
    frequency_bin_centers_hz: tuple[float, ...]
    coverage: WaterfallCoverageV2
    tiles: tuple[NumericalWaterfallTileV2, ...]
    maximum_working_set_bytes: Annotated[int, Field(gt=0)]

    @field_validator("frequency_bin_centers_hz")
    @classmethod
    def _frequencies_are_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("waterfall frequencies must be finite")
        return value

    @model_validator(mode="after")
    def _waterfall_is_consistent(self) -> Self:
        if len(self.receiver_ids) != 1:
            raise ValueError("Standard numerical waterfall requires exactly one receiver")
        if len(self.frequency_bin_centers_hz) != self.frequency_bin_count:
            raise ValueError("waterfall frequency axis disagrees with its bin count")
        if tuple(sorted(self.frequency_bin_centers_hz)) != self.frequency_bin_centers_hz:
            raise ValueError("waterfall frequency centers must be ordered")
        if len(self.tiles) != self.time_bin_count:
            raise ValueError("waterfall time axis disagrees with its bin count")
        expected_samples = self.coverage.expected_samples
        samples_per_bin = max(1, math.ceil(max(expected_samples, 1) / self.time_bin_count))
        for index, tile in enumerate(self.tiles):
            if (
                tile.time_bin != index
                or tile.sample_start != index * samples_per_bin
                or tile.sample_stop
                != min(expected_samples, index * samples_per_bin + samples_per_bin)
            ):
                raise ValueError("waterfall tile geometry is not canonical")
            if len(tile.receiver_power_dbfs) != len(self.receiver_ids) or any(
                len(row) != self.frequency_bin_count for row in tile.receiver_power_dbfs
            ):
                raise ValueError("waterfall tile matrix shape is inconsistent")
        if sum(item.transform_count for item in self.tiles) * self.fft_samples != (
            self.coverage.transformed_samples
        ):
            raise ValueError("waterfall transform count disagrees with coverage")
        return self


class StreamTimingEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    first_estimate_utc_ns: Annotated[int, Field(ge=0)]
    first_earliest_utc_ns: Annotated[int, Field(ge=0)]
    first_latest_utc_ns: Annotated[int, Field(ge=0)]
    last_estimate_utc_ns: Annotated[int, Field(ge=0)]
    last_earliest_utc_ns: Annotated[int, Field(ge=0)]
    last_latest_utc_ns: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _bounds_are_ordered(self) -> Self:
        if not self.first_earliest_utc_ns <= self.first_estimate_utc_ns <= self.first_latest_utc_ns:
            raise ValueError("first-sample estimate lies outside its bounds")
        if not self.last_earliest_utc_ns <= self.last_estimate_utc_ns <= self.last_latest_utc_ns:
            raise ValueError("last-sample estimate lies outside its bounds")
        if self.first_estimate_utc_ns > self.last_estimate_utc_ns:
            raise ValueError("last-sample estimate precedes first-sample estimate")
        return self


class ReceiverFrequencyReferenceV1(ContractModel):
    schema_version: Literal[1] = 1
    reference: FrequencyReference
    center_frequency_hz: float | None = None
    uncertainty_hz: Annotated[float | None, Field(ge=0)] = None
    calibration_digest: Sha256Digest | None = None

    @field_validator("center_frequency_hz", "uncertainty_hz")
    @classmethod
    def _optional_floats_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("frequency values must be finite")
        return value

    @model_validator(mode="after")
    def _reference_is_honest(self) -> Self:
        calibrated = self.reference is FrequencyReference.CALIBRATED
        fields_present = (
            self.center_frequency_hz is not None,
            self.uncertainty_hz is not None,
            self.calibration_digest is not None,
        )
        if calibrated and not all(fields_present):
            raise ValueError("calibrated frequency requires center, uncertainty, and digest")
        if not calibrated and any(fields_present):
            raise ValueError("uncalibrated prior cannot carry calibration authority")
        return self


class _StandardPathInputBindBase(ContractModel):
    """Fields and invariants shared by immutable path-binding schema versions."""

    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    manifest_digest: Sha256Digest
    raw_integrity_attestation_digest: Sha256Digest
    selected_stream_digest: Sha256Digest
    compressed_chunk_closure_digest: Sha256Digest
    uncompressed_chunk_closure_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    profile_revision_digest: Sha256Digest
    capture_plan_digest: Sha256Digest
    receiver_settings_digest: Sha256Digest
    science_configuration_digest: Sha256Digest
    science_implementation_digest: Sha256Digest
    capture_lineage_resolution: Literal["resolved", "legacy_unresolved"]
    physical_receiver_id: Identifier | None = None
    hardware_epoch_id: Identifier | None = None
    tuned_center_frequency_hz: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    declared_sample_count: Annotated[int, Field(ge=0)]
    timing: StreamTimingEvidenceV1
    frequency_reference: ReceiverFrequencyReferenceV1
    binding_digest: Sha256Digest

    @model_validator(mode="after")
    def _binding_is_consistent(self) -> Self:
        resolved = self.capture_lineage_resolution == "resolved"
        if resolved != (
            self.physical_receiver_id is not None and self.hardware_epoch_id is not None
        ):
            raise ValueError("capture lineage resolution disagrees with hardware identities")
        if not resolved and (
            self.physical_receiver_id is not None or self.hardware_epoch_id is not None
        ):
            raise ValueError("legacy-unresolved capture cannot fabricate hardware identity")
        if self.binding_digest != _content_digest(self, "binding_digest"):
            raise ValueError("path input binding digest does not match content")
        return self


class StandardPathInputBindV2(_StandardPathInputBindBase):
    """Exact immutable receiver-path source selected by the V2 input-bind node."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-path-input-bind-v2"]


class StandardPathInputBindV3(_StandardPathInputBindBase):
    """Path authority plus explicit manifest-declared Starlink tuning intent."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-path-input-bind-v3"]
    starlink_channel: Annotated[int, Field(ge=1, le=8)]
    starlink_edge: StarlinkEdge
    starlink_tuning_evidence_source: Literal["per_stream_manifest_tag", "capture_profile"]


class StandardPathInputBindV4(_StandardPathInputBindBase):
    """Native-rate path authority over the complete logical device-time span.

    V4 is additive: V2/V3 continue to bind their historical packed-IQ source
    semantics.  The embedded validity inventory is the sole authority for
    observed, missing, and continuity-segment coordinates in Standard-native.
    """

    schema_version: Literal[4] = 4
    algorithm_version: Literal["standard-path-input-bind-v4"]
    starlink_channel: Annotated[int, Field(ge=1, le=8)]
    starlink_edge: StarlinkEdge
    starlink_tuning_evidence_source: Literal["per_stream_manifest_tag", "capture_profile"]
    rf_bandwidth_hz: Annotated[int, Field(gt=0)]
    requested_sample_count: Annotated[int, Field(gt=0)]
    requested_duration_seconds: Annotated[Decimal, Field(gt=0)]
    logical_sample_count: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    observed_iq_digest: Sha256Digest
    logical_iq_digest: Sha256Digest
    timeline_sha256: Sha256Digest
    gap_map_sha256: Sha256Digest
    gap_map_content_digest: Sha256Digest
    validity_inventory_sha256: Sha256Digest
    first_device_sample_counter: Annotated[int, Field(ge=0)]
    last_device_sample_counter_inclusive: Annotated[int, Field(ge=0)]
    validity_inventory: ValidityInventoryV1

    @model_validator(mode="after")
    def _native_device_axis_is_closed(self) -> Self:
        if self.sample_rate_hz not in {2_500_000, 3_000_000, 5_000_000, 10_000_000}:
            raise ValueError("Standard-native sample rate is not reviewed")
        if not (
            self.declared_sample_count == self.requested_sample_count == self.logical_sample_count
        ):
            raise ValueError("Standard-native declared, requested, and logical counts differ")
        if self.logical_sample_count != self.observed_sample_count + self.missing_sample_count:
            raise ValueError("Standard-native logical count does not close observed and missing IQ")
        expected_duration = Decimal(self.requested_sample_count) / Decimal(self.sample_rate_hz)
        if self.requested_duration_seconds != expected_duration:
            raise ValueError("Standard-native requested duration disagrees with sample geometry")
        if (
            self.last_device_sample_counter_inclusive - self.first_device_sample_counter + 1
            != self.logical_sample_count
        ):
            raise ValueError("Standard-native counter span disagrees with logical sample count")

        validity = self.validity_inventory
        if (
            validity.stream_id != self.stream_id
            or validity.timeline_sha256 != self.timeline_sha256
            or validity.gap_map_content_digest != self.gap_map_content_digest
            or validity.first_device_sample_counter != self.first_device_sample_counter
            or validity.logical_sample_count != self.logical_sample_count
            or validity.observed_sample_count != self.observed_sample_count
            or validity.missing_sample_count != self.missing_sample_count
            or validity.inventory_digest != self.validity_inventory_sha256
        ):
            raise ValueError("Standard-native path facts disagree with the validity inventory")
        return self


@dataclass(frozen=True, slots=True)
class ManifestStarlinkTuningIntent:
    channel: int
    edge: StarlinkEdge
    evidence_source: Literal["per_stream_manifest_tag", "capture_profile"]


def resolve_manifest_starlink_tuning(
    manifest: RecordingManifestV1 | RecordingManifestV3 | RecordingManifestV4 | RecordingManifestV5,
) -> dict[str, ManifestStarlinkTuningIntent]:
    """Resolve explicit per-stream Starlink intent without frequency inference."""

    stream_ids = {stream.stream_id for stream in manifest.streams}
    tuning_tags = tuple(
        tag
        for tag in manifest.tags
        if tag.startswith("tuning") and not tag.startswith("tuning_policy:")
    )
    channel_by_value = {f"ch{channel}": channel for channel in range(1, 9)}
    if tuning_tags:
        resolved: dict[str, ManifestStarlinkTuningIntent] = {}
        for tag in tuning_tags:
            parts = tag.split(":")
            if len(parts) != 4:
                raise ValueError(f"invalid per-stream Starlink tuning tag: {tag}")
            _, stream_id, channel_value, edge_value = parts
            channel = channel_by_value.get(channel_value)
            try:
                edge = StarlinkEdge(edge_value)
            except ValueError as error:
                raise ValueError(f"invalid per-stream Starlink tuning tag: {tag}") from error
            if stream_id not in stream_ids or channel is None or stream_id in resolved:
                raise ValueError(f"invalid per-stream Starlink tuning tag: {tag}")
            resolved[stream_id] = ManifestStarlinkTuningIntent(
                channel=channel,
                edge=edge,
                evidence_source="per_stream_manifest_tag",
            )
        if set(resolved) != stream_ids:
            raise ValueError("per-stream Starlink tuning tags must cover every manifest stream")
        return resolved

    if type(manifest) is RecordingManifestV5:
        raise ValueError("production V5 manifest requires complete per-stream tuning tags")
    if isinstance(manifest, RecordingManifestV4):
        return {
            stream_id: ManifestStarlinkTuningIntent(
                channel=manifest.capture_plan.starlink_channel,
                edge=manifest.capture_plan.starlink_edge,
                evidence_source="capture_profile",
            )
            for stream_id in stream_ids
        }

    profile = manifest.capture_plan.profile_revision.profile
    channel = channel_by_value.get(profile.starlink_channel or "")
    if channel is None or profile.starlink_edge is None:
        raise ValueError(
            "Standard analysis requires explicit profile or complete per-stream Starlink tuning"
        )
    return {
        stream_id: ManifestStarlinkTuningIntent(
            channel=channel,
            edge=profile.starlink_edge,
            evidence_source="capture_profile",
        )
        for stream_id in stream_ids
    }


class ProbeWindowV1(ContractModel):
    schema_version: Literal[1] = 1
    probe_id: Sha256Digest
    coarse_window_index: Annotated[int, Field(ge=0)]
    subwindow_index: Annotated[int, Field(ge=0)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    time_s: Annotated[float, Field(ge=0)]

    @field_validator("time_s")
    @classmethod
    def _time_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("probe time must be finite")
        return value


class ProbeScheduleV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-probe-schedule-v1"] = "standard-probe-schedule-v1"
    sample_rate_hz: Annotated[int, Field(gt=0)]
    declared_sample_count: Annotated[int, Field(ge=0)]
    coarse_window_ms: Literal[1000] = 1000
    subwindow_ms: Annotated[int, Field(gt=0, le=1000)] = 50
    probe_ms: Annotated[int, Field(gt=0, le=1000)] = 20
    maximum_coarse_windows: Annotated[int, Field(gt=0, le=86_400)] = 120
    source_probe_count: Annotated[int, Field(ge=0)]
    returned_probe_count: Annotated[int, Field(ge=0)]
    truncated_probe_count: Annotated[int, Field(ge=0)]
    probes: tuple[ProbeWindowV1, ...]
    schedule_digest: Sha256Digest

    @model_validator(mode="after")
    def _schedule_is_canonical(self) -> Self:
        if 1000 % self.subwindow_ms:
            raise ValueError("subwindow duration must divide one second")
        if self.probe_ms > self.subwindow_ms:
            raise ValueError("probe cannot exceed its subwindow")
        if self.returned_probe_count != len(self.probes):
            raise ValueError("returned probe count disagrees with probes")
        if self.returned_probe_count + self.truncated_probe_count != self.source_probe_count:
            raise ValueError("probe truncation accounting is inconsistent")
        starts = tuple(item.sample_start for item in self.probes)
        ids = tuple(item.probe_id for item in self.probes)
        if starts != tuple(sorted(starts)) or len(set(starts)) != len(starts):
            raise ValueError("probe starts must be unique and ordered")
        if len(set(ids)) != len(ids):
            raise ValueError("probe IDs must be unique")
        if self.schedule_digest != _content_digest(self, "schedule_digest"):
            raise ValueError("schedule digest does not match content")
        return self


class ProbeWindowV2(ContractModel):
    """One explicitly placed probe within a 50 ms scheduling subwindow."""

    schema_version: Literal[2] = 2
    probe_id: Sha256Digest
    coarse_window_index: Annotated[int, Field(ge=0)]
    subwindow_index: Annotated[int, Field(ge=0)]
    probe_offset_ms: Annotated[int, Field(ge=0, le=1000)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    time_s: Annotated[float, Field(ge=0)]

    @field_validator("time_s")
    @classmethod
    def _time_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("probe time must be finite")
        return value


class ProbeScheduleV2(ContractModel):
    """Bounded schedule with an explicit ordered probe pattern."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-probe-schedule-v2"] = "standard-probe-schedule-v2"
    sample_rate_hz: Annotated[int, Field(gt=0)]
    declared_sample_count: Annotated[int, Field(ge=0)]
    coarse_window_ms: Literal[1000] = 1000
    subwindow_ms: Annotated[int, Field(gt=0, le=1000)] = 50
    probe_ms: Annotated[int, Field(gt=0, le=1000)] = 20
    probe_offsets_ms: Annotated[
        tuple[Annotated[int, Field(ge=0, le=1000)], ...], Field(min_length=1, max_length=20)
    ]
    maximum_coarse_windows: Annotated[int, Field(gt=0, le=86_400)] = 120
    source_probe_count: Annotated[int, Field(ge=0)]
    returned_probe_count: Annotated[int, Field(ge=0)]
    truncated_probe_count: Annotated[int, Field(ge=0)]
    probes: tuple[ProbeWindowV2, ...]
    schedule_digest: Sha256Digest

    @model_validator(mode="after")
    def _schedule_is_canonical(self) -> Self:
        if 1000 % self.subwindow_ms:
            raise ValueError("subwindow duration must divide one second")
        if self.probe_offsets_ms != tuple(sorted(set(self.probe_offsets_ms))):
            raise ValueError("probe offsets must be unique and ordered")
        if any(offset + self.probe_ms > self.subwindow_ms for offset in self.probe_offsets_ms):
            raise ValueError("probe support exceeds its subwindow")
        if self.returned_probe_count != len(self.probes):
            raise ValueError("returned probe count disagrees with probes")
        if self.returned_probe_count + self.truncated_probe_count != self.source_probe_count:
            raise ValueError("probe truncation accounting is inconsistent")
        starts = tuple(item.sample_start for item in self.probes)
        ids = tuple(item.probe_id for item in self.probes)
        if starts != tuple(sorted(starts)) or len(set(starts)) != len(starts):
            raise ValueError("probe starts must be unique and ordered")
        if len(set(ids)) != len(ids):
            raise ValueError("probe IDs must be unique")
        if any(item.probe_offset_ms not in self.probe_offsets_ms for item in self.probes):
            raise ValueError("probe carries an undeclared offset")
        if self.schedule_digest != _content_digest(self, "schedule_digest"):
            raise ValueError("schedule digest does not match content")
        return self


class PilotMethodScoreV2(ContractModel):
    schema_version: Literal[2] = 2
    method: MethodName
    exact_score: float
    control_score: float | None
    margin: float
    tracking_cfo_hz: float

    @field_validator("exact_score", "control_score", "margin", "tracking_cfo_hz")
    @classmethod
    def _scores_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("pilot score values must be finite")
        return value


class PilotCandidateV2(ContractModel):
    schema_version: Literal[2] = 2
    rank: Annotated[int, Field(ge=0)]
    local_epoch_sample: Annotated[int, Field(ge=0)]
    acquired_baseband_cfo_hz: float
    method_scores: tuple[PilotMethodScoreV2, ...]
    qam_accuracy: Annotated[float | None, Field(ge=0, le=1)] = None
    qam_evm: Annotated[float | None, Field(gt=0)] = None

    @field_validator("acquired_baseband_cfo_hz", "qam_accuracy", "qam_evm")
    @classmethod
    def _candidate_floats_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("pilot candidate values must be finite")
        return value

    @model_validator(mode="after")
    def _methods_are_unique(self) -> Self:
        methods = tuple(item.method for item in self.method_scores)
        if len(methods) != len(set(methods)):
            raise ValueError("pilot method scores must be unique")
        return self


class PilotProbeCertificateV2(ContractModel):
    schema_version: Literal[2] = 2
    probe_id: Sha256Digest
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    status: StandardScientificStatus
    source_candidate_count: Annotated[int, Field(ge=0)]
    returned_candidate_count: Annotated[int, Field(ge=0)]
    truncated_candidate_count: Annotated[int, Field(ge=0)]
    candidates: tuple[PilotCandidateV2, ...]
    reason: BoundedText
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @field_validator("time_s")
    @classmethod
    def _certificate_time_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("certificate time must be finite")
        return value

    @model_validator(mode="after")
    def _candidate_counts_are_consistent(self) -> Self:
        if self.returned_candidate_count != len(self.candidates):
            raise ValueError("returned candidate count disagrees with candidates")
        if (
            self.returned_candidate_count + self.truncated_candidate_count
            != self.source_candidate_count
        ):
            raise ValueError("candidate truncation accounting is inconsistent")
        ranks = tuple(item.rank for item in self.candidates)
        if ranks != tuple(range(len(ranks))):
            raise ValueError("candidate ranks must be contiguous from zero")
        return self


class Glrt64TimelinePointV1(ContractModel):
    schema_version: Literal[1] = 1
    probe_id: Sha256Digest
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    baseband_cfo_hz: float | None
    initial_margin: float | None
    qam_accuracy: Annotated[float | None, Field(ge=0, le=1)] = None

    @field_validator("time_s", "baseband_cfo_hz", "initial_margin", "qam_accuracy")
    @classmethod
    def _timeline_values_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("timeline values must be finite")
        return value


class StandardTrajectoryV1(ContractModel):
    schema_version: Literal[1] = 1
    trajectory_id: Sha256Digest
    family_id: Sha256Digest | None
    method: MethodName
    polynomial_degree: Annotated[int, Field(ge=1, le=3)]
    reference_time_s: Annotated[float, Field(ge=0)]
    coefficients_hz: tuple[float, ...]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    point_count: Annotated[int, Field(gt=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    bic: float
    em_iterations: Annotated[int, Field(ge=0)]
    fit_matches_well: bool
    selected_for_correction: bool
    corrected_glrt64_probe_count: Annotated[int, Field(ge=0)]
    median_glrt64_margin_delta: float | None

    @field_validator(
        "reference_time_s",
        "start_s",
        "end_s",
        "residual_rms_hz",
        "bic",
        "median_glrt64_margin_delta",
    )
    @classmethod
    def _trajectory_values_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("trajectory values must be finite")
        return value

    @field_validator("coefficients_hz")
    @classmethod
    def _coefficients_are_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("trajectory coefficients must be finite")
        return value

    @model_validator(mode="after")
    def _trajectory_geometry_is_consistent(self) -> Self:
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("coefficient count must equal polynomial degree plus one")
        if self.end_s < self.start_s:
            raise ValueError("trajectory end precedes start")
        if self.selected_for_correction and not self.fit_matches_well:
            raise ValueError("a trajectory selected for correction must match well")
        return self


class PathStandardReportV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    pipeline_family: Literal["standard-glrt64-v2"] = "standard-glrt64-v2"
    status: StandardScientificStatus
    reason: BoundedText
    sample_rate_hz: Annotated[int, Field(gt=0)]
    declared_sample_count: Annotated[int, Field(ge=0)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    coverage_fraction: Annotated[float, Field(ge=0, le=1)]
    timing: StreamTimingEvidenceV1
    frequency_reference: ReceiverFrequencyReferenceV1
    probe_schedule_digest: Sha256Digest
    method_names: tuple[MethodName, ...]
    initial_glrt64: tuple[Glrt64TimelinePointV1, ...]
    trajectories: tuple[StandardTrajectoryV1, ...]
    products: tuple[StandardProductRefV1, ...]
    truncated_candidate_count: Annotated[int, Field(ge=0)] = 0
    truncated_trajectory_count: Annotated[int, Field(ge=0)] = 0
    report_digest: Sha256Digest
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _path_report_is_canonical(self) -> Self:
        if self.observed_sample_count > self.declared_sample_count:
            raise ValueError("observed path samples exceed the declaration")
        expected_coverage = (
            self.observed_sample_count / self.declared_sample_count
            if self.declared_sample_count
            else 0.0
        )
        if not math.isclose(self.coverage_fraction, expected_coverage, abs_tol=1e-15):
            raise ValueError("path coverage fraction disagrees with sample counts")
        if len(self.method_names) != len(set(self.method_names)):
            raise ValueError("path method names must be unique")
        points = tuple((item.sample_start, item.probe_id) for item in self.initial_glrt64)
        if points != tuple(sorted(points)) or len(points) != len(set(points)):
            raise ValueError("GLRT64 points must be uniquely ordered")
        trajectories = tuple(item.trajectory_id for item in self.trajectories)
        if len(trajectories) != len(set(trajectories)):
            raise ValueError("path trajectory IDs must be unique")
        product_keys = tuple((item.kind, item.contract_schema) for item in self.products)
        if product_keys != tuple(sorted(product_keys)) or len(product_keys) != len(
            set(product_keys)
        ):
            raise ValueError("path product references must be uniquely ordered")
        if self.report_digest != _content_digest(self, "report_digest"):
            raise ValueError("path report digest does not match content")
        return self


class TrajectoryAssociationV1(ContractModel):
    schema_version: Literal[1] = 1
    association_id: Sha256Digest
    left_path_id: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    left_trajectory_id: Sha256Digest
    right_path_id: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    right_trajectory_id: Sha256Digest
    overlap_start_s: Annotated[float, Field(ge=0)]
    overlap_end_s: Annotated[float, Field(ge=0)]
    midpoint_frequency_difference_hz: Annotated[float, Field(ge=0)]
    gate_hz: Annotated[float, Field(gt=0)]

    @field_validator(
        "overlap_start_s",
        "overlap_end_s",
        "midpoint_frequency_difference_hz",
        "gate_hz",
    )
    @classmethod
    def _association_values_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("association values must be finite")
        return value

    @model_validator(mode="after")
    def _association_is_inside_gate(self) -> Self:
        if self.overlap_end_s <= self.overlap_start_s:
            raise ValueError("trajectory association requires positive overlap")
        if self.midpoint_frequency_difference_hz > self.gate_hz:
            raise ValueError("trajectory association exceeds its gate")
        return self


class RadioStandardReportV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    pipeline_family: Literal["standard-glrt64-v2"] = "standard-glrt64-v2"
    status: StandardScientificStatus
    reason: BoundedText
    declared_receiver_ids: tuple[Annotated[int, Field(ge=0, le=255)], ...]
    paths: tuple[PathStandardReportV1, ...]
    association_status: AssociationStatus
    associations: tuple[TrajectoryAssociationV1, ...]
    unmatched_trajectory_ids: tuple[
        Annotated[str, StringConstraints(min_length=1, max_length=640)], ...
    ]
    child_truncated_candidate_count: Annotated[int, Field(ge=0)]
    child_truncated_trajectory_count: Annotated[int, Field(ge=0)]
    report_digest: Sha256Digest
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _radio_report_is_canonical(self) -> Self:
        receiver_ids = tuple(item.receiver_id for item in self.paths)
        if self.declared_receiver_ids != receiver_ids or receiver_ids != tuple(
            sorted(receiver_ids)
        ):
            raise ValueError("radio path inventory must equal ordered declared receivers")
        if len(receiver_ids) != len(set(receiver_ids)):
            raise ValueError("radio receiver paths must be unique")
        if self.association_status is not AssociationStatus.EVALUATED and self.associations:
            raise ValueError("unevaluated radio report cannot contain associations")
        if self.unmatched_trajectory_ids != tuple(sorted(self.unmatched_trajectory_ids)):
            raise ValueError("unmatched trajectories must be ordered")
        if self.report_digest != _content_digest(self, "report_digest"):
            raise ValueError("radio report digest does not match content")
        return self


class PairTimingEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    synchronization_inventory_digest: Sha256Digest
    union_start_utc_ns: Annotated[int, Field(ge=0)]
    union_end_utc_ns: Annotated[int, Field(ge=0)]
    estimated_overlap_start_utc_ns: Annotated[int, Field(ge=0)]
    estimated_overlap_end_utc_ns: Annotated[int, Field(ge=0)]
    estimated_start_skew_ns: Annotated[int, Field(ge=0)]
    start_skew_uncertainty_ns: Annotated[int, Field(ge=0)]
    guaranteed_overlap_ns: Annotated[int, Field(ge=0)]
    synchronization_grade: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    phase_coherent: Literal[False] = False

    @model_validator(mode="after")
    def _pair_timing_is_valid(self) -> Self:
        if self.union_end_utc_ns <= self.union_start_utc_ns:
            raise ValueError("paired union must be positive")
        if self.estimated_overlap_end_utc_ns <= self.estimated_overlap_start_utc_ns:
            raise ValueError("paired estimated overlap must be positive")
        if self.guaranteed_overlap_ns > (
            self.estimated_overlap_end_utc_ns - self.estimated_overlap_start_utc_ns
        ):
            raise ValueError("guaranteed overlap cannot exceed estimated overlap")
        return self


class StandardPairInputBindV2(ContractModel):
    """Manifest-authoritative noncoherent pair facts unavailable from child reports."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-pair-input-bind-v2"]
    session_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    raw_integrity_attestation_digests: tuple[Sha256Digest, ...]
    timing: PairTimingEvidenceV1
    binding_digest: Sha256Digest

    @model_validator(mode="after")
    def _pair_binding_is_consistent(self) -> Self:
        if not self.raw_integrity_attestation_digests:
            raise ValueError("pair binding requires raw integrity attestation")
        if (
            tuple(sorted(set(self.raw_integrity_attestation_digests)))
            != self.raw_integrity_attestation_digests
        ):
            raise ValueError("pair raw integrity attestations must be unique and ordered")
        if self.timing.synchronization_inventory_digest != self.synchronization_inventory_digest:
            raise ValueError("pair timing does not belong to the synchronization inventory")
        if self.binding_digest != _content_digest(self, "binding_digest"):
            raise ValueError("pair input binding digest does not match content")
        return self


class PairedStandardReportV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    pipeline_family: Literal["standard-glrt64-v2"] = "standard-glrt64-v2"
    status: StandardScientificStatus
    reason: BoundedText
    radios: tuple[RadioStandardReportV1, RadioStandardReportV1]
    timing: PairTimingEvidenceV1
    association_status: AssociationStatus
    associations: tuple[TrajectoryAssociationV1, ...]
    unmatched_trajectory_ids: tuple[
        Annotated[str, StringConstraints(min_length=1, max_length=640)], ...
    ]
    child_truncated_candidate_count: Annotated[int, Field(ge=0)]
    child_truncated_trajectory_count: Annotated[int, Field(ge=0)]
    report_digest: Sha256Digest
    phase_coherent: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _paired_report_is_canonical(self) -> Self:
        radio_keys = tuple((item.stream_id, item.radio_id) for item in self.radios)
        if radio_keys != tuple(sorted(radio_keys)) or len(set(radio_keys)) != 2:
            raise ValueError("paired radio inventory must be unique and ordered")
        if self.timing.synchronization_inventory_digest != self.synchronization_inventory_digest:
            raise ValueError("paired timing inventory digest mismatch")
        if self.association_status is not AssociationStatus.EVALUATED and self.associations:
            raise ValueError("unevaluated paired report cannot contain associations")
        if self.unmatched_trajectory_ids != tuple(sorted(self.unmatched_trajectory_ids)):
            raise ValueError("unmatched trajectories must be ordered")
        if self.report_digest != _content_digest(self, "report_digest"):
            raise ValueError("paired report digest does not match content")
        return self


def _content_digest(model: ContractModel, digest_field: str) -> str:
    return canonical_digest(model.model_dump(mode="json", exclude={digest_field}))


def standard_content_digest(values: dict[str, object]) -> str:
    """Digest a contract constructor document before its digest field exists."""

    return canonical_digest(values)
