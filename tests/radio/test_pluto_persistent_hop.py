from __future__ import annotations

from threading import Event, get_ident
from types import SimpleNamespace

import numpy as np
import pytest

from leo.radio.pluto_persistent_hop import (
    PERSISTENT_HOP_EXCLUDED_SERIAL,
    PlutoPersistentHopRadio,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import (
    PersistentHopSessionReceiptV1,
    compile_persistent_hop_plan_v1,
    persistent_hop_wire_session_id,
)


class _Name:
    def __init__(self, name: str) -> None:
        self.name = name


class _UpstreamSession:
    def __init__(self, blocks, receipt) -> None:
        self._blocks = blocks
        self.receipt = receipt
        self.cancelled = False

    def visits(self):
        yield from self._blocks

    def cancel(self) -> None:
        self.cancelled = True


class _Client:
    def __init__(self, session, expected_wire_id: int) -> None:
        self.session = session
        self.expected_wire_id = expected_wire_id
        self.start_arguments = None

    def start(self, plan, *, session_id: int, tandem_request):
        assert session_id == self.expected_wire_id
        self.start_arguments = (plan, tandem_request)
        return self.session


class _HeldVisitUpstream(_UpstreamSession):
    def __init__(self, blocks, receipt) -> None:
        super().__init__(blocks, receipt)
        self.visit_entered = Event()
        self.release_visit = Event()
        self.visit_thread_id = None
        self.cancel_thread_id = None

    def visits(self):
        self.visit_thread_id = get_ident()
        self.visit_entered.set()
        assert self.release_visit.wait(timeout=2)
        yield from self._blocks

    def cancel(self) -> None:
        self.cancel_thread_id = get_ident()
        super().cancel()


class _QueueFullUpstream(_UpstreamSession):
    def __init__(self, blocks, receipt) -> None:
        super().__init__(blocks, receipt)
        self.second_visit_pulled = Event()
        self.cancel_thread_id = None
        self.visit_thread_id = None

    def visits(self):
        self.visit_thread_id = get_ident()
        for index, block in enumerate(self._blocks):
            if index == 1:
                self.second_visit_pulled.set()
            yield block

    def cancel(self) -> None:
        self.cancel_thread_id = get_ident()
        super().cancel()


class _ProducerFailure(RuntimeError):
    pass


class _FailingUpstream(_UpstreamSession):
    def __init__(self, blocks, receipt, error) -> None:
        super().__init__(blocks, receipt)
        self.error = error
        self.visit_thread_id = None
        self.cancel_thread_id = None

    def visits(self):
        self.visit_thread_id = get_ident()
        yield from self._blocks
        raise self.error

    def cancel(self) -> None:
        self.cancel_thread_id = get_ident()
        super().cancel()


def _cancelled_source(*, visit_count: int = 2):
    radio = FakePersistentHopRadio()
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=4)
    session = radio.begin_session(plan, session_id="adapter-session")
    blocks = [session.read_visit() for _ in range(visit_count)]
    session.request_cancel()
    receipt = session.finish()
    upstream_blocks = tuple(
        SimpleNamespace(
            visit=_upstream_visit(item.evidence),
            samples=np.ascontiguousarray(item.samples.T),
        )
        for item in blocks
    )
    return plan, blocks, _UpstreamSession(upstream_blocks, _upstream_receipt(receipt))


def _upstream_visit(visit):
    invalid = visit.transition_invalid_before
    return SimpleNamespace(
        visit_index=visit.visit_index,
        sweep_index=visit.sweep_index,
        target_index=visit.target_index,
        fastlock_profile_index=visit.fastlock_profile_index,
        event_sequence=visit.event_sequence,
        device_event_id=visit.device_event_id,
        device_event_flags=visit.device_event_flags,
        fastlock_slot=visit.fastlock_slot,
        requested_center_hz=visit.requested_if_center_hz,
        actual_lo_frequency_hz=visit.actual_lo_frequency_hz,
        actual_if_offset_hz=visit.actual_if_offset_hz,
        transition_invalid_before=SimpleNamespace(
            from_profile_index=(
                0xFF if invalid.from_profile_index is None else invalid.from_profile_index
            ),
            to_profile_index=invalid.to_profile_index,
            transition_before_counter=invalid.transition_before_counter,
            transition_after_counter=invalid.transition_after_counter,
            device_sample_counter=invalid.device_sample_counter,
            device_sample_counter_end_exclusive=invalid.device_sample_counter_end_exclusive,
        ),
        valid_device_sample_counter=visit.valid_device_sample_counter,
        valid_device_sample_counter_end_exclusive=(visit.valid_device_sample_counter_end_exclusive),
        valid_sample_count=visit.valid_sample_count,
    )


def _upstream_receipt(receipt: PersistentHopSessionReceiptV1):
    status = receipt.terminal_status
    settings = receipt.restoration.original_settings
    upstream_settings = SimpleNamespace(
        center_frequency_hz=float(settings.center_frequency_hz),
        sample_rate_hz=float(settings.sample_rate_hz),
        bandwidth_hz=float(settings.bandwidth_hz),
        channels=settings.receiver_ids,
        gain_modes=tuple(settings.gain_mode.value for _ in settings.receiver_ids),
        gain_db=tuple(item.gain_db for item in settings.gains),
    )
    return SimpleNamespace(
        session_id=persistent_hop_wire_session_id(receipt.session_id),
        radio_serial="allowed-serial",
        radio_uri="ip:192.168.1.18",
        radio_id="scanner-radio",
        metadata_abi_version=3,
        stream_generation=37,
        kernel_buffers_requested=receipt.kernel_buffers_requested,
        kernel_buffers_readback=receipt.kernel_buffers_readback,
        continuity_attested=True,
        missing_sample_count=0,
        overflow_count=0,
        hop_event_sequence_gap_count=0,
        visits=tuple(_upstream_visit(item) for item in receipt.visits),
        target_coverage=tuple(
            SimpleNamespace(
                target_index=item.target_index,
                visit_count=item.visit_count,
                valid_sample_count=item.valid_sample_count,
            )
            for item in receipt.target_coverage
        ),
        capture_outcome=receipt.capture_outcome,
        transition_invalid_sample_count=receipt.transition_invalid_sample_count,
        incomplete_visit_sample_count=0,
        valid_sample_count=receipt.valid_sample_count,
        duty_denominator_sample_count=receipt.duty_denominator_sample_count,
        valid_duty_ppm=receipt.valid_duty_ppm,
        duty_target_met=receipt.duty_target_met,
        restoration=SimpleNamespace(status="restored"),
        host_lifecycle=SimpleNamespace(
            original_settings=upstream_settings,
            restored_settings=upstream_settings,
            receive_buffer_closed=True,
            fastlock_inactive=True,
        ),
        status=SimpleNamespace(
            state=_Name(status.state.upper()),
            reason=_Name(
                {
                    "complete": "PLAN_COMPLETE",
                    "client_close": "CLIENT_CLOSE",
                    "disconnect": "CLIENT_DISCONNECT",
                    "device": "DEVICE_ERROR",
                    "event_overflow": "EVENT_OVERFLOW",
                    "event_sequence": "EVENT_SEQUENCE",
                    "counter_discontinuity": "COUNTER_DISCONTINUITY",
                    "protocol": "PROTOCOL_ERROR",
                    "restore_error": "RESTORE_ERROR",
                }[status.reason]
            ),
            error_code=status.error_code,
            flags=status.flags,
            session_id=persistent_hop_wire_session_id(receipt.session_id),
            planned_dwells=status.planned_dwells,
            visits_started=status.visits_started,
            events_emitted=status.events_emitted,
            next_event_sequence=status.next_event_sequence,
            last_block_sequence=status.last_block_sequence,
            last_block_end_counter=status.last_block_end_counter,
            first_counter=status.first_counter,
            final_counter=status.final_counter,
            restore_before_counter=status.restore_before_counter,
            restore_after_counter=status.restore_after_counter,
            restored_lo_frequency_hz=status.restored_lo_frequency_hz,
            restore_error_code=status.restore_error_code,
            active_profile_index=(
                0xFF if status.active_profile_index is None else status.active_profile_index
            ),
            restored_profile_index=(
                0xFF if status.restored_profile_index is None else status.restored_profile_index
            ),
            startup_invalid_start_counter=status.startup_invalid_start_counter,
            startup_invalid_end_counter_exclusive=(status.startup_invalid_end_counter_exclusive),
            device_dropped_events=status.device_dropped_events,
        ),
    )


def test_adapter_maps_valid_visit_iq_and_terminal_receipt() -> None:
    plan, source_blocks, upstream = _cancelled_source()
    wire_id = persistent_hop_wire_session_id("adapter-session")
    client = _Client(upstream, wire_id)
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        client_factory=lambda uri, serial: client,
        plan_factory=lambda selected: selected,
        tandem_request_factory=lambda: "hold",
    )

    assert radio.open().uri == "ip:192.168.1.18"
    session = radio.begin_session(plan, session_id="adapter-session")
    mapped = [session.read_visit(), session.read_visit()]
    with pytest.raises(StopIteration):
        session.read_visit()
    receipt = session.finish()

    assert client.start_arguments == (plan, "hold")
    assert [item.evidence for item in mapped] == [item.evidence for item in source_blocks]
    np.testing.assert_array_equal(mapped[1].samples, source_blocks[1].samples)
    assert receipt.capture_outcome == "cancelled"
    assert receipt.stream_generation == "iio-0000000000000025"
    assert receipt.radio_id == "scanner-radio"
    assert receipt.valid_sample_count == sum(item.evidence.valid_sample_count for item in mapped)
    assert receipt.valid_duty_ppm == 909_090
    assert receipt.duty_target_met
    radio.close()


def test_adapter_targets_one_explicit_alternate_iiod_port() -> None:
    plan, _source_blocks, upstream = _cancelled_source(visit_count=0)
    upstream.receipt.radio_uri = "ip:192.168.1.18:30432"
    client = _Client(upstream, persistent_hop_wire_session_id("adapter-session"))
    opened: list[tuple[str, str]] = []
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        iiod_port=30_432,
        client_factory=lambda uri, serial: opened.append((uri, serial)) or client,
    )

    assert radio.open().uri == "ip:192.168.1.18:30432"
    session = radio.begin_session(plan, session_id="adapter-session")
    with pytest.raises(StopIteration):
        session.read_visit()
    assert session.finish().radio_uri == "ip:192.168.1.18:30432"
    assert opened == [("ip:192.168.1.18:30432", "allowed-serial")]
    radio.close()


def test_adapter_maps_cancel_after_next_transition_without_forging_a_visit() -> None:
    plan, source_blocks, upstream = _cancelled_source()
    source = upstream.receipt
    source.status.visits_started += 1
    source.status.events_emitted += 1
    source.status.next_event_sequence += 1
    source.status.final_counter += plan.transition_guard_samples
    source.status.restore_before_counter = source.status.final_counter
    source.status.restore_after_counter = source.status.final_counter + 1
    source.transition_invalid_sample_count += plan.transition_guard_samples
    source.duty_denominator_sample_count += plan.transition_guard_samples
    source.valid_duty_ppm = (
        source.valid_sample_count * 1_000_000 // source.duty_denominator_sample_count
    )
    source.duty_target_met = source.valid_duty_ppm >= plan.minimum_valid_duty_ppm
    wire_id = persistent_hop_wire_session_id("adapter-session")
    client = _Client(upstream, wire_id)
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        client_factory=lambda uri, serial: client,
        plan_factory=lambda selected: selected,
        tandem_request_factory=lambda: "hold",
    )

    radio.open()
    session = radio.begin_session(plan, session_id="adapter-session")
    mapped = [session.read_visit(), session.read_visit()]
    session.request_cancel()
    receipt = session.finish()

    assert [item.evidence for item in mapped] == [item.evidence for item in source_blocks]
    assert receipt.capture_outcome == "cancelled"
    assert len(receipt.visits) == 2
    assert receipt.terminal_incomplete_visit_count == 1
    assert receipt.terminal_unretained_invalid_sample_count == plan.transition_guard_samples
    assert receipt.terminal_unretained_valid_sample_count == 0
    assert receipt.duty_target_met == (receipt.valid_duty_ppm >= plan.minimum_valid_duty_ppm)
    radio.close()


def test_adapter_cancel_is_producer_owned_and_retains_current_completed_visit() -> None:
    plan, source_blocks, source = _cancelled_source(visit_count=1)
    upstream = _HeldVisitUpstream(source._blocks, source.receipt)
    client = _Client(upstream, persistent_hop_wire_session_id("adapter-session"))
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        read_ahead_visits=1,
        client_factory=lambda uri, serial: client,
        plan_factory=lambda selected: selected,
        tandem_request_factory=lambda: "hold",
    )

    radio.open()
    session = radio.begin_session(plan, session_id="adapter-session")
    assert upstream.visit_entered.wait(timeout=2)
    session.request_cancel()
    assert not upstream.cancelled
    upstream.release_visit.set()

    block = session.read_visit()
    with pytest.raises(StopIteration):
        session.read_visit()
    receipt = session.finish()

    assert block.evidence == source_blocks[0].evidence
    assert receipt.visits == (source_blocks[0].evidence,)
    assert upstream.cancelled
    assert upstream.cancel_thread_id == upstream.visit_thread_id
    assert upstream.cancel_thread_id != get_ident()
    radio.close()


def test_adapter_finish_drains_a_full_read_ahead_queue_for_recovery() -> None:
    plan, source_blocks, source = _cancelled_source(visit_count=2)
    upstream = _QueueFullUpstream(source._blocks, source.receipt)
    client = _Client(upstream, persistent_hop_wire_session_id("adapter-session"))
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        read_ahead_visits=1,
        client_factory=lambda uri, serial: client,
        plan_factory=lambda selected: selected,
        tandem_request_factory=lambda: "hold",
    )

    radio.open()
    session = radio.begin_session(plan, session_id="adapter-session")
    assert upstream.second_visit_pulled.wait(timeout=2)
    session.request_cancel()
    receipt = session.finish()

    assert receipt.visits == tuple(item.evidence for item in source_blocks)
    assert upstream.cancelled
    assert upstream.cancel_thread_id == upstream.visit_thread_id
    assert session.complete
    radio.close()


def test_adapter_propagates_producer_error_after_preserving_terminal_receipt() -> None:
    plan, source_blocks, source = _cancelled_source(visit_count=1)
    failure = _ProducerFailure("refill failed")
    upstream = _FailingUpstream(source._blocks, source.receipt, failure)
    client = _Client(upstream, persistent_hop_wire_session_id("adapter-session"))
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        read_ahead_visits=1,
        client_factory=lambda uri, serial: client,
        plan_factory=lambda selected: selected,
        tandem_request_factory=lambda: "hold",
    )

    radio.open()
    session = radio.begin_session(plan, session_id="adapter-session")
    assert session.read_visit().evidence == source_blocks[0].evidence
    with pytest.raises(_ProducerFailure, match="refill failed") as raised:
        session.read_visit()
    session.request_cancel()
    receipt = session.finish()

    assert raised.value is failure
    assert receipt.visits == (source_blocks[0].evidence,)
    assert upstream.cancelled
    assert upstream.cancel_thread_id == upstream.visit_thread_id
    radio.close()


def test_adapter_builds_the_exact_installed_ppu_plan_without_hardware() -> None:
    plan, _source_blocks, upstream = _cancelled_source(visit_count=0)
    client = _Client(upstream, persistent_hop_wire_session_id("adapter-session"))
    radio = PlutoPersistentHopRadio(
        "192.168.1.18",
        expected_serial="allowed-serial",
        radio_id="scanner-radio",
        client_factory=lambda uri, serial: client,
    )

    radio.open()
    session = radio.begin_session(plan, session_id="adapter-session")
    with pytest.raises(StopIteration):
        session.read_visit()
    session.finish()
    upstream_plan, tandem = client.start_arguments

    assert upstream_plan.sample_rate_hz == plan.sample_rate_hz
    assert upstream_plan.rf_bandwidth_hz == plan.bandwidth_hz
    assert upstream_plan.manual_gain_db == plan.gain_db
    assert [profile.target.name for profile in upstream_plan.profiles] == [
        "CH1L",
        "CH2L",
        "CH3L",
        "CH4L",
        "CH1U",
        "CH2U",
        "CH3U",
        "CH4U",
    ]
    assert tandem.mode.name == "HOLD"
    radio.close()


@pytest.mark.parametrize("host", ["localhost", "192.168.2.18", "ip:192.168.1.18"])
def test_adapter_rejects_nonliteral_or_nonlocal_lan_hosts(host: str) -> None:
    with pytest.raises(ValueError, match="192.168.1"):
        PlutoPersistentHopRadio(host, expected_serial="allowed", radio_id="scanner")


def test_adapter_hard_denies_excluded_serial() -> None:
    with pytest.raises(ValueError, match="excluded"):
        PlutoPersistentHopRadio(
            "192.168.1.18",
            expected_serial=PERSISTENT_HOP_EXCLUDED_SERIAL,
            radio_id="scanner",
        )


@pytest.mark.parametrize("port", [0, 65_536, True, "30432"])
def test_adapter_rejects_invalid_alternate_iiod_ports(port) -> None:
    with pytest.raises(ValueError, match="port"):
        PlutoPersistentHopRadio(
            "192.168.1.18",
            expected_serial="allowed",
            radio_id="scanner",
            iiod_port=port,
        )


@pytest.mark.parametrize("read_ahead", [0, 65, True, "8"])
def test_adapter_rejects_unbounded_or_invalid_read_ahead(read_ahead) -> None:
    with pytest.raises(ValueError, match="read-ahead"):
        PlutoPersistentHopRadio(
            "192.168.1.18",
            expected_serial="allowed",
            radio_id="scanner",
            read_ahead_visits=read_ahead,
        )
