"""Application-owned adaptive capture contracts, independent of PPU and IIO.

These are new kinds, not revisions of the existing fixed-order capture kinds.
Wire protocol V2 and application schema V1 are explicitly distinct identities.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self, get_args, get_origin

from pydantic import ConfigDict, Field, model_validator

from leo.contracts.base import ContractModel
from leo.scanner.models import ScanTarget
from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopRestorationReceiptV1,
    PersistentHopTargetCoverageV1,
    persistent_hop_wire_session_id,
)

Counter = Annotated[int, Field(strict=True, ge=0, lt=1 << 64)]
PositiveCounter = Annotated[int, Field(strict=True, gt=0, lt=1 << 64)]
Index = Annotated[int, Field(strict=True, ge=0, lt=2500)]
Count = Annotated[int, Field(strict=True, ge=0, le=2500)]
TargetIndex = Annotated[int, Field(strict=True, ge=0, le=7)]
SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
AdaptiveMode = Literal["shadow", "adaptive"]
ChoiceReason = Literal["warmup", "weighted", "exploration", "none_active", "fault_fallback"]


class AdaptiveModel(ContractModel):
    model_config = ConfigDict(revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def _literal_integers_are_exact(cls, value: Any) -> Any:
        # Pydantic Literal[1] otherwise accepts True and 1.0. Do not coerce
        # protocol versions, flags or the pinned numeric policy at this boundary.
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                choices = get_args(field.annotation)
                if (
                    name in value
                    and get_origin(field.annotation) is Literal
                    and choices
                    and all(type(item) is int for item in choices)
                    and type(value[name]) is not int
                ):
                    raise ValueError(f"adaptive {name} must be an exact integer")
        return value


class AdaptiveHopPolicyV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    policy_id: Literal["three-miss-two-second-v1"] = "three-miss-two-second-v1"
    mode: AdaptiveMode
    generation: PositiveCounter
    warmup_visits: Literal[3] = 3
    missed_dwells: Literal[3] = 3
    cooldown_ms: Literal[2000] = 2000
    active_weight: Literal[3] = 3
    quiet_weight: Literal[1] = 1
    maximum_revisit_ms: Literal[3000] = 3000
    hop_budget_ms: Literal[160] = 160
    maximum_result_age_ms: Literal[1000] = 1000
    unhealthy_limit: Literal[3] = 3


class AdaptiveHopPlanV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_adaptive_hop_plan"] = "starlink_adaptive_hop_plan"
    geometry: PersistentHopPlanV1
    policy: AdaptiveHopPolicyV1
    classification_receiver: Literal[1] = 1

    @model_validator(mode="after")
    def _geometry_is_revalidated(self) -> Self:
        # The published geometry contract remains unchanged, including its
        # band/IF coverage, 300 s / 120 ms and two recorded receiver rules.
        PersistentHopPlanV1.model_validate(self.geometry.model_dump())
        return self


class AdaptiveHopDecisionV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    mode: AdaptiveMode
    generation: PositiveCounter
    decision_counter: Counter
    basis_visit: Index | None
    proposed_target: TargetIndex
    reason: ChoiceReason
    active_mask: Annotated[int, Field(strict=True, ge=0, le=255)]
    quiet_mask: Annotated[int, Field(strict=True, ge=0, le=255)]
    consecutive_misses: Annotated[int, Field(strict=True, ge=0, le=3)]
    cooldown_remaining_samples: Counter

    @model_validator(mode="after")
    def _states_do_not_overlap(self) -> Self:
        if self.active_mask & self.quiet_mask:
            raise ValueError("adaptive active and quiet masks overlap")
        return self


class AdaptiveHopEventV1(AdaptiveModel):
    """Every actual transition, including an unfinished last visit on cancel."""

    schema_version: Literal[1] = 1
    visit_index: Index
    event_sequence: Index
    device_event_id: PositiveCounter
    device_event_flags: Literal[3] = 3
    target_index: TargetIndex
    from_profile_index: TargetIndex | None
    fastlock_slot: TargetIndex
    target: ScanTarget
    actual_lo_frequency_hz: PositiveCounter
    actual_if_offset_hz: Annotated[int, Field(strict=True, ge=-10, le=10)]
    invalid_start_counter: Counter
    transition_before_counter: Counter
    transition_after_counter: Counter
    valid_start_counter: PositiveCounter
    decision: AdaptiveHopDecisionV1

    @model_validator(mode="after")
    def _event_is_source_attested(self) -> Self:
        ScanTarget.model_validate(self.target.model_dump())
        if (
            self.event_sequence != self.visit_index
            or self.fastlock_slot != self.target_index
            or (self.from_profile_index is None) != (self.visit_index == 0)
            or self.actual_lo_frequency_hz + self.actual_if_offset_hz != self.target.if_center_hz
            or not self.invalid_start_counter
            <= self.transition_before_counter
            <= self.transition_after_counter
            < self.valid_start_counter
            or self.decision.decision_counter > self.transition_before_counter
            or (self.visit_index and self.decision.decision_counter < self.invalid_start_counter)
            or (
                self.decision.basis_visit is not None
                and self.decision.basis_visit >= self.visit_index
            )
            or (
                self.decision.mode == "adaptive"
                and self.decision.proposed_target != self.target_index
            )
            or (self.decision.mode == "shadow" and self.target_index != self.visit_index % 8)
        ):
            raise ValueError("adaptive event, actual tuning or decision binding is inconsistent")
        return self


class AdaptiveHopVisitV1(AdaptiveModel):
    """Only complete valid IQ, without an invented sweep coordinate."""

    schema_version: Literal[1] = 1
    event: AdaptiveHopEventV1
    valid_end_counter_exclusive: PositiveCounter

    @model_validator(mode="after")
    def _interval_increases(self) -> Self:
        if self.valid_end_counter_exclusive <= self.event.valid_start_counter:
            raise ValueError("adaptive valid visit does not increase")
        return self

    @property
    def valid_sample_count(self) -> int:
        return self.valid_end_counter_exclusive - self.event.valid_start_counter


class AdaptiveHopTerminalV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    wire_protocol_version: Literal[2] = 2
    wire_feature_flags: Literal[63] = 63
    state: Literal["completed", "cancelled"]
    reason: Literal["complete", "client_close", "disconnect"]
    flags: Literal[57] = 57
    error_code: Literal[0] = 0
    session_id: PositiveCounter
    planned_dwells: Literal[2500] = 2500
    visits_started: Count
    events_emitted: Count
    next_event_sequence: Count
    last_block_sequence: Counter
    last_block_end_counter: Counter
    first_counter: Counter
    final_counter: Counter
    restore_before_counter: Counter
    restore_after_counter: Counter
    restored_lo_frequency_hz: PositiveCounter
    restore_error_code: Literal[0] = 0
    active_profile_index: TargetIndex | None
    restored_profile_index: TargetIndex | None
    startup_invalid_start_counter: Counter
    startup_invalid_end_counter_exclusive: Counter
    device_dropped_events: Literal[0] = 0

    @model_validator(mode="after")
    def _terminal_is_closed(self) -> Self:
        if (
            (self.state == "completed") != (self.reason == "complete")
            or self.visits_started != self.events_emitted
            or self.next_event_sequence != self.events_emitted
            or self.final_counter < self.first_counter
            or self.startup_invalid_end_counter_exclusive < self.startup_invalid_start_counter
            or self.restore_before_counter < max(self.final_counter, self.last_block_end_counter)
            or self.restore_after_counter < self.restore_before_counter
            or (self.state == "completed" and self.final_counter > self.last_block_end_counter)
            or (self.state == "cancelled" and self.final_counter < self.last_block_end_counter)
        ):
            raise ValueError("adaptive terminal counters or lifecycle are inconsistent")
        return self


class AdaptiveHopReceiptV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_adaptive_hop_session"] = "starlink_adaptive_hop_session"
    session_id: SessionId
    radio_id: Annotated[str, Field(min_length=1, max_length=128)]
    radio_serial: Annotated[str, Field(min_length=1, max_length=128)]
    radio_uri: Annotated[str, Field(min_length=1, max_length=512)]
    plan: AdaptiveHopPlanV1
    metadata_abi_version: Literal[3] = 3
    stream_generation: PositiveCounter | None
    source_span_attested: Annotated[bool, Field(strict=True)]
    kernel_buffers_requested: Annotated[int, Field(strict=True, ge=2, le=64)]
    kernel_buffers_readback: Annotated[int, Field(strict=True, ge=2, le=64)]
    terminal: AdaptiveHopTerminalV1
    events: Annotated[tuple[AdaptiveHopEventV1, ...], Field(max_length=2500)]
    complete_visit_count: Count
    valid_sample_count: Counter
    transition_invalid_sample_count: Counter
    unclassified_sample_count: Counter
    unreceived_tail_sample_count: Counter
    duty_denominator_sample_count: Counter
    valid_duty_ppm: Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
    duty_target_met: Annotated[bool, Field(strict=True)]
    restoration: PersistentHopRestorationReceiptV1

    @model_validator(mode="after")
    def _receipt_reproduces_source_accounting(self) -> Self:
        g, p, terminal = self.plan.geometry, self.plan.policy, self.terminal
        PersistentHopRestorationReceiptV1.model_validate(self.restoration.model_dump())
        if (
            terminal.session_id != persistent_hop_wire_session_id(self.session_id)
            or terminal.visits_started != len(self.events)
            or self.kernel_buffers_requested != g.kernel_buffers
            or self.kernel_buffers_readback != g.kernel_buffers
            or self.restoration.status != "restored"
            or self.complete_visit_count
            != max(0, len(self.events) - (terminal.state == "cancelled"))
            or (self.events and self.stream_generation is None)
            or self.source_span_attested != bool(self.events)
        ):
            raise ValueError("adaptive receipt identity, visit inventory or restoration mismatch")
        previous: AdaptiveHopEventV1 | None = None
        for i, event in enumerate(self.events):
            d = event.decision
            if (
                event.visit_index != i
                or event.target != g.profiles[event.target_index].target
                or event.from_profile_index != (previous.target_index if previous else None)
                or event.valid_start_counter
                != event.transition_after_counter + g.transition_guard_samples
                or event.valid_start_counter + g.valid_visit_samples >= 1 << 64
                or d.generation != p.generation
                or d.mode != p.mode
                or d.cooldown_remaining_samples > g.sample_rate_hz * p.cooldown_ms // 1000
                or event.transition_after_counter > terminal.final_counter
            ):
                raise ValueError("adaptive receipt event differs from its actual plan")
            if previous is not None and (
                event.invalid_start_counter != previous.valid_start_counter + g.valid_visit_samples
                or event.device_event_id <= previous.device_event_id
                or event.invalid_start_counter - terminal.first_counter
                >= g.nominal_device_sample_count
                or (
                    previous.decision.basis_visit is not None
                    and (d.basis_visit is None or d.basis_visit < previous.decision.basis_visit)
                )
            ):
                raise ValueError(
                    "adaptive receipt event/counter/decision sequence is not contiguous"
                )
            if d.basis_visit is not None and (
                self.events[d.basis_visit].valid_start_counter + g.valid_visit_samples
                > d.decision_counter
            ):
                raise ValueError("adaptive decision uses an unfinished source dwell")
            previous = event
        if self.events and (
            terminal.first_counter != self.events[0].invalid_start_counter
            or terminal.startup_invalid_start_counter != terminal.first_counter
            or terminal.startup_invalid_end_counter_exclusive != self.events[0].valid_start_counter
        ):
            raise ValueError("adaptive terminal startup does not match actual events")
        if not self.events and (
            terminal.startup_invalid_start_counter or terminal.startup_invalid_end_counter_exclusive
        ):
            raise ValueError("adaptive empty receipt has an invented startup event")
        valid = self.complete_visit_count * g.valid_visit_samples
        invalid = sum(
            max(
                0,
                min(terminal.final_counter, e.valid_start_counter)
                - max(terminal.first_counter, e.invalid_start_counter),
            )
            for e in self.events
        )
        denominator = (
            terminal.final_counter - terminal.first_counter if self.source_span_attested else 0
        )
        if (
            self.complete_visit_count
            and self.events[self.complete_visit_count - 1].valid_start_counter
            + g.valid_visit_samples
            > terminal.last_block_end_counter
        ):
            raise ValueError("adaptive receipt claims valid IQ beyond delivered counters")
        if terminal.state == "completed":
            if (
                not self.events
                or terminal.final_counter
                != self.events[-1].valid_start_counter + g.valid_visit_samples
            ):
                raise ValueError("adaptive completed receipt lacks its final full dwell")
            overshoot = (
                g.valid_visit_samples
                + self.events[-1].valid_start_counter
                - self.events[-1].invalid_start_counter
            )
            if (
                not g.nominal_device_sample_count
                <= denominator
                <= g.nominal_device_sample_count + overshoot
            ):
                raise ValueError("adaptive complete capture is outside its 300-second envelope")
            if terminal.last_block_end_counter - terminal.final_counter > g.samples_per_block:
                raise ValueError("adaptive terminal retained more than one boundary refill")
        unclassified = denominator - valid - invalid
        duty = valid * 1_000_000 // denominator if denominator else 0
        if (
            self.valid_sample_count != valid
            or self.transition_invalid_sample_count != invalid
            or self.duty_denominator_sample_count != denominator
            or self.unclassified_sample_count != unclassified
            or (terminal.state == "completed" and unclassified)
            or self.unreceived_tail_sample_count
            != max(
                0,
                terminal.final_counter
                - (terminal.last_block_end_counter or terminal.first_counter),
            )
            * self.source_span_attested
            or self.valid_duty_ppm != duty
            or self.duty_target_met != (duty >= g.minimum_valid_duty_ppm)
        ):
            raise ValueError("adaptive receipt time, duty or partial-tail accounting differs")
        return self

    @property
    def visits(self) -> tuple[AdaptiveHopVisitV1, ...]:
        return tuple(
            AdaptiveHopVisitV1(
                event=e,
                valid_end_counter_exclusive=(
                    e.valid_start_counter + self.plan.geometry.valid_visit_samples
                ),
            )
            for e in self.events[: self.complete_visit_count]
        )

    @property
    def target_coverage(self) -> tuple[PersistentHopTargetCoverageV1, ...]:
        return tuple(
            PersistentHopTargetCoverageV1(
                target_index=p.target_index,
                target=p.target,
                visit_count=sum(
                    e.target_index == p.target_index
                    for e in self.events[: self.complete_visit_count]
                ),
                valid_sample_count=sum(
                    e.target_index == p.target_index
                    for e in self.events[: self.complete_visit_count]
                )
                * self.plan.geometry.valid_visit_samples,
            )
            for p in self.plan.geometry.profiles
        )
