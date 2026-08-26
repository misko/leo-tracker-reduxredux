"""Canonical device-axis IQ validity and continuity-segment contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest

StreamIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]

ContinuityBoundaryReason = Literal[
    "counter_gap",
    "overflow_flag",
    "counter_gap_and_overflow",
    "terminal_counter_gap",
    "terminal_counter_gap_and_overflow",
]


class DeviceAxisContentKind(StrEnum):
    """Meaning of one canonical validity run on the logical device axis."""

    OBSERVED = "observed"
    ZERO_FILL = "zero_fill"


class ValidityRunV1(ContractModel):
    """One non-empty observed or missing run on the logical device axis."""

    schema_version: Literal[1] = 1
    run_index: Annotated[int, Field(ge=0)]
    device_sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    content_kind: DeviceAxisContentKind
    stored_sample_start: Annotated[int, Field(ge=0)] | None = None
    continuity_segment_index: Annotated[int, Field(ge=0)] | None = None

    @property
    def device_sample_stop(self) -> int:
        return self.device_sample_start + self.sample_count

    @model_validator(mode="after")
    def _coordinates_match_content(self) -> Self:
        observed = self.content_kind is DeviceAxisContentKind.OBSERVED
        has_observed_coordinates = (
            self.stored_sample_start is not None and self.continuity_segment_index is not None
        )
        if observed != has_observed_coordinates:
            raise ValueError(
                "observed validity runs require stored and segment coordinates; "
                "zero-fill runs forbid them"
            )
        return self


class ContinuitySegmentV1(ContractModel):
    """One possibly empty observed-IQ segment with global and packed coordinates."""

    schema_version: Literal[1] = 1
    segment_index: Annotated[int, Field(ge=0)]
    device_sample_start: Annotated[int, Field(ge=0)]
    device_sample_stop: Annotated[int, Field(ge=0)]
    stored_sample_start: Annotated[int, Field(ge=0)]
    stored_sample_stop: Annotated[int, Field(ge=0)]
    preceding_missing_sample_count: Annotated[int, Field(ge=0)] = 0
    preceding_boundary_reason: ContinuityBoundaryReason | None = None
    preceding_boundary_header_sha256: Sha256Digest | None = None

    @property
    def observed_sample_count(self) -> int:
        return self.device_sample_stop - self.device_sample_start

    @model_validator(mode="after")
    def _segment_is_consistent(self) -> Self:
        if self.device_sample_stop < self.device_sample_start:
            raise ValueError("continuity segment device coordinates regressed")
        if self.stored_sample_stop < self.stored_sample_start:
            raise ValueError("continuity segment stored coordinates regressed")
        if self.device_sample_stop - self.device_sample_start != (
            self.stored_sample_stop - self.stored_sample_start
        ):
            raise ValueError("continuity segment stored and device lengths disagree")

        if self.segment_index == 0:
            if (
                self.preceding_missing_sample_count
                or self.preceding_boundary_reason is not None
                or self.preceding_boundary_header_sha256 is not None
            ):
                raise ValueError("the first continuity segment cannot declare a prior boundary")
            return self

        if self.preceding_boundary_reason is None or self.preceding_boundary_header_sha256 is None:
            raise ValueError("later continuity segments require bound preceding-boundary evidence")
        has_gap = self.preceding_missing_sample_count > 0
        reason_has_gap = self.preceding_boundary_reason != "overflow_flag"
        if has_gap != reason_has_gap:
            raise ValueError("continuity segment missing count disagrees with boundary reason")
        return self


class ValidityInventoryV1(ContractModel):
    """Compact canonical validity runs derived from counter-authoritative evidence."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["counter-authoritative-validity-v1"] = (
        "counter-authoritative-validity-v1"
    )
    stream_id: StreamIdentifier
    timeline_sha256: Sha256Digest
    gap_map_content_digest: Sha256Digest
    first_device_sample_counter: Annotated[int, Field(ge=0)]
    logical_sample_count: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    continuity_boundary_count: Annotated[int, Field(ge=0)]
    runs: tuple[ValidityRunV1, ...]
    segments: tuple[ContinuitySegmentV1, ...]

    @property
    def inventory_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def _inventory_is_canonical(self) -> Self:
        if self.logical_sample_count != self.observed_sample_count + self.missing_sample_count:
            raise ValueError("validity logical count must equal observed plus missing samples")
        if not self.segments:
            raise ValueError("validity inventory requires at least one continuity segment")
        if self.continuity_boundary_count != len(self.segments) - 1:
            raise ValueError("validity boundary count disagrees with segment inventory")

        previous: ContinuitySegmentV1 | None = None
        observed_total = 0
        missing_total = 0
        for expected_index, segment in enumerate(self.segments):
            if segment.segment_index != expected_index:
                raise ValueError("validity segment indexes must be contiguous")
            if previous is None:
                if segment.device_sample_start != 0 or segment.stored_sample_start != 0:
                    raise ValueError(
                        "validity segment inventory must begin at device and stored zero"
                    )
            else:
                if segment.stored_sample_start != previous.stored_sample_stop:
                    raise ValueError("validity segment stored coordinates are not contiguous")
                if segment.device_sample_start != (
                    previous.device_sample_stop + segment.preceding_missing_sample_count
                ):
                    raise ValueError("validity segment device gap disagrees with missing count")
                missing_total += segment.preceding_missing_sample_count
            observed_total += segment.observed_sample_count
            previous = segment

        assert previous is not None
        if previous.device_sample_stop != self.logical_sample_count:
            raise ValueError("validity segments do not close the logical device span")
        if previous.stored_sample_stop != self.observed_sample_count:
            raise ValueError("validity segments do not close the packed observed span")
        if (
            observed_total != self.observed_sample_count
            or missing_total != self.missing_sample_count
        ):
            raise ValueError("validity segment counts disagree with the inventory")

        expected_runs: list[tuple[DeviceAxisContentKind, int, int, int | None, int | None]] = []
        device_cursor = 0
        for segment in self.segments:
            if segment.device_sample_start > device_cursor:
                expected_runs.append(
                    (
                        DeviceAxisContentKind.ZERO_FILL,
                        device_cursor,
                        segment.device_sample_start - device_cursor,
                        None,
                        None,
                    )
                )
            if segment.observed_sample_count:
                expected_runs.append(
                    (
                        DeviceAxisContentKind.OBSERVED,
                        segment.device_sample_start,
                        segment.observed_sample_count,
                        segment.stored_sample_start,
                        segment.segment_index,
                    )
                )
            device_cursor = segment.device_sample_stop

        if len(self.runs) != len(expected_runs):
            raise ValueError("validity run inventory is not the canonical segment expansion")
        for expected_index, (run, expected) in enumerate(
            zip(self.runs, expected_runs, strict=True)
        ):
            if run.run_index != expected_index:
                raise ValueError("validity run indexes must be contiguous")
            actual = (
                run.content_kind,
                run.device_sample_start,
                run.sample_count,
                run.stored_sample_start,
                run.continuity_segment_index,
            )
            if actual != expected:
                raise ValueError("validity runs disagree with the canonical segment expansion")
        return self
