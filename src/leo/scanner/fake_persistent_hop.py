"""Deterministic no-hardware implementation of the persistent hopping port."""

from __future__ import annotations

import hashlib
from contextlib import suppress

import numpy as np

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode
from leo.scanner.persistent_hop import (
    PersistentHopCaptureOutcome,
    PersistentHopContinuityFaultV1,
    PersistentHopPlanV1,
    PersistentHopRestorationReceiptV1,
    PersistentHopSessionReceiptV1,
    PersistentHopTargetCoverageV1,
    PersistentHopTerminalReason,
    PersistentHopTerminalStatusV1,
    PersistentHopTransitionInvalidSpanV1,
    PersistentHopVisitV1,
)
from leo.scanner.persistent_hop_ports import PersistentHopVisitBlock
from leo.scanner.ports import ScanRadioIdentity


class FakePersistentHopError(RuntimeError):
    """The deterministic fake rejected a lifecycle action or injected a failure."""


def default_fake_persistent_hop_settings() -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=1_000_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=40.0),
            ReceiverGainV1(receiver_id=1, gain_db=40.0),
        ),
    )


class FakePersistentHopRadio:
    """One fake radio with exact restoration and a single active-session rule."""

    def __init__(
        self,
        radio_id: str = "fake-persistent-hop",
        *,
        serial: str = "fake-persistent-hop-serial",
        initial_settings: RadioSettingsV1 | None = None,
        transition_invalid_ms: int = 12,
        gaps_before_visits: dict[int, int] | None = None,
        overflow_visits: set[int] | None = None,
        hop_event_sequence_gaps_before_visits: dict[int, int] | None = None,
        restoration_error: str | None = None,
        transport_loss_before_visit: int | None = None,
        first_device_sample_counter: int = 1_000_000,
    ) -> None:
        if transition_invalid_ms <= 0:
            raise ValueError("fake persistent-hop transition interval must be positive")
        if first_device_sample_counter < 0:
            raise ValueError("fake persistent-hop first device counter must be nonnegative")
        if any(index <= 0 or missing <= 0 for index, missing in (gaps_before_visits or {}).items()):
            raise ValueError("fake gaps must be positive and occur after the first visit")
        if any(
            index <= 0 or missing <= 0
            for index, missing in (hop_event_sequence_gaps_before_visits or {}).items()
        ):
            raise ValueError("fake event gaps must be positive and occur after the first visit")
        self._identity = ScanRadioIdentity(radio_id, serial, f"fake://{radio_id}")
        self._settings = initial_settings or default_fake_persistent_hop_settings()
        self._transition_invalid_ms = transition_invalid_ms
        self._gaps_before_visits = dict(gaps_before_visits or {})
        self._overflow_visits = frozenset(overflow_visits or set())
        self._hop_event_sequence_gaps = dict(hop_event_sequence_gaps_before_visits or {})
        self._restoration_error = restoration_error
        self._transport_loss_before_visit = transport_loss_before_visit
        self._first_device_sample_counter = first_device_sample_counter
        self._is_open = False
        self._active_session: FakePersistentHopSession | None = None
        self.lifecycle: list[str] = []

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    @property
    def settings(self) -> RadioSettingsV1:
        return self._settings

    def open(self) -> ScanRadioIdentity:
        if self._is_open:
            raise FakePersistentHopError("fake persistent-hop radio is already open")
        self._is_open = True
        self.lifecycle.append("open")
        return self.identity

    def begin_session(
        self, plan: PersistentHopPlanV1, *, session_id: str
    ) -> FakePersistentHopSession:
        if not self._is_open:
            raise FakePersistentHopError("fake persistent-hop radio is not open")
        if self._active_session is not None:
            raise FakePersistentHopError("fake persistent-hop radio already has an active session")
        transition_invalid_samples = plan.sample_rate_hz * self._transition_invalid_ms // 1_000
        if transition_invalid_samples <= plan.transition_guard_samples:
            raise FakePersistentHopError(
                "fake transition interval must exceed the plan's post-transition guard"
            )
        original = self._settings
        self._settings = RadioSettingsV1(
            center_frequency_hz=plan.profiles[0].target.if_center_hz,
            sample_rate_hz=plan.sample_rate_hz,
            bandwidth_hz=plan.bandwidth_hz,
            receiver_ids=plan.receiver_ids,
            gain_mode=original.gain_mode,
            gains=(
                tuple(
                    ReceiverGainV1(receiver_id=receiver_id, gain_db=40.0)
                    for receiver_id in plan.receiver_ids
                )
                if original.gain_mode is GainMode.MANUAL
                else ()
            ),
        )
        session = FakePersistentHopSession(
            self,
            plan,
            session_id=session_id,
            original_settings=original,
            transition_invalid_samples=transition_invalid_samples,
            first_device_sample_counter=self._first_device_sample_counter,
            gaps_before_visits=self._gaps_before_visits,
            overflow_visits=self._overflow_visits,
            hop_event_sequence_gaps_before_visits=self._hop_event_sequence_gaps,
            restoration_error=self._restoration_error,
            transport_loss_before_visit=self._transport_loss_before_visit,
        )
        self._active_session = session
        self.lifecycle.append(f"begin_session:{session_id}")
        return session

    def _session_finished(
        self, session: FakePersistentHopSession, restoration: PersistentHopRestorationReceiptV1
    ) -> None:
        if self._active_session is not session:
            raise FakePersistentHopError("fake persistent-hop terminal session is not active")
        if restoration.restored_settings is not None:
            self._settings = restoration.restored_settings
        self._active_session = None
        self.lifecycle.append(f"finish_session:{restoration.status}")

    def close(self) -> None:
        if not self._is_open:
            return
        if self._active_session is not None:
            raise FakePersistentHopError(
                "active fake persistent-hop session must finish before close"
            )
        self._is_open = False
        self.lifecycle.append("close")


class FakePersistentHopSession:
    """Deterministic visit source with optional fail-closed continuity injections."""

    def __init__(
        self,
        radio: FakePersistentHopRadio,
        plan: PersistentHopPlanV1,
        *,
        session_id: str,
        original_settings: RadioSettingsV1,
        transition_invalid_samples: int,
        first_device_sample_counter: int,
        gaps_before_visits: dict[int, int],
        overflow_visits: frozenset[int],
        hop_event_sequence_gaps_before_visits: dict[int, int],
        restoration_error: str | None,
        transport_loss_before_visit: int | None,
    ) -> None:
        self._radio = radio
        self._plan = plan
        self._session_id = session_id
        self._original_settings = original_settings
        self._transition_invalid_samples = transition_invalid_samples
        self._first_counter = first_device_sample_counter
        self._next_counter = first_device_sample_counter
        self._next_event_sequence = 0
        self._gaps_before_visits = gaps_before_visits
        self._overflow_visits = overflow_visits
        self._hop_event_sequence_gaps = hop_event_sequence_gaps_before_visits
        self._restoration_error = restoration_error
        self._transport_loss_before_visit = transport_loss_before_visit
        self._visits: list[PersistentHopVisitV1] = []
        self._faults: list[PersistentHopContinuityFaultV1] = []
        self._sample_cache: dict[int, np.ndarray] = {}
        self._terminal = False
        self._cancelled = False
        self._finished = False
        self._transport_lost = False

    @property
    def plan(self) -> PersistentHopPlanV1:
        return self._plan

    @property
    def complete(self) -> bool:
        return self._terminal

    def read_visit(self) -> PersistentHopVisitBlock:
        if self._terminal and not self._transport_lost:
            raise StopIteration
        evidence = self._advance_visit()
        samples = self._sample_cache.get(evidence.target_index)
        if samples is None:
            samples = np.empty(
                (self.plan.valid_visit_samples, len(self.plan.receiver_ids)),
                dtype=np.complex64,
            )
            for receiver_column, receiver_id in enumerate(self.plan.receiver_ids):
                samples[:, receiver_column] = complex(
                    evidence.target_index + 1,
                    receiver_id + 1,
                )
            samples.setflags(write=False)
            self._sample_cache[evidence.target_index] = samples
        return PersistentHopVisitBlock(samples, self.plan.receiver_ids, evidence)

    def request_cancel(self) -> None:
        if self._finished:
            raise FakePersistentHopError("fake persistent-hop session was already finished")
        if self._transport_lost:
            raise FakePersistentHopError("cannot cancel after persistent-hop transport loss")
        if self._terminal:
            return
        self._cancelled = True
        self._terminal = True

    def run_to_completion(self) -> PersistentHopSessionReceiptV1:
        """Advance without materializing IQ, then return one terminal fake receipt."""

        while not self.complete:
            with suppress(StopIteration):
                self._advance_visit()
        return self.finish()

    def _advance_visit(self) -> PersistentHopVisitV1:
        if self._finished or self._terminal:
            raise FakePersistentHopError("fake persistent-hop session is terminal")
        visit_index = len(self._visits)
        if self._transport_loss_before_visit == visit_index:
            self._transport_lost = True
            self._terminal = True
            raise FakePersistentHopError("injected persistent-hop transport loss")

        missing = self._gaps_before_visits.get(visit_index, 0)
        if missing:
            expected = self._next_counter
            self._next_counter += missing
            self._faults.append(
                PersistentHopContinuityFaultV1(
                    fault_index=len(self._faults),
                    before_visit_index=visit_index,
                    kind="missing_samples",
                    expected_device_sample_counter=expected,
                    actual_device_sample_counter=self._next_counter,
                    missing_sample_count=missing,
                    reason="deterministic fake injected a device-counter gap",
                )
            )
            self._terminal = True
            raise StopIteration

        event_gap = self._hop_event_sequence_gaps.get(visit_index, 0)
        expected_event_sequence = self._next_event_sequence
        self._next_event_sequence += event_gap
        if event_gap:
            self._faults.append(
                PersistentHopContinuityFaultV1(
                    fault_index=len(self._faults),
                    before_visit_index=visit_index,
                    kind="hop_event_sequence_gap",
                    expected_hop_event_sequence=expected_event_sequence,
                    actual_hop_event_sequence=self._next_event_sequence,
                    reason="deterministic fake injected a device-event gap",
                )
            )
            self._terminal = True
            raise StopIteration

        profile = self.plan.profiles[visit_index % len(self.plan.profiles)]
        invalid_start = self._next_counter
        transition_samples = self._transition_invalid_samples - self.plan.transition_guard_samples
        transition_after = invalid_start + transition_samples
        invalid_end = transition_after + self.plan.transition_guard_samples
        transition = PersistentHopTransitionInvalidSpanV1(
            kind="startup_prime" if visit_index == 0 else "retune_and_settle",
            visit_index=visit_index,
            from_profile_index=(
                None if visit_index == 0 else self._visits[-1].fastlock_profile_index
            ),
            to_profile_index=profile.fastlock_profile_index,
            transition_before_counter=invalid_start,
            transition_after_counter=transition_after,
            device_sample_counter=invalid_start,
            device_sample_counter_end_exclusive=invalid_end,
        )
        valid_start = invalid_end
        valid_end = valid_start + self.plan.valid_visit_samples
        visit = PersistentHopVisitV1(
            visit_index=visit_index,
            sweep_index=visit_index // len(self.plan.profiles),
            target_index=profile.target_index,
            fastlock_profile_index=profile.fastlock_profile_index,
            event_sequence=self._next_event_sequence,
            device_event_id=self._next_event_sequence + 1,
            fastlock_slot=profile.fastlock_profile_index,
            target=profile.target,
            requested_if_center_hz=profile.target.if_center_hz,
            actual_lo_frequency_hz=profile.target.if_center_hz,
            actual_if_offset_hz=0,
            transition_invalid_before=transition,
            valid_device_sample_counter=valid_start,
            valid_device_sample_counter_end_exclusive=valid_end,
            valid_sample_count=self.plan.valid_visit_samples,
        )
        self._visits.append(visit)
        self._next_counter = valid_end
        self._next_event_sequence += 1

        if visit_index in self._overflow_visits:
            self._faults.append(
                PersistentHopContinuityFaultV1(
                    fault_index=len(self._faults),
                    before_visit_index=visit_index,
                    kind="rx_overflow",
                    expected_device_sample_counter=valid_start,
                    actual_device_sample_counter=valid_start,
                    overflow_observed=True,
                    reason="deterministic fake injected an RX overflow",
                )
            )

        elapsed = self._next_counter - self._first_counter
        if self._faults or elapsed >= self.plan.nominal_device_sample_count:
            self._terminal = True
        return visit

    def finish(self) -> PersistentHopSessionReceiptV1:
        if self._finished:
            raise FakePersistentHopError("fake persistent-hop session was already finished")
        if self._transport_lost:
            raise FakePersistentHopError(
                "transport loss has no server-attested persistent-hop terminal receipt"
            )
        if not self._terminal:
            raise FakePersistentHopError(
                "fake persistent-hop session has not reached a terminal state"
            )

        restoration = self._restoration()
        self._finished = True
        self._radio._session_finished(self, restoration)
        capture_outcome: PersistentHopCaptureOutcome = (
            "failed"
            if self._faults or restoration.status == "failed"
            else "cancelled"
            if self._cancelled
            else "complete"
        )
        reason: PersistentHopTerminalReason = (
            "restore_error"
            if restoration.status == "failed"
            else "client_close"
            if self._cancelled
            else "counter_discontinuity"
            if any(item.kind == "missing_samples" for item in self._faults)
            else "event_sequence"
            if any(item.kind == "hop_event_sequence_gap" for item in self._faults)
            else "device"
            if self._faults
            else "complete"
        )
        terminal_flags = 1 | 8 | 32
        if restoration.status == "restored":
            terminal_flags |= 16
        if self._faults:
            terminal_flags |= 4

        visits = tuple(self._visits)
        valid_samples = sum(item.valid_sample_count for item in visits)
        transition_samples = sum(item.transition_invalid_before.sample_count for item in visits)
        missing_samples = sum(
            item.missing_sample_count for item in self._faults if item.kind == "missing_samples"
        )
        device_span = self._next_counter - self._first_counter
        coverage = tuple(
            PersistentHopTargetCoverageV1(
                target_index=profile.target_index,
                target=profile.target,
                visit_count=sum(item.target_index == profile.target_index for item in visits),
                valid_sample_count=sum(
                    item.valid_sample_count
                    for item in visits
                    if item.target_index == profile.target_index
                ),
            )
            for profile in self.plan.profiles
        )
        event_gap_count = sum(
            int(item.actual_hop_event_sequence or 0) - int(item.expected_hop_event_sequence or 0)
            for item in self._faults
            if item.kind == "hop_event_sequence_gap"
        )
        restored_lo = self._original_settings.center_frequency_hz
        terminal = PersistentHopTerminalStatusV1(
            state=(
                "failed"
                if capture_outcome == "failed"
                else "cancelled"
                if capture_outcome == "cancelled"
                else "completed"
            ),
            reason=reason,
            error_code=-5 if capture_outcome == "failed" else 0,
            flags=terminal_flags,
            session_id=self._wire_session_id(),
            visits_started=len(visits),
            events_emitted=len(visits),
            next_event_sequence=self._next_event_sequence,
            last_block_sequence=max(0, len(visits) - 1),
            last_block_end_counter=self._next_counter,
            first_counter=self._first_counter,
            final_counter=self._next_counter,
            restore_before_counter=self._next_counter,
            restore_after_counter=self._next_counter,
            restored_lo_frequency_hz=restored_lo,
            restore_error_code=0 if restoration.status == "restored" else -5,
            active_profile_index=(visits[-1].fastlock_profile_index if visits else None),
            restored_profile_index=None,
            startup_invalid_start_counter=(
                visits[0].transition_invalid_before.device_sample_counter
                if visits
                else self._first_counter
            ),
            startup_invalid_end_counter_exclusive=(
                visits[0].transition_invalid_before.device_sample_counter_end_exclusive
                if visits
                else self._first_counter
            ),
            device_dropped_events=event_gap_count,
        )
        receipt = PersistentHopSessionReceiptV1(
            session_id=self._session_id,
            radio_id=self._radio.identity.radio_id,
            radio_serial=self._radio.identity.serial,
            radio_uri=self._radio.identity.uri,
            plan=self.plan,
            metadata_abi_version=3,
            stream_generation=f"fake-hop-{self._wire_session_id()}",
            kernel_buffers_requested=self.plan.kernel_buffers,
            kernel_buffers_readback=self.plan.kernel_buffers,
            capture_outcome=capture_outcome,
            terminal_status=terminal,
            session_start_device_sample_counter=self._first_counter,
            session_end_device_sample_counter_exclusive=self._next_counter,
            visits=visits,
            continuity_faults=tuple(self._faults),
            target_coverage=coverage,
            valid_sample_count=valid_samples,
            transition_invalid_sample_count=transition_samples,
            missing_sample_count=missing_samples,
            overflow_count=sum(item.kind == "rx_overflow" for item in self._faults),
            hop_event_sequence_gap_count=event_gap_count,
            duty_denominator_sample_count=device_span,
            valid_duty_ppm=(valid_samples * 1_000_000 // device_span if device_span else 0),
            continuity_attested=not self._faults,
            duty_target_met=(
                bool(device_span)
                and valid_samples * 1_000_000 // device_span >= self.plan.minimum_valid_duty_ppm
            ),
            restoration=restoration,
        )
        return receipt

    def _restoration(self) -> PersistentHopRestorationReceiptV1:
        if self._restoration_error is None:
            return PersistentHopRestorationReceiptV1(
                status="restored",
                original_settings=self._original_settings,
                restored_settings=self._original_settings,
                receive_buffer_closed=True,
                fastlock_inactive=True,
            )
        return PersistentHopRestorationReceiptV1(
            status="failed",
            original_settings=self._original_settings,
            restored_settings=None,
            receive_buffer_closed=True,
            fastlock_inactive=False,
            error_type="FakePersistentHopError",
            error_message=self._restoration_error,
        )

    def _wire_session_id(self) -> int:
        digest = hashlib.sha256(self._session_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "little") or 1
