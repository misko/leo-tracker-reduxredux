"""Native-10M single-RX adaptive contracts with separately attested host evidence.

Application major 2 uses provider wire major 3. The published dual-RX
application major 1 remains closed to this geometry and feedback producer.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.scanner.adaptive_hop import (
    AdaptiveHopPlanV1,
    AdaptiveHopReceiptV1,
    AdaptiveHopTerminalV1,
    AdaptiveModel,
    Counter,
    Index,
    PositiveCounter,
    TargetIndex,
)
from leo.scanner.single_rx import SingleRxPersistentHopPlanV2

HOST_ADAPTIVE_PROFILE_ID = "adaptive-single-rx-random-10m-300s-v1"
Finite = Annotated[float, Field(allow_inf_nan=False)]
Duration = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Outcome = Literal["unknown", "detected", "not_detected"]


class HostDecisionConfigurationV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    execution: Literal["host"] = "host"
    detector_id: Literal["six-screen-one-blind-confirm-v1"] = "six-screen-one-blind-confirm-v1"
    # The release manifest binds the native library, templates, filter and sources.
    detector_manifest_sha256: Sha256Digest
    source_rate_hz: Literal[10_000_000] = 10_000_000
    decision_rate_hz: Literal[2_500_000] = 2_500_000
    decimation_factor: Literal[4] = 4
    decimation_phase: Literal[0] = 0
    filter_taps: Literal[161] = 161
    filter_arithmetic: Literal["q15"] = "q15"
    reset: Literal["each-visit"] = "each-visit"
    group_delay_source_samples: Literal[80] = 80
    supported_start: Literal[40] = 40
    supported_end: Literal[300_000] = 300_000
    screen_count: Literal[6] = 6
    screen_samples: Literal[50_000] = 50_000
    maximum_confirmations: Literal[1] = 1

    @model_validator(mode="after")
    def _artifact_is_identified(self) -> Self:
        if self.detector_manifest_sha256 == "sha256:" + "0" * 64:
            raise ValueError("host decision requires a nonzero release manifest digest")
        return self

    @property
    def configuration_sha256(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class HostAdaptiveHopPlanV2(AdaptiveHopPlanV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    geometry: SingleRxPersistentHopPlanV2
    classification_receiver: Literal[0, 1]  # type: ignore[assignment]
    decision: HostDecisionConfigurationV1
    qualification_minimum_valid_duty_ppm: Literal[950_000] = 950_000

    @field_validator("classification_receiver", mode="before")
    @classmethod
    def _receiver_is_exact(cls, value):
        if type(value) is not int:
            raise ValueError("host classification receiver must be an exact integer")
        return value

    @model_validator(mode="after")
    def _geometry_is_revalidated(self) -> Self:
        SingleRxPersistentHopPlanV2.model_validate(self.geometry.model_dump())
        if self.geometry.receiver_ids != (self.classification_receiver,):
            raise ValueError("host classification receiver differs from the recorded receiver")
        return self


class HostDecisionNumericsV1(AdaptiveModel):
    """Frozen detector output; candidate scalars describe its first candidate.

    Outcome summarizes all candidates in the one blind confirmation. A later
    candidate can be positive, so first-candidate scalars do not define outcome.
    """

    schema_version: Literal[1] = 1
    outcome: Outcome
    screen_mask: Literal[63] = 63
    confirmation_mask: Literal[1, 2, 4, 8, 16, 32]
    supported_start: Literal[40] = 40
    supported_end: Literal[300_000] = 300_000
    candidate_supported: Annotated[bool, Field(strict=True)]
    epoch: Annotated[int, Field(strict=True, ge=0, lt=3333)]
    fractional_complete: Annotated[bool, Field(strict=True)]
    fractional_offset: Finite
    cfo_hz: Finite
    exact_score: Finite
    margin: Finite
    filter_cpu_ms: Duration
    cpu_ms: Duration
    wall_ms: Duration
    screen_scores: Annotated[tuple[Finite, ...], Field(min_length=6, max_length=6)]

    @property
    def first_candidate_source_epoch_offset(self) -> float | None:
        if not self.candidate_supported or not self.fractional_complete:
            return None
        window = self.confirmation_mask.bit_length() - 1
        return 4 * (window * 50_000 + self.epoch + self.fractional_offset) - 80


class HostDecisionRecordV1(AdaptiveModel):
    """One emitted visit's computation and transport, never a policy-apply claim."""

    schema_version: Literal[1] = 1
    session_id: PositiveCounter
    generation: PositiveCounter
    stream_generation: PositiveCounter
    visit_index: Index
    event_sequence: Index
    receiver_id: Literal[0, 1]
    target_index: TargetIndex
    valid_start_counter: PositiveCounter
    valid_end_counter_exclusive: PositiveCounter
    configuration_sha256: Sha256Digest
    submitted_monotonic_ns: Counter
    started_monotonic_ns: Counter | None
    completed_monotonic_ns: Counter | None
    feedback_monotonic_ns: Counter
    feedback_completed_monotonic_ns: Counter
    numerics: HostDecisionNumericsV1 | None
    health: Literal["healthy", "queue_overflow", "detector_failure", "expired"]
    failure: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    feedback_outcome: Outcome
    feedback_disposition: Literal["accepted", "source_ended", "rejected", "not_submitted"]
    feedback_error: Annotated[str, Field(min_length=1, max_length=2048)] | None = None

    @model_validator(mode="after")
    def _evidence_is_consistent(self) -> Self:
        if (
            self.event_sequence != self.visit_index
            or self.valid_end_counter_exclusive - self.valid_start_counter != 1_200_000
            or self.feedback_monotonic_ns < self.submitted_monotonic_ns
            or self.feedback_completed_monotonic_ns < self.feedback_monotonic_ns
            or (self.started_monotonic_ns is None) != (self.completed_monotonic_ns is None)
        ):
            raise ValueError("host decision source or clock interval is inconsistent")
        if self.started_monotonic_ns is not None:
            assert self.completed_monotonic_ns is not None
            if (
                not self.submitted_monotonic_ns
                <= self.started_monotonic_ns
                <= (self.completed_monotonic_ns)
                <= self.feedback_monotonic_ns
            ):
                raise ValueError("host computation clocks are not ordered")
        elif self.health != "queue_overflow":
            raise ValueError("host computation requires its worker clock interval")
        if self.health == "healthy":
            if (
                self.numerics is None
                or self.failure is not None
                or self.feedback_outcome != self.numerics.outcome
                or self.feedback_monotonic_ns - self.submitted_monotonic_ns > 1_000_000_000
            ):
                raise ValueError("healthy host decision lacks fresh complete evidence")
        elif self.feedback_outcome != "unknown" or self.failure is None:
            raise ValueError("degraded host decision must retain an explicit unknown and reason")
        if self.health in ("queue_overflow", "detector_failure") and self.numerics is not None:
            raise ValueError("failed host computation cannot invent numerical evidence")
        if self.health == "queue_overflow" and self.started_monotonic_ns is not None:
            raise ValueError("overflowed host work cannot claim worker execution")
        if (self.feedback_disposition in ("rejected", "not_submitted")) != (
            self.feedback_error is not None
        ):
            raise ValueError("host feedback rejection must retain its transport error")
        return self

    @property
    def feedback_call_elapsed_ns(self) -> int | None:
        if self.feedback_disposition == "not_submitted":
            return None
        return self.feedback_completed_monotonic_ns - self.feedback_monotonic_ns


class HostAdaptiveHopTerminalV2(AdaptiveHopTerminalV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    wire_protocol_version: Literal[3] = 3  # type: ignore[assignment]
    wire_feature_flags: Literal[127] = 127  # type: ignore[assignment]


class HostAdaptiveHopReceiptV2(AdaptiveHopReceiptV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    plan: HostAdaptiveHopPlanV2
    terminal: HostAdaptiveHopTerminalV2
    host_decisions: Annotated[tuple[HostDecisionRecordV1, ...], Field(max_length=2500)]

    @property
    def qualification_duty_floor_met(self) -> bool:
        # Published geometry retains its 90% transport-accounting target.
        # Adaptive deployment has a separately pinned, stricter acceptance gate.
        return self.valid_duty_ppm >= self.plan.qualification_minimum_valid_duty_ppm

    @model_validator(mode="after")
    def _host_evidence_is_source_bound(self) -> Self:
        if len(self.host_decisions) != self.complete_visit_count:
            raise ValueError("host decisions must account for every complete native visit")
        for index, record in enumerate(self.host_decisions):
            event = self.events[index]
            if (
                record.session_id != self.terminal.session_id
                or record.generation != self.plan.policy.generation
                or record.stream_generation != self.stream_generation
                or record.visit_index != index
                or record.receiver_id != self.plan.classification_receiver
                or record.target_index != event.target_index
                or record.valid_start_counter != event.valid_start_counter
                or record.valid_end_counter_exclusive != event.valid_start_counter + 1_200_000
                or record.configuration_sha256 != self.plan.decision.configuration_sha256
            ):
                raise ValueError("host decision differs from its native source or configuration")
        return self
