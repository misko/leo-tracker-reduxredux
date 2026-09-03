"""Anti-corruption adapter for one counter-authoritative Pluto hop session."""

from __future__ import annotations

import importlib
import ipaddress
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Literal, cast

import numpy as np

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode
from leo.scanner.persistent_hop import (
    PersistentHopCaptureOutcome,
    PersistentHopPlanV1,
    PersistentHopRestorationReceiptV1,
    PersistentHopSessionReceiptV1,
    PersistentHopTargetCoverageV1,
    PersistentHopTerminalReason,
    PersistentHopTerminalStatusV1,
    PersistentHopTransitionInvalidSpanV1,
    PersistentHopVisitV1,
    persistent_hop_wire_session_id,
)
from leo.scanner.persistent_hop_ports import (
    PersistentHopSession,
    PersistentHopVisitBlock,
)
from leo.scanner.ports import ScanRadioIdentity

PERSISTENT_HOP_EXCLUDED_SERIAL = "104000bac4950008230026001b440a003a"
_DEFAULT_READ_AHEAD_VISITS = 8
_MAXIMUM_READ_AHEAD_VISITS = 64
_PRODUCER_POLL_SECONDS = 0.05
_PRODUCER_JOIN_TIMEOUT_SECONDS = 15.0

PersistentHopClientFactory = Callable[[str, str], Any]
PersistentHopPlanFactory = Callable[[PersistentHopPlanV1], Any]
TandemRequestFactory = Callable[[], Any]


class PlutoPersistentHopError(RuntimeError):
    """The production persistent-hop adapter rejected incomplete evidence."""


class PlutoPersistentHopRadio:
    """Bind Leo contracts to PPU without leaking hardware types into the domain.

    ``open`` begins the logical ownership episode without creating a second IIO
    context. PPU opens and serial-attests the single physical-LAN context
    atomically with ``begin_session`` and retains it through HOPT and restore.
    """

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        radio_id: str,
        iiod_port: int | None = None,
        read_ahead_visits: int = _DEFAULT_READ_AHEAD_VISITS,
        client_factory: PersistentHopClientFactory | None = None,
        plan_factory: PersistentHopPlanFactory | None = None,
        tandem_request_factory: TandemRequestFactory | None = None,
    ) -> None:
        self._uri = _physical_lan_uri(host, iiod_port=iiod_port)
        if not expected_serial or expected_serial != expected_serial.strip():
            raise ValueError("persistent-hop serial must be one trimmed nonempty value")
        if expected_serial == PERSISTENT_HOP_EXCLUDED_SERIAL:
            raise ValueError("the excluded Pluto serial cannot run persistent hopping")
        if not radio_id or radio_id != radio_id.strip():
            raise ValueError("persistent-hop radio ID must be one trimmed nonempty value")
        if (
            not isinstance(read_ahead_visits, int)
            or isinstance(read_ahead_visits, bool)
            or not 1 <= read_ahead_visits <= _MAXIMUM_READ_AHEAD_VISITS
        ):
            raise ValueError("persistent-hop read-ahead visits must be within 1..64")
        self._expected_serial = expected_serial
        self._identity = ScanRadioIdentity(radio_id, expected_serial, self._uri)
        self._client_factory = client_factory or _load_client
        self._plan_factory = plan_factory or _load_plan
        self._tandem_request_factory = tandem_request_factory or _load_tandem_hold_request
        self._read_ahead_visits = read_ahead_visits
        self._opened = False
        self._session: _PlutoPersistentHopSession | None = None

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        if self._opened:
            raise PlutoPersistentHopError("persistent-hop radio is already open")
        self._opened = True
        return self._identity

    def begin_session(
        self,
        plan: PersistentHopPlanV1,
        *,
        session_id: str,
    ) -> PersistentHopSession:
        if not self._opened:
            raise PlutoPersistentHopError("persistent-hop radio must be opened first")
        if self._session is not None:
            raise PlutoPersistentHopError("persistent-hop radio already owns a session")
        wire_session_id = persistent_hop_wire_session_id(session_id)
        try:
            client = self._client_factory(self._uri, self._expected_serial)
            upstream = client.start(
                self._plan_factory(plan),
                session_id=wire_session_id,
                tandem_request=self._tandem_request_factory(),
            )
        except Exception as error:
            raise PlutoPersistentHopError(
                f"persistent-hop provider start failed: {type(error).__name__}: {error}"
            ) from error
        session = _PlutoPersistentHopSession(
            upstream,
            plan=plan,
            identity=self._identity,
            session_id=session_id,
            wire_session_id=wire_session_id,
            read_ahead_visits=self._read_ahead_visits,
        )
        self._session = session
        return session

    def close(self) -> None:
        session, self._session = self._session, None
        self._opened = False
        if session is not None and not session.complete:
            try:
                session.request_cancel()
                session.finish()
            except Exception as error:
                raise PlutoPersistentHopError(
                    f"persistent-hop radio close failed: {type(error).__name__}: {error}"
                ) from error


class _PlutoPersistentHopSession:
    def __init__(
        self,
        upstream: Any,
        *,
        plan: PersistentHopPlanV1,
        identity: ScanRadioIdentity,
        session_id: str,
        wire_session_id: int,
        read_ahead_visits: int,
    ) -> None:
        self._upstream = upstream
        self._plan = plan
        self._identity = identity
        self._session_id = session_id
        self._wire_session_id = wire_session_id
        self._visits: queue.Queue[PersistentHopVisitBlock] = queue.Queue(maxsize=read_ahead_visits)
        self._cancel_requested = threading.Event()
        self._producer_done = threading.Event()
        self._producer_error: BaseException | None = None
        self._producer_error_observed = False
        self._receipt: PersistentHopSessionReceiptV1 | None = None
        self._produced_evidence: list[PersistentHopVisitV1] = []
        self._upstream_cancel_called = False
        self._upstream_terminal = False
        self._producer = threading.Thread(
            target=self._run_producer,
            name=f"leo-hop-radio-{session_id}",
            daemon=False,
        )
        self._producer.start()

    @property
    def plan(self) -> PersistentHopPlanV1:
        return self._plan

    @property
    def complete(self) -> bool:
        return self._producer_done.is_set() and self._visits.empty()

    def read_visit(self) -> PersistentHopVisitBlock:
        while True:
            try:
                return self._visits.get(timeout=_PRODUCER_POLL_SECONDS)
            except queue.Empty:
                if not self._producer_done.is_set():
                    continue
                self._join_producer()
                self._raise_producer_error()
                if self._receipt is None:
                    raise PlutoPersistentHopError(
                        "persistent-hop producer ended without terminal evidence"
                    ) from None
                raise StopIteration from None

    def request_cancel(self) -> None:
        if not self.complete:
            self._cancel_requested.set()

    def finish(self) -> PersistentHopSessionReceiptV1:
        if not self.complete:
            if not self._cancel_requested.is_set():
                raise PlutoPersistentHopError(
                    "persistent-hop finish requires a server-attested terminal receipt"
                )
            self._drain_recovery_visits()
        self._join_producer()
        self._raise_producer_error()
        if self._receipt is None:
            raise PlutoPersistentHopError(
                "persistent-hop finish requires a server-attested terminal receipt"
            )
        return self._receipt

    def _run_producer(self) -> None:
        try:
            visits = iter(self._upstream.visits())
            while True:
                if self._cancel_requested.is_set():
                    self._cancel_upstream()
                    self._receipt = self._map_receipt()
                    return
                try:
                    sampled = next(visits)
                except StopIteration:
                    self._upstream_terminal = True
                    self._receipt = self._map_receipt()
                    return
                block = self._map_sampled_visit(sampled)
                self._put_completed_visit(block)
                self._produced_evidence.append(block.evidence)
                if self._cancel_requested.is_set():
                    self._cancel_upstream()
                    self._receipt = self._map_receipt()
                    return
        except BaseException as error:
            self._recover_terminal_after_failure(error)
            self._producer_error = error
        finally:
            self._producer_done.set()

    def _map_sampled_visit(self, sampled: Any) -> PersistentHopVisitBlock:
        evidence = _map_visit(sampled.visit, self._plan)
        values = np.asarray(sampled.samples)
        expected = (len(self._plan.receiver_ids), evidence.valid_sample_count)
        if values.dtype != np.complex64 or values.shape != expected:
            raise PlutoPersistentHopError(
                f"PPU persistent-hop IQ is {values.shape}/{values.dtype}, expected "
                f"{expected}/complex64"
            )
        return PersistentHopVisitBlock(
            samples=np.ascontiguousarray(values.T, dtype=np.complex64),
            receiver_ids=self._plan.receiver_ids,
            evidence=evidence,
        )

    def _put_completed_visit(self, block: PersistentHopVisitBlock) -> None:
        while True:
            try:
                self._visits.put(block, timeout=_PRODUCER_POLL_SECONDS)
                return
            except queue.Full:
                continue

    def _cancel_upstream(self) -> None:
        self._upstream_cancel_called = True
        try:
            self._upstream.cancel()
        except Exception as error:
            raise PlutoPersistentHopError(
                f"persistent-hop in-band cancellation failed: {type(error).__name__}: {error}"
            ) from error
        self._upstream_terminal = True

    def _recover_terminal_after_failure(self, primary: BaseException) -> None:
        try:
            if not self._upstream_terminal and not self._upstream_cancel_called:
                self._cancel_upstream()
            if self._upstream_terminal and self._receipt is None:
                self._receipt = self._map_receipt()
        except BaseException as cleanup:
            primary.add_note(
                "persistent-hop producer terminal recovery failed: "
                f"{type(cleanup).__name__}: {cleanup}"
            )

    def _drain_recovery_visits(self) -> None:
        deadline = time.monotonic() + _PRODUCER_JOIN_TIMEOUT_SECONDS
        while not self.complete:
            with suppress(queue.Empty):
                self._visits.get(timeout=_PRODUCER_POLL_SECONDS)
            if time.monotonic() >= deadline:
                raise PlutoPersistentHopError(
                    "persistent-hop producer did not stop after cancellation"
                )

    def _join_producer(self) -> None:
        self._producer.join(timeout=_PRODUCER_JOIN_TIMEOUT_SECONDS)
        if self._producer.is_alive():
            raise PlutoPersistentHopError("persistent-hop producer did not stop after cancellation")

    def _raise_producer_error(self) -> None:
        if self._producer_error is not None and not self._producer_error_observed:
            self._producer_error_observed = True
            raise self._producer_error

    def _map_receipt(self) -> PersistentHopSessionReceiptV1:
        try:
            receipt = _map_receipt(
                self._upstream.receipt,
                plan=self._plan,
                identity=self._identity,
                session_id=self._session_id,
                wire_session_id=self._wire_session_id,
            )
            if receipt.visits != tuple(self._produced_evidence):
                raise PlutoPersistentHopError(
                    "PPU terminal visits disagree with produced IQ visits"
                )
            return receipt
        except PlutoPersistentHopError:
            raise
        except Exception as error:
            raise PlutoPersistentHopError(
                f"persistent-hop terminal evidence mapping failed: {type(error).__name__}: {error}"
            ) from error


def _map_receipt(
    upstream: Any,
    *,
    plan: PersistentHopPlanV1,
    identity: ScanRadioIdentity,
    session_id: str,
    wire_session_id: int,
) -> PersistentHopSessionReceiptV1:
    if int(upstream.session_id) != wire_session_id:
        raise PlutoPersistentHopError("PPU terminal receipt belongs to another session")
    if str(upstream.radio_serial) != identity.serial or str(upstream.radio_uri) != identity.uri:
        raise PlutoPersistentHopError("PPU terminal radio identity changed")
    if int(upstream.metadata_abi_version) != 3:
        raise PlutoPersistentHopError("PPU terminal receipt lost metadata ABI 3")
    if upstream.stream_generation is None or int(upstream.stream_generation) <= 0:
        raise PlutoPersistentHopError("PPU terminal receipt lacks a stream generation")
    if (
        int(upstream.kernel_buffers_requested) != plan.kernel_buffers
        or int(upstream.kernel_buffers_readback) != plan.kernel_buffers
    ):
        raise PlutoPersistentHopError("PPU terminal kernel-buffer evidence changed")
    if not bool(upstream.continuity_attested):
        raise PlutoPersistentHopError("PPU terminal receipt reports lost continuity")
    if any(
        int(value)
        for value in (
            upstream.missing_sample_count,
            upstream.overflow_count,
            upstream.hop_event_sequence_gap_count,
        )
    ):
        raise PlutoPersistentHopError("PPU terminal receipt contains a continuity fault")

    visits = tuple(_map_visit(item, plan) for item in upstream.visits)
    status = upstream.status
    incomplete_count = int(status.visits_started) - len(visits)
    if incomplete_count not in (0, 1):
        raise PlutoPersistentHopError("PPU terminal incomplete-visit count is invalid")
    retained_invalid = sum(item.transition_invalid_before.sample_count for item in visits)
    trailing_invalid = int(upstream.transition_invalid_sample_count) - retained_invalid
    trailing_valid = int(upstream.incomplete_visit_sample_count)
    if trailing_invalid < 0 or trailing_valid < 0:
        raise PlutoPersistentHopError("PPU terminal trailing sample counts regressed")
    if not incomplete_count and (trailing_invalid or trailing_valid):
        raise PlutoPersistentHopError("PPU terminal trailing samples lack a started visit")
    capture_outcome = str(upstream.capture_outcome)
    if capture_outcome not in {"complete", "cancelled"}:
        raise PlutoPersistentHopError("PPU did not return a supported terminal outcome")
    if int(status.planned_dwells) != 2_500:
        raise PlutoPersistentHopError("PPU terminal dwell safety bound changed")

    restoration = _map_restoration(upstream)
    mapped_status = PersistentHopTerminalStatusV1(
        state=_state_name(status.state),
        reason=_reason_name(status.reason),
        error_code=int(status.error_code),
        flags=int(status.flags),
        session_id=int(status.session_id),
        planned_dwells=2_500,
        visits_started=int(status.visits_started),
        events_emitted=int(status.events_emitted),
        next_event_sequence=int(status.next_event_sequence),
        last_block_sequence=int(status.last_block_sequence),
        last_block_end_counter=int(status.last_block_end_counter),
        first_counter=int(status.first_counter),
        final_counter=int(status.final_counter),
        restore_before_counter=int(status.restore_before_counter),
        restore_after_counter=int(status.restore_after_counter),
        restored_lo_frequency_hz=int(status.restored_lo_frequency_hz),
        restore_error_code=int(status.restore_error_code),
        active_profile_index=_optional_profile(status.active_profile_index),
        restored_profile_index=_optional_profile(status.restored_profile_index),
        startup_invalid_start_counter=int(status.startup_invalid_start_counter),
        startup_invalid_end_counter_exclusive=int(status.startup_invalid_end_counter_exclusive),
        device_dropped_events=int(status.device_dropped_events),
    )
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
        for profile in plan.profiles
    )
    _require_upstream_coverage(upstream.target_coverage, coverage)
    return PersistentHopSessionReceiptV1(
        session_id=session_id,
        radio_id=identity.radio_id,
        radio_serial=identity.serial,
        radio_uri=identity.uri,
        plan=plan,
        stream_generation=f"iio-{int(upstream.stream_generation):016x}",
        kernel_buffers_requested=int(upstream.kernel_buffers_requested),
        kernel_buffers_readback=int(upstream.kernel_buffers_readback),
        capture_outcome=cast(PersistentHopCaptureOutcome, capture_outcome),
        terminal_status=mapped_status,
        session_start_device_sample_counter=int(status.first_counter),
        session_end_device_sample_counter_exclusive=int(status.final_counter),
        visits=visits,
        target_coverage=coverage,
        valid_sample_count=int(upstream.valid_sample_count),
        transition_invalid_sample_count=int(upstream.transition_invalid_sample_count),
        terminal_incomplete_visit_count=incomplete_count,
        terminal_unretained_invalid_sample_count=trailing_invalid,
        terminal_unretained_valid_sample_count=trailing_valid,
        missing_sample_count=int(upstream.missing_sample_count),
        overflow_count=int(upstream.overflow_count),
        hop_event_sequence_gap_count=int(upstream.hop_event_sequence_gap_count),
        duty_denominator_sample_count=int(upstream.duty_denominator_sample_count),
        valid_duty_ppm=int(upstream.valid_duty_ppm),
        continuity_attested=bool(upstream.continuity_attested),
        duty_target_met=bool(upstream.duty_target_met),
        restoration=restoration,
    )


def _map_visit(upstream: Any, plan: PersistentHopPlanV1) -> PersistentHopVisitV1:
    visit_index = int(upstream.visit_index)
    target_index = int(upstream.target_index)
    if not 0 <= target_index < len(plan.profiles):
        raise PlutoPersistentHopError("PPU visit target lies outside the plan")
    profile = plan.profiles[target_index]
    invalid = upstream.transition_invalid_before
    from_profile = int(invalid.from_profile_index)
    device_event_flags = int(upstream.device_event_flags)
    if device_event_flags != 3:
        raise PlutoPersistentHopError("PPU visit lost counter or LO attestation")
    return PersistentHopVisitV1(
        visit_index=visit_index,
        sweep_index=int(upstream.sweep_index),
        target_index=target_index,
        fastlock_profile_index=int(upstream.fastlock_profile_index),
        event_sequence=int(upstream.event_sequence),
        device_event_id=int(upstream.device_event_id),
        device_event_flags=3,
        fastlock_slot=int(upstream.fastlock_slot),
        target=profile.target,
        requested_if_center_hz=int(upstream.requested_center_hz),
        actual_lo_frequency_hz=int(upstream.actual_lo_frequency_hz),
        actual_if_offset_hz=int(upstream.actual_if_offset_hz),
        transition_invalid_before=PersistentHopTransitionInvalidSpanV1(
            kind="startup_prime" if visit_index == 0 else "retune_and_settle",
            visit_index=visit_index,
            from_profile_index=None if from_profile == 0xFF else from_profile,
            to_profile_index=int(invalid.to_profile_index),
            transition_before_counter=int(invalid.transition_before_counter),
            transition_after_counter=int(invalid.transition_after_counter),
            device_sample_counter=int(invalid.device_sample_counter),
            device_sample_counter_end_exclusive=int(invalid.device_sample_counter_end_exclusive),
        ),
        valid_device_sample_counter=int(upstream.valid_device_sample_counter),
        valid_device_sample_counter_end_exclusive=int(
            upstream.valid_device_sample_counter_end_exclusive
        ),
        valid_sample_count=int(upstream.valid_sample_count),
    )


def _map_restoration(upstream: Any) -> PersistentHopRestorationReceiptV1:
    host = upstream.host_lifecycle
    server = upstream.restoration
    if host is None:
        raise PlutoPersistentHopError("PPU terminal receipt lacks host restoration evidence")
    original = _map_settings(host.original_settings)
    restored = _map_settings(host.restored_settings)
    succeeded = (
        str(server.status) == "restored"
        and original == restored
        and bool(host.receive_buffer_closed)
        and bool(host.fastlock_inactive)
    )
    if not succeeded:
        raise PlutoPersistentHopError("PPU did not attest exact two-layer restoration")
    return PersistentHopRestorationReceiptV1(
        status="restored",
        original_settings=original,
        restored_settings=restored,
        receive_buffer_closed=True,
        fastlock_inactive=True,
    )


def _map_settings(upstream: Any) -> RadioSettingsV1:
    modes = tuple(str(value) for value in upstream.gain_modes)
    if not modes or len(set(modes)) != 1:
        raise PlutoPersistentHopError("PPU settings use mixed or absent receiver gain modes")
    try:
        gain_mode = GainMode(modes[0])
    except ValueError as error:
        raise PlutoPersistentHopError("PPU settings use an unknown receiver gain mode") from error
    receiver_ids = tuple(int(value) for value in upstream.channels)
    gain_values = tuple(float(value) for value in upstream.gain_db)
    if gain_mode is GainMode.MANUAL and len(gain_values) != len(receiver_ids):
        raise PlutoPersistentHopError("PPU manual-gain readback is incomplete")
    return RadioSettingsV1(
        center_frequency_hz=_exact_integer(upstream.center_frequency_hz, "center frequency"),
        sample_rate_hz=_exact_integer(upstream.sample_rate_hz, "sample rate"),
        bandwidth_hz=_exact_integer(upstream.bandwidth_hz, "bandwidth"),
        receiver_ids=receiver_ids,
        gain_mode=gain_mode,
        gains=(
            tuple(
                ReceiverGainV1(receiver_id=receiver_id, gain_db=gain_db)
                for receiver_id, gain_db in zip(receiver_ids, gain_values, strict=True)
            )
            if gain_mode is GainMode.MANUAL
            else ()
        ),
    )


def _require_upstream_coverage(
    upstream: Any,
    expected: tuple[PersistentHopTargetCoverageV1, ...],
) -> None:
    observed = tuple(
        (int(item.target_index), int(item.visit_count), int(item.valid_sample_count))
        for item in upstream
    )
    wanted = tuple(
        (item.target_index, item.visit_count, item.valid_sample_count) for item in expected
    )
    if observed != wanted:
        raise PlutoPersistentHopError("PPU target coverage disagrees with mapped visits")


def _load_plan(plan: PersistentHopPlanV1) -> Any:
    module = importlib.import_module("pluto_plus.persistent_hop")
    profile_type = module.PersistentHopProfileV1
    plan_type = module.PersistentHopPlanV1
    return plan_type(
        nominal_duration_seconds=plan.nominal_duration_seconds,
        valid_visit_ms=plan.valid_visit_ms,
        sample_rate_hz=plan.sample_rate_hz,
        rf_bandwidth_hz=plan.bandwidth_hz,
        transition_guard_samples=plan.transition_guard_samples,
        samples_per_block=plan.samples_per_block,
        kernel_buffers=plan.kernel_buffers,
        minimum_valid_duty_ppm=plan.minimum_valid_duty_ppm,
        manual_gain_db=plan.gain_db,
        profiles=tuple(
            profile_type(
                target_index=profile.target_index,
                fastlock_profile_index=profile.fastlock_profile_index,
                center_hz=profile.target.if_center_hz,
                lo_hz=profile.target.if_center_hz,
                profile_crc32=0,
            )
            for profile in plan.profiles
        ),
    )


def _load_client(uri: str, expected_serial: str) -> Any:
    module = importlib.import_module("pluto_plus.hardware.iio_persistent_hop")
    return module.iio_persistent_hop_client(uri, expected_serial=expected_serial)


def _load_tandem_hold_request() -> Any:
    module = importlib.import_module("pluto_plus.tandem")
    return module.TandemSessionRequestV1(mode=module.TandemMode.HOLD)


def _physical_lan_uri(host: str, *, iiod_port: int | None = None) -> str:
    if not host or host != host.strip() or host.startswith("ip:"):
        raise ValueError("persistent-hop host must be a literal 192.168.1.* address")
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError as error:
        raise ValueError("persistent-hop host must be a literal 192.168.1.* address") from error
    network = ipaddress.IPv4Network("192.168.1.0/24")
    if str(address) != host or address not in network or address in {network[0], network[-1]}:
        raise ValueError("persistent-hop host must be a usable literal 192.168.1.* address")
    if iiod_port is not None and (
        not isinstance(iiod_port, int)
        or isinstance(iiod_port, bool)
        or not 1 <= iiod_port <= 65_535
    ):
        raise ValueError("persistent-hop iiOD port must be an integer within 1..65535")
    suffix = "" if iiod_port is None else f":{iiod_port}"
    return f"ip:{address}{suffix}"


def _exact_integer(value: Any, name: str) -> int:
    number = float(value)
    rounded = round(number)
    if number != rounded:
        raise PlutoPersistentHopError(f"PPU {name} readback is not integral")
    return rounded


def _optional_profile(value: Any) -> int | None:
    profile = int(value)
    return None if profile == 0xFF else profile


def _state_name(value: Any) -> Literal["completed", "cancelled", "failed"]:
    names = {"COMPLETED": "completed", "CANCELLED": "cancelled", "FAILED": "failed"}
    try:
        return cast(Literal["completed", "cancelled", "failed"], names[value.name])
    except (AttributeError, KeyError) as error:
        raise PlutoPersistentHopError("PPU terminal state is not terminal") from error


def _reason_name(value: Any) -> PersistentHopTerminalReason:
    names = {
        "PLAN_COMPLETE": "complete",
        "CLIENT_CLOSE": "client_close",
        "CLIENT_DISCONNECT": "disconnect",
        "DEVICE_ERROR": "device",
        "EVENT_OVERFLOW": "event_overflow",
        "EVENT_SEQUENCE": "event_sequence",
        "COUNTER_DISCONTINUITY": "counter_discontinuity",
        "PROTOCOL_ERROR": "protocol",
        "RESTORE_ERROR": "restore_error",
    }
    try:
        return cast(PersistentHopTerminalReason, names[value.name])
    except (AttributeError, KeyError) as error:
        raise PlutoPersistentHopError("PPU terminal reason is invalid") from error
