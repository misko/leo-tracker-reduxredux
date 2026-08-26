"""Segment-aware trajectory replay accounting for Standard-native paths."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_native_stateful_v2 import NativeStatefulSegmentDispositionV2
from leo.contracts.trajectory_accounting import (
    ReplayTransitionCountsV1,
    TrajectoryAccountingConfigV2,
    TrajectoryConditionedReplayAccountingV2,
)


def _sum_transitions(
    values: tuple[ReplayTransitionCountsV1, ...],
) -> ReplayTransitionCountsV1:
    return ReplayTransitionCountsV1(
        positive_to_positive=sum(item.positive_to_positive for item in values),
        positive_to_negative=sum(item.positive_to_negative for item in values),
        negative_to_positive=sum(item.negative_to_positive for item in values),
        negative_to_negative=sum(item.negative_to_negative for item in values),
    )


class StandardNativeTrajectoryAccountingSegmentV3(ContractModel):
    """One reset-local accounting result and its authoritative global support."""

    schema_version: Literal[3] = 3
    continuity_segment_index: Annotated[int, Field(ge=0)]
    global_device_sample_start: Annotated[int, Field(ge=0)]
    global_device_sample_stop: Annotated[int, Field(ge=0)]
    stateful_segment_digest: Sha256Digest
    stateful_disposition: NativeStatefulSegmentDispositionV2
    local_science_digest: Sha256Digest | None
    trajectory_feedback_digest: Sha256Digest | None
    accounting: TrajectoryConditionedReplayAccountingV2 | None
    segment_digest: Sha256Digest

    @model_validator(mode="after")
    def _segment_is_closed(self) -> Self:
        if self.global_device_sample_stop < self.global_device_sample_start:
            raise ValueError("native accounting segment support regressed")
        analyzed = self.stateful_disposition is NativeStatefulSegmentDispositionV2.ANALYZED
        optional = (
            self.local_science_digest,
            self.trajectory_feedback_digest,
            self.accounting,
        )
        if analyzed != all(item is not None for item in optional):
            raise ValueError("native accounting segment disagrees with stateful science")
        if not analyzed and any(item is not None for item in optional):
            raise ValueError("unavailable native accounting segment carries derived science")
        if self.segment_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"segment_digest"})
        ):
            raise ValueError("native accounting segment digest does not match content")
        return self


class StandardNativeTrajectoryConditionedAccountingV3(ContractModel):
    """Digest-bound per-segment replay accounting without cross-gap association."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-trajectory-accounting-v3"] = (
        "standard-native-trajectory-accounting-v3"
    )
    source: StandardNativeSourceV1
    stateful_path_digest: Sha256Digest
    science_configuration_digest: Sha256Digest
    configuration: TrajectoryAccountingConfigV2
    segments: tuple[StandardNativeTrajectoryAccountingSegmentV3, ...]
    accounted_segment_count: Annotated[int, Field(ge=0)]
    evaluation_count: Annotated[int, Field(ge=0)]
    associated_evaluation_count: Annotated[int, Field(ge=0)]
    unassociated_evaluation_count: Annotated[int, Field(ge=0)]
    reacquired_associated_transitions: ReplayTransitionCountsV1
    conditioned_associated_transitions: ReplayTransitionCountsV1
    reacquired_unique_probe_transitions: ReplayTransitionCountsV1
    conditioned_unique_probe_transitions: ReplayTransitionCountsV1
    content_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    cross_segment_association_permitted: Literal[False] = False

    @model_validator(mode="after")
    def _accounting_is_closed(self) -> Self:
        if len(self.segments) != len(self.source.continuity_segments):
            raise ValueError("native accounting omitted an authoritative segment")
        for persisted, authoritative in zip(
            self.segments,
            self.source.continuity_segments,
            strict=True,
        ):
            if (
                persisted.continuity_segment_index != authoritative.segment_index
                or persisted.global_device_sample_start != authoritative.device_sample_start
                or persisted.global_device_sample_stop != authoritative.device_sample_stop
            ):
                raise ValueError("native accounting changed authoritative segment support")
            if (
                persisted.accounting is not None
                and persisted.accounting.configuration != self.configuration
            ):
                raise ValueError("native accounting segment changed reviewed policy")
        accounted = tuple(item.accounting for item in self.segments if item.accounting is not None)
        if self.accounted_segment_count != len(accounted):
            raise ValueError("native accounting segment count does not close")
        if self.evaluation_count != sum(item.evaluation_count for item in accounted):
            raise ValueError("native accounting evaluation count does not close")
        if self.associated_evaluation_count != sum(
            item.associated_evaluation_count for item in accounted
        ) or self.unassociated_evaluation_count != sum(
            item.unassociated_evaluation_count for item in accounted
        ):
            raise ValueError("native accounting association counts do not close")
        transition_fields = (
            "reacquired_associated_transitions",
            "conditioned_associated_transitions",
            "reacquired_unique_probe_transitions",
            "conditioned_unique_probe_transitions",
        )
        for field in transition_fields:
            expected = _sum_transitions(tuple(getattr(item, field) for item in accounted))
            if getattr(self, field) != expected:
                raise ValueError(f"native accounting {field} does not close")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("native accounting content digest does not match")
        return self
