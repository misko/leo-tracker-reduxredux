"""Additive contracts for one counter-authoritative persistent hopping session."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.radio import RadioSettingsV1
from leo.contracts.states import GainMode
from leo.scanner.models import ScannerModel, ScanTarget, scheduled_low_band_targets
from leo.scanner.schedule import ScheduledScannerRunIntentV1

PERSISTENT_HOP_NOMINAL_DURATION_SECONDS = 300
PERSISTENT_HOP_VALID_VISIT_MS = 120
PERSISTENT_HOP_RATE_HZ = (2_500_000, 5_000_000)
PERSISTENT_HOP_MINIMUM_VALID_DUTY_PPM = 900_000
PERSISTENT_HOP_LNB_LO_HZ = 9_750_000_000
PersistentHopCaptureOutcome = Literal["complete", "cancelled", "failed"]
PersistentHopTerminalReason = Literal[
    "complete",
    "client_close",
    "disconnect",
    "device",
    "event_overflow",
    "event_sequence",
    "counter_discontinuity",
    "protocol",
    "restore_error",
]


class PersistentHopProfileV1(ScannerModel):
    """One immutable Fast Lock profile assignment in scanner visit order."""

    schema_version: Literal[1] = 1
    target_index: Annotated[int, Field(ge=0, le=7)]
    fastlock_profile_index: Annotated[int, Field(ge=0, le=7)]
    target: ScanTarget


class PersistentHopPlanV1(ScannerModel):
    """Fixed geometry for one 300-second, single-rate hopping session."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_persistent_hop_plan"] = "starlink_persistent_hop_plan"
    nominal_duration_seconds: Literal[300] = 300
    valid_visit_ms: Literal[120] = 120
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    bandwidth_hz: Literal[2_500_000, 5_000_000]
    lnb_lo_hz: Literal[9_750_000_000] = 9_750_000_000
    receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    gain_mode: Literal[GainMode.MANUAL] = GainMode.MANUAL
    gain_db: float = 40.0
    samples_per_block: Annotated[int, Field(ge=4_096, le=1_048_576)] = 131_072
    kernel_buffers: Annotated[int, Field(ge=2, le=64)] = 8
    transition_guard_samples: Annotated[int, Field(gt=0)]
    maximum_visit_count: Literal[2_500] = 2_500
    minimum_valid_duty_ppm: Literal[900_000] = 900_000
    profiles: Annotated[tuple[PersistentHopProfileV1, ...], Field(min_length=8, max_length=8)]

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if self.bandwidth_hz != self.sample_rate_hz:
            raise ValueError("persistent-hop bandwidth must equal sample rate")
        if not math.isfinite(self.gain_db):
            raise ValueError("persistent-hop gain must be finite")
        if self.transition_guard_samples >= self.valid_visit_samples:
            raise ValueError("persistent-hop transition guard must be shorter than a visit")
        if self.planned_valid_duty_ppm < self.minimum_valid_duty_ppm:
            raise ValueError("persistent-hop transition guard cannot meet minimum valid duty")
        targets = scheduled_low_band_targets(
            bandwidth_hz=self.bandwidth_hz,
            lnb_lo_hz=self.lnb_lo_hz,
        )
        expected = tuple(
            PersistentHopProfileV1(
                target_index=index,
                fastlock_profile_index=index,
                target=target,
            )
            for index, target in enumerate(targets)
        )
        if self.profiles != expected:
            raise ValueError(
                "persistent-hop profiles must map 0..7 exactly to "
                "CH1L CH2L CH3L CH4L CH1U CH2U CH3U CH4U"
            )
        return self

    @property
    def valid_visit_samples(self) -> int:
        return self.sample_rate_hz * self.valid_visit_ms // 1_000

    @property
    def nominal_device_sample_count(self) -> int:
        return self.sample_rate_hz * self.nominal_duration_seconds

    @property
    def planned_valid_duty_ppm(self) -> int:
        return (
            self.valid_visit_samples
            * 1_000_000
            // (self.valid_visit_samples + self.transition_guard_samples)
        )


def compile_persistent_hop_plan_v1(
    *,
    sample_rate_hz: Literal[2_500_000, 5_000_000],
    kernel_buffers: int = 8,
    transition_guard_us: int = 11_000,
    gain_db: float = 40.0,
    samples_per_block: int = 131_072,
) -> PersistentHopPlanV1:
    """Build the only admitted profile order for one supported native rate."""

    if transition_guard_us <= 0:
        raise ValueError("persistent-hop transition guard must be positive")
    guard_numerator = sample_rate_hz * transition_guard_us
    if guard_numerator % 1_000_000:
        raise ValueError("persistent-hop transition guard must be sample-exact")
    targets = scheduled_low_band_targets(
        bandwidth_hz=sample_rate_hz,
        lnb_lo_hz=PERSISTENT_HOP_LNB_LO_HZ,
    )
    return PersistentHopPlanV1(
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        gain_db=gain_db,
        samples_per_block=samples_per_block,
        kernel_buffers=kernel_buffers,
        transition_guard_samples=guard_numerator // 1_000_000,
        profiles=tuple(
            PersistentHopProfileV1(
                target_index=index,
                fastlock_profile_index=index,
                target=target,
            )
            for index, target in enumerate(targets)
        ),
    )


def compile_scheduled_persistent_hop_plan_v1(
    intent: ScheduledScannerRunIntentV1,
    *,
    transition_guard_us: int = 11_000,
    kernel_buffers: int | None = None,
    samples_per_block: int = 131_072,
) -> PersistentHopPlanV1:
    """Project one existing 20-minute scanner slot onto truthful persistent geometry."""

    configuration = intent.configuration
    if intent.interval_seconds != 1_200:
        raise ValueError("persistent hopping requires the 20-minute scanner cadence")
    if intent.run_duration_seconds != PERSISTENT_HOP_NOMINAL_DURATION_SECONDS:
        raise ValueError("persistent hopping requires an exact 300-second capture")
    if configuration.dwell_ms != PERSISTENT_HOP_VALID_VISIT_MS:
        raise ValueError("persistent hopping requires exact 120 ms valid visits")
    if configuration.gain_mode is not GainMode.MANUAL:
        raise ValueError("persistent hopping requires an explicit manual gain")
    if configuration.sample_rate_hz not in PERSISTENT_HOP_RATE_HZ:
        raise ValueError("persistent hopping requires a native 2.5 or 5 MS/s slot")
    selected_buffers = configuration.kernel_buffers if kernel_buffers is None else kernel_buffers
    plan = compile_persistent_hop_plan_v1(
        sample_rate_hz=configuration.sample_rate_hz,  # type: ignore[arg-type]
        kernel_buffers=selected_buffers,
        transition_guard_us=transition_guard_us,
        gain_db=configuration.gain_db,
        samples_per_block=samples_per_block,
    )
    if tuple(profile.target for profile in plan.profiles) != configuration.targets:
        raise ValueError("persistent hopping targets disagree with the scheduled scanner slot")
    return plan


class PersistentHopTransitionInvalidSpanV1(ScannerModel):
    """Device-counter interval deliberately excluded around one profile transition."""

    schema_version: Literal[1] = 1
    kind: Literal["startup_prime", "retune_and_settle"]
    visit_index: Annotated[int, Field(ge=0)]
    from_profile_index: Annotated[int | None, Field(ge=0, le=7)] = None
    to_profile_index: Annotated[int, Field(ge=0, le=7)]
    transition_before_counter: Annotated[int, Field(ge=0)]
    transition_after_counter: Annotated[int, Field(ge=0)]
    device_sample_counter: Annotated[int, Field(ge=0)]
    device_sample_counter_end_exclusive: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _span_is_a_transition(self) -> Self:
        if self.device_sample_counter_end_exclusive <= self.device_sample_counter:
            raise ValueError("persistent-hop transition-invalid span must increase")
        if not (
            self.device_sample_counter
            <= self.transition_before_counter
            <= self.transition_after_counter
            <= self.device_sample_counter_end_exclusive
        ):
            raise ValueError("persistent-hop transition counters escape the invalid span")
        if self.visit_index == 0:
            if self.kind != "startup_prime" or self.from_profile_index is not None:
                raise ValueError("first persistent-hop visit requires an unowned startup prime")
        elif self.kind != "retune_and_settle" or self.from_profile_index is None:
            raise ValueError("later persistent-hop visits require a profile transition")
        return self

    @property
    def sample_count(self) -> int:
        return self.device_sample_counter_end_exclusive - self.device_sample_counter


class PersistentHopVisitV1(ScannerModel):
    """One complete valid dwell and the invalid transition that immediately precedes it."""

    schema_version: Literal[1] = 1
    visit_index: Annotated[int, Field(ge=0)]
    sweep_index: Annotated[int, Field(ge=0)]
    target_index: Annotated[int, Field(ge=0, le=7)]
    fastlock_profile_index: Annotated[int, Field(ge=0, le=7)]
    event_sequence: Annotated[int, Field(ge=0)]
    device_event_id: Annotated[int, Field(gt=0)]
    device_event_flags: Literal[3] = 3
    fastlock_slot: Annotated[int, Field(ge=0, le=7)]
    target: ScanTarget
    requested_if_center_hz: Annotated[int, Field(gt=0)]
    actual_lo_frequency_hz: Annotated[int, Field(gt=0)]
    actual_if_offset_hz: int
    transition_invalid_before: PersistentHopTransitionInvalidSpanV1
    valid_device_sample_counter: Annotated[int, Field(ge=0)]
    valid_device_sample_counter_end_exclusive: Annotated[int, Field(gt=0)]
    valid_sample_count: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _visit_is_closed(self) -> Self:
        transition = self.transition_invalid_before
        if transition.visit_index != self.visit_index:
            raise ValueError("persistent-hop transition visit index disagrees with visit")
        if transition.to_profile_index != self.fastlock_profile_index:
            raise ValueError("persistent-hop transition profile disagrees with visit")
        if self.fastlock_slot != self.fastlock_profile_index:
            raise ValueError("persistent-hop Fast Lock slot disagrees with visit profile")
        if transition.device_sample_counter_end_exclusive != self.valid_device_sample_counter:
            raise ValueError("persistent-hop transition must end at the first valid sample")
        if (
            self.valid_device_sample_counter_end_exclusive - self.valid_device_sample_counter
            != self.valid_sample_count
        ):
            raise ValueError("persistent-hop valid counter range disagrees with sample count")
        if self.requested_if_center_hz != self.target.if_center_hz:
            raise ValueError("persistent-hop requested IF disagrees with target")
        if abs(self.actual_if_offset_hz) > 10 or (
            self.actual_lo_frequency_hz + self.actual_if_offset_hz != self.requested_if_center_hz
        ):
            raise ValueError("persistent-hop actual LO and bounded IF offset disagree with request")
        return self


class PersistentHopContinuityFaultV1(ScannerModel):
    """Structured device-counter, overflow, or hop-event continuity failure."""

    schema_version: Literal[1] = 1
    fault_index: Annotated[int, Field(ge=0)]
    before_visit_index: Annotated[int, Field(ge=0)]
    kind: Literal["missing_samples", "rx_overflow", "hop_event_sequence_gap"]
    expected_device_sample_counter: Annotated[int | None, Field(ge=0)] = None
    actual_device_sample_counter: Annotated[int | None, Field(ge=0)] = None
    missing_sample_count: Annotated[int, Field(ge=0)] = 0
    overflow_observed: bool = False
    expected_hop_event_sequence: Annotated[int | None, Field(ge=0)] = None
    actual_hop_event_sequence: Annotated[int | None, Field(ge=0)] = None
    reason: Annotated[str, Field(min_length=1, max_length=2048)]

    @model_validator(mode="after")
    def _fault_fields_agree(self) -> Self:
        if self.kind == "missing_samples":
            if (
                self.expected_device_sample_counter is None
                or self.actual_device_sample_counter is None
                or self.actual_device_sample_counter <= self.expected_device_sample_counter
                or self.missing_sample_count
                != self.actual_device_sample_counter - self.expected_device_sample_counter
                or self.overflow_observed
                or self.expected_hop_event_sequence is not None
                or self.actual_hop_event_sequence is not None
            ):
                raise ValueError("persistent-hop missing-sample fault evidence is inconsistent")
        elif self.kind == "rx_overflow":
            if (
                self.expected_device_sample_counter is None
                or self.actual_device_sample_counter != self.expected_device_sample_counter
                or self.missing_sample_count
                or not self.overflow_observed
                or self.expected_hop_event_sequence is not None
                or self.actual_hop_event_sequence is not None
            ):
                raise ValueError("persistent-hop overflow fault evidence is inconsistent")
        elif (
            self.expected_hop_event_sequence is None
            or self.actual_hop_event_sequence is None
            or self.actual_hop_event_sequence <= self.expected_hop_event_sequence
            or self.expected_device_sample_counter is not None
            or self.actual_device_sample_counter is not None
            or self.missing_sample_count
            or self.overflow_observed
        ):
            raise ValueError("persistent-hop event-sequence fault evidence is inconsistent")
        return self


class PersistentHopTargetCoverageV1(ScannerModel):
    """Valid visit coverage for one target in a possibly partial final sweep."""

    schema_version: Literal[1] = 1
    target_index: Annotated[int, Field(ge=0, le=7)]
    target: ScanTarget
    visit_count: Annotated[int, Field(ge=0)]
    valid_sample_count: Annotated[int, Field(ge=0)]


class PersistentHopRestorationReceiptV1(ScannerModel):
    """Terminal proof that mutable radio state was restored or failed explicitly."""

    schema_version: Literal[1] = 1
    status: Literal["restored", "failed"]
    original_settings: RadioSettingsV1
    restored_settings: RadioSettingsV1 | None = None
    receive_buffer_closed: bool
    fastlock_inactive: bool
    error_type: Annotated[str | None, Field(min_length=1, max_length=256)] = None
    error_message: Annotated[str | None, Field(min_length=1, max_length=2048)] = None

    @model_validator(mode="after")
    def _restoration_is_closed(self) -> Self:
        errors_are_complete = (self.error_type is None) == (self.error_message is None)
        if not errors_are_complete:
            raise ValueError("persistent-hop restoration error evidence is partial")
        if self.status == "restored":
            if (
                self.restored_settings != self.original_settings
                or not self.receive_buffer_closed
                or not self.fastlock_inactive
                or self.error_type is not None
            ):
                raise ValueError("successful persistent-hop restoration is not exact")
        elif self.error_type is None:
            raise ValueError("failed persistent-hop restoration lacks structured error evidence")
        return self


class PersistentHopTerminalStatusV1(ScannerModel):
    """Lossless semantic projection of the server-attested HOPT v1 status."""

    schema_version: Literal[1] = 1
    state: Literal["completed", "cancelled", "failed"]
    reason: PersistentHopTerminalReason
    error_code: Annotated[int, Field(ge=-(1 << 31), lt=1 << 31)]
    flags: Annotated[int, Field(ge=0, le=63)]
    session_id: Annotated[int, Field(gt=0)]
    planned_dwells: Literal[2_500] = 2_500
    visits_started: Annotated[int, Field(ge=0, le=2_500)]
    events_emitted: Annotated[int, Field(ge=0, le=2_500)]
    next_event_sequence: Annotated[int, Field(ge=0, le=2_500)]
    last_block_sequence: Annotated[int, Field(ge=0)]
    last_block_end_counter: Annotated[int, Field(ge=0)]
    first_counter: Annotated[int, Field(ge=0)]
    final_counter: Annotated[int, Field(gt=0)]
    restore_before_counter: Annotated[int, Field(ge=0)]
    restore_after_counter: Annotated[int, Field(ge=0)]
    restored_lo_frequency_hz: Annotated[int, Field(gt=0)]
    restore_error_code: Annotated[int, Field(ge=-(1 << 31), lt=1 << 31)]
    active_profile_index: Annotated[int | None, Field(ge=0, le=7)] = None
    restored_profile_index: Annotated[int | None, Field(ge=0, le=7)] = None
    startup_invalid_start_counter: Annotated[int, Field(ge=0)]
    startup_invalid_end_counter_exclusive: Annotated[int, Field(gt=0)]
    device_dropped_events: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _status_is_terminal(self) -> Self:
        if not self.flags & 1:
            raise ValueError("persistent-hop server status lacks the terminal flag")
        if self.final_counter < self.first_counter:
            raise ValueError("persistent-hop terminal counter interval is reversed")
        if self.restore_after_counter < self.restore_before_counter:
            raise ValueError("persistent-hop restoration counter bracket is reversed")
        if self.startup_invalid_end_counter_exclusive < self.startup_invalid_start_counter:
            raise ValueError("persistent-hop startup invalid interval is reversed")
        if self.next_event_sequence < self.events_emitted:
            raise ValueError("persistent-hop terminal event sequence precedes emitted count")
        if self.state == "completed" and self.reason != "complete":
            raise ValueError("completed persistent-hop status lacks the complete reason")
        if self.reason == "complete" and self.state != "completed":
            raise ValueError("persistent-hop complete reason requires completed state")
        if self.state in {"completed", "cancelled"} and self.error_code:
            raise ValueError("successful or cancelled persistent-hop status has an error")
        if self.state == "failed" and self.error_code >= 0:
            raise ValueError("failed persistent-hop status requires a negative errno")
        if self.restore_error_code > 0:
            raise ValueError("persistent-hop restore errno cannot be positive")
        return self


class PersistentHopSessionReceiptV1(ScannerModel):
    """Terminal evidence and exact duty accounting for one persistent session."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_persistent_hop_session"] = "starlink_persistent_hop_session"
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    radio_id: Annotated[str, Field(min_length=1, max_length=128)]
    radio_serial: Annotated[str, Field(min_length=1, max_length=128)]
    radio_uri: Annotated[str, Field(min_length=1, max_length=512)]
    plan: PersistentHopPlanV1
    server_protocol_version: Literal[1] = 1
    server_feature_flags: Literal[31] = 31
    request_flags: Literal[3] = 3
    metadata_abi_version: Literal[3] = 3
    stream_generation: Annotated[str, Field(min_length=1, max_length=128)]
    kernel_buffers_requested: Annotated[int, Field(ge=2, le=64)]
    kernel_buffers_readback: Annotated[int, Field(ge=2, le=64)]
    capture_outcome: PersistentHopCaptureOutcome
    terminal_status: PersistentHopTerminalStatusV1
    terminal_status_attested: Literal[True] = True
    session_start_device_sample_counter: Annotated[int, Field(ge=0)]
    session_end_device_sample_counter_exclusive: Annotated[int, Field(ge=0)]
    visits: tuple[PersistentHopVisitV1, ...]
    continuity_faults: tuple[PersistentHopContinuityFaultV1, ...] = ()
    target_coverage: Annotated[
        tuple[PersistentHopTargetCoverageV1, ...], Field(min_length=8, max_length=8)
    ]
    valid_sample_count: Annotated[int, Field(ge=0)]
    transition_invalid_sample_count: Annotated[int, Field(ge=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    overflow_count: Annotated[int, Field(ge=0)]
    hop_event_sequence_gap_count: Annotated[int, Field(ge=0)]
    duty_denominator_sample_count: Annotated[int, Field(ge=0)]
    valid_duty_ppm: Annotated[int, Field(ge=0, le=1_000_000)]
    continuity_attested: bool
    duty_target_met: bool
    restoration: PersistentHopRestorationReceiptV1

    @model_validator(mode="after")
    def _session_is_closed(self) -> Self:
        plan = self.plan
        if self.kernel_buffers_requested != plan.kernel_buffers:
            raise ValueError("persistent-hop requested kernel buffers disagree with plan")
        if self.kernel_buffers_readback != self.kernel_buffers_requested:
            raise ValueError("persistent-hop kernel-buffer readback disagrees with request")
        expected_state = {
            "complete": "completed",
            "cancelled": "cancelled",
            "failed": "failed",
        }[self.capture_outcome]
        if self.terminal_status.state != expected_state:
            raise ValueError("persistent-hop terminal state disagrees with capture outcome")
        terminal_flags = self.terminal_status.flags
        restoration_attempted = bool(terminal_flags & 8)
        restoration_succeeded = bool(terminal_flags & 16)
        restoration_required = bool(terminal_flags & 32)
        if not restoration_required or not restoration_attempted:
            raise ValueError("persistent-hop terminal status lacks required restoration evidence")
        if restoration_succeeded != (self.restoration.status == "restored"):
            raise ValueError("persistent-hop terminal flags disagree with restoration receipt")
        if (
            self.session_end_device_sample_counter_exclusive
            < self.session_start_device_sample_counter
        ):
            raise ValueError("persistent-hop device-counter session interval is reversed")
        if self.capture_outcome == "complete" and not self.visits:
            raise ValueError("complete persistent-hop session has no visits")
        if len(self.visits) > plan.maximum_visit_count:
            raise ValueError("persistent-hop session exceeds its finite visit bound")
        if self.capture_outcome == "complete" and self.duty_denominator_sample_count < (
            plan.nominal_device_sample_count
        ):
            raise ValueError("complete persistent-hop session ended before its nominal duration")
        if self.capture_outcome == "complete" and len(self.visits) > 1:
            prior_end = self.visits[-2].valid_device_sample_counter_end_exclusive
            if prior_end - self.session_start_device_sample_counter >= (
                plan.nominal_device_sample_count
            ):
                raise ValueError(
                    "persistent-hop complete session retained visits after its deadline"
                )

        fault_indexes = tuple(item.fault_index for item in self.continuity_faults)
        if fault_indexes != tuple(range(len(self.continuity_faults))):
            raise ValueError("persistent-hop fault indexes must be contiguous from zero")
        if any(item.before_visit_index > len(self.visits) for item in self.continuity_faults):
            raise ValueError("persistent-hop fault references a visit outside the session")
        if any(
            item.kind == "rx_overflow" and item.before_visit_index == len(self.visits)
            for item in self.continuity_faults
        ):
            raise ValueError("persistent-hop terminal overflow fault lacks an observed visit")

        missing_by_visit: dict[int, list[PersistentHopContinuityFaultV1]] = defaultdict(list)
        event_by_visit: dict[int, list[PersistentHopContinuityFaultV1]] = defaultdict(list)
        for fault in self.continuity_faults:
            if fault.kind == "missing_samples":
                missing_by_visit[fault.before_visit_index].append(fault)
            elif fault.kind == "hop_event_sequence_gap":
                event_by_visit[fault.before_visit_index].append(fault)

        expected_counter = self.session_start_device_sample_counter
        expected_event_id = 0
        previous_device_event_id: int | None = None
        valid_samples = 0
        transition_samples = 0
        visit_counts = [0] * len(plan.profiles)
        target_samples = [0] * len(plan.profiles)
        for index, visit in enumerate(self.visits):
            profile = plan.profiles[index % len(plan.profiles)]
            if (
                visit.visit_index != index
                or visit.sweep_index != index // len(plan.profiles)
                or visit.target_index != profile.target_index
                or visit.fastlock_profile_index != profile.fastlock_profile_index
                or visit.target != profile.target
                or visit.valid_sample_count != plan.valid_visit_samples
            ):
                raise ValueError(
                    "persistent-hop visits must follow the exact repeated profile plan"
                )
            transition = visit.transition_invalid_before
            if (
                previous_device_event_id is not None
                and visit.device_event_id <= previous_device_event_id
            ):
                raise ValueError("persistent-hop device event IDs must strictly increase")
            previous_device_event_id = visit.device_event_id
            expected_from = None if index == 0 else self.visits[index - 1].fastlock_profile_index
            if transition.from_profile_index != expected_from:
                raise ValueError("persistent-hop transition source profile is not the prior visit")

            actual_counter = transition.device_sample_counter
            missing_faults = missing_by_visit.get(index, [])
            if actual_counter == expected_counter:
                if missing_faults:
                    raise ValueError(
                        "persistent-hop session declares a missing fault without a gap"
                    )
            else:
                if actual_counter < expected_counter or len(missing_faults) != 1:
                    raise ValueError("persistent-hop counter gap lacks exact fault evidence")
                fault = missing_faults[0]
                if (
                    fault.expected_device_sample_counter != expected_counter
                    or fault.actual_device_sample_counter != actual_counter
                ):
                    raise ValueError("persistent-hop counter gap disagrees with its fault")

            event_faults = event_by_visit.get(index, [])
            if visit.event_sequence == expected_event_id:
                if event_faults:
                    raise ValueError("persistent-hop session declares an event fault without a gap")
            else:
                if visit.event_sequence < expected_event_id or len(event_faults) != 1:
                    raise ValueError("persistent-hop event gap lacks exact fault evidence")
                event_fault = event_faults[0]
                if (
                    event_fault.expected_hop_event_sequence != expected_event_id
                    or event_fault.actual_hop_event_sequence != visit.event_sequence
                ):
                    raise ValueError("persistent-hop event gap disagrees with its fault")

            expected_counter = visit.valid_device_sample_counter_end_exclusive
            expected_event_id = visit.event_sequence + 1
            valid_samples += visit.valid_sample_count
            transition_samples += transition.sample_count
            visit_counts[visit.target_index] += 1
            target_samples[visit.target_index] += visit.valid_sample_count

        terminal_missing = missing_by_visit.get(len(self.visits), [])
        if terminal_missing:
            if len(terminal_missing) != 1:
                raise ValueError("persistent-hop terminal counter gap has duplicate faults")
            fault = terminal_missing[0]
            if (
                fault.expected_device_sample_counter != expected_counter
                or fault.actual_device_sample_counter
                != self.session_end_device_sample_counter_exclusive
            ):
                raise ValueError("persistent-hop terminal counter gap disagrees with its fault")
        elif expected_counter != self.session_end_device_sample_counter_exclusive:
            raise ValueError("persistent-hop terminal counter disagrees with its final visit")
        terminal_event_faults = event_by_visit.get(len(self.visits), [])
        if terminal_event_faults:
            if len(terminal_event_faults) != 1:
                raise ValueError("persistent-hop terminal event gap has duplicate faults")
            event_fault = terminal_event_faults[0]
            if event_fault.expected_hop_event_sequence != expected_event_id:
                raise ValueError("persistent-hop terminal event gap disagrees with its fault")
        if max(visit_counts) - min(visit_counts) > 1:
            raise ValueError("persistent-hop target visit coverage differs by more than one visit")

        expected_coverage = tuple(
            PersistentHopTargetCoverageV1(
                target_index=profile.target_index,
                target=profile.target,
                visit_count=visit_counts[profile.target_index],
                valid_sample_count=target_samples[profile.target_index],
            )
            for profile in plan.profiles
        )
        if self.target_coverage != expected_coverage:
            raise ValueError("persistent-hop target coverage disagrees with visits")

        missing_samples = sum(
            item.missing_sample_count
            for item in self.continuity_faults
            if item.kind == "missing_samples"
        )
        overflow_count = sum(item.kind == "rx_overflow" for item in self.continuity_faults)
        event_gap_count = sum(
            int(item.actual_hop_event_sequence or 0) - int(item.expected_hop_event_sequence or 0)
            for item in self.continuity_faults
            if item.kind == "hop_event_sequence_gap"
        )
        device_span = (
            self.session_end_device_sample_counter_exclusive
            - self.session_start_device_sample_counter
        )
        if device_span != valid_samples + transition_samples + missing_samples:
            raise ValueError("persistent-hop duty denominator leaves device samples unaccounted")
        expected_duty_ppm = valid_samples * 1_000_000 // device_span if device_span else 0
        if (
            self.valid_sample_count != valid_samples
            or self.transition_invalid_sample_count != transition_samples
            or self.missing_sample_count != missing_samples
            or self.overflow_count != overflow_count
            or self.hop_event_sequence_gap_count != event_gap_count
            or self.duty_denominator_sample_count != device_span
            or self.valid_duty_ppm != expected_duty_ppm
        ):
            raise ValueError("persistent-hop terminal accounting disagrees with evidence")
        if self.continuity_attested != (not self.continuity_faults):
            raise ValueError("persistent-hop continuity status disagrees with faults")
        expected_fault_flag = bool(self.continuity_faults)
        if bool(terminal_flags & 4) != expected_fault_flag:
            raise ValueError("persistent-hop terminal continuity flag disagrees with faults")
        status = self.terminal_status
        if (
            status.first_counter != self.session_start_device_sample_counter
            or status.final_counter != self.session_end_device_sample_counter_exclusive
            or status.visits_started != len(self.visits)
            or status.events_emitted != len(self.visits)
            or status.next_event_sequence != len(self.visits) + self.hop_event_sequence_gap_count
            or status.planned_dwells != plan.maximum_visit_count
        ):
            raise ValueError("persistent-hop terminal status disagrees with session evidence")
        if self.visits:
            first_transition = self.visits[0].transition_invalid_before
            if (
                status.startup_invalid_start_counter != first_transition.device_sample_counter
                or status.startup_invalid_end_counter_exclusive
                != first_transition.device_sample_counter_end_exclusive
            ):
                raise ValueError(
                    "persistent-hop terminal startup interval disagrees with first visit"
                )
        elif status.startup_invalid_start_counter != status.startup_invalid_end_counter_exclusive:
            raise ValueError("empty persistent-hop session claims a startup invalid interval")
        if status.device_dropped_events != self.hop_event_sequence_gap_count:
            raise ValueError("persistent-hop terminal dropped-event count disagrees with faults")
        if (
            self.restoration.status == "restored"
            and status.restored_lo_frequency_hz
            != self.restoration.original_settings.center_frequency_hz
        ):
            raise ValueError("persistent-hop terminal restored LO disagrees with original settings")
        if self.duty_target_met != (expected_duty_ppm >= plan.minimum_valid_duty_ppm):
            raise ValueError("persistent-hop duty-target status disagrees with exact accounting")
        return self

    @property
    def valid_duty_percent(self) -> float:
        """Convenience presentation; integer numerator and denominator remain authoritative."""

        if not self.duty_denominator_sample_count:
            return 0.0
        return self.valid_sample_count * 100.0 / self.duty_denominator_sample_count

    @property
    def qualified(self) -> bool:
        return (
            self.capture_outcome == "complete"
            and self.continuity_attested
            and self.duty_target_met
            and self.restoration.status == "restored"
        )
