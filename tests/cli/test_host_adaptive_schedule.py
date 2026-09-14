"""Native scheduled admission uses fake hardware and the real storage path."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest

from leo.cli.backend import CliBackendError, ScheduledAdaptiveHopRun, ScheduledScannerConfiguration
from leo.cli.composition import CompositionHooks, LocalAcquisitionBackend
from leo.cli.runner import ContinuousAcquisitionRunner
from leo.radio.host_decision_release import HostDecisionRelease
from leo.scanner.adaptive_hop_application import AdaptiveHopCaptureError
from leo.scanner.host_adaptive import HOST_ADAPTIVE_PROFILE_ID
from leo.scanner.host_adaptive_schedule import HostAdaptiveScheduledScannerIntentV4
from leo.scanner.schedule import canonical_scheduled_scanner_operation_key
from leo.scanner.single_rx import parse_scheduled_scanner_intent
from tests.cli.test_adaptive_hop_schedule import RecordingStore, ScheduledFixtureRadio
from tests.cli.test_capture_supervisor import _AdvancingCancel, _Clock, _DurableSupervisorBackend
from tests.cli.test_persistent_hop_schedule import _Lifecycle, _RecordingAuthority, _settings
from tests.scanner.host_adaptive_fixtures import decision_configuration, host_receipt
from tests.scanner.test_host_adaptive_application import HostFixtureRadio


class NativeRadio(ScheduledFixtureRadio):
    def close(self):
        super().close()
        if self.fault == "close":
            raise OSError("injected close failure")

    def begin_session(self, plan, *, session_id):
        self.events.append("radio.capture")
        return HostFixtureRadio(
            host_receipt(
                plan=plan,
                session_id=session_id,
                count=self.count,
                radio_id=self.identity.radio_id,
                radio_serial=self.identity.serial,
                radio_uri=self.identity.uri,
            ),
            fault=self.fault,
        )


def fixture(tmp_path, mode="adaptive", fault=None):
    settings = _settings(
        tmp_path,
        scanner_profile=HOST_ADAPTIVE_PROFILE_ID,
        scanner_hop_policy=mode,
        scanner_interval_seconds=600,
        scanner_adaptive_sample_rates_hz=(10_000_000,),
        scanner_host_decision_manifest_path=tmp_path / "manifest.json",
        scanner_host_decision_manifest_sha256=decision_configuration().detector_manifest_sha256,
    )
    settings.bulk_root.mkdir(exist_ok=True)
    events = []
    radio = NativeRadio(events, fault=fault)
    store = RecordingStore(settings.bulk_root, events)
    lifecycle = _Lifecycle(events)
    backend = LocalAcquisitionBackend(
        settings,
        CompositionHooks(
            host_adaptive_hop_radio_factory=lambda _: radio,
            host_decision_release_loader=lambda *_: HostDecisionRelease(
                decision_configuration(), Path("unused")
            ),
            adaptive_hop_store_factory=lambda _: store,
            persistent_hop_iiod_lifecycle_factory=lambda _: lifecycle,
        ),
    )
    backend._capture_authority = _RecordingAuthority(events)
    return backend, radio, store, events


def test_host_adaptive_queue_accepts_measured_storage_stall_capacity(tmp_path):
    backend, _radio, store, _events = fixture(tmp_path)
    try:
        settings = replace(
            backend.settings,
            scanner_persistent_queue_capacity_visits=256,
        )
        assert settings.scanner_persistent_queue_capacity_visits == 256
        with pytest.raises(ValueError, match="within 1..256"):
            replace(settings, scanner_persistent_queue_capacity_visits=257)
    finally:
        store.close()


def intent(backend, slot=datetime(2026, 9, 13, 0, 0, tzinfo=UTC)):
    return backend.scheduled_scanner_intent(
        operation_key=canonical_scheduled_scanner_operation_key(slot),
        scheduled_for=slot,
    )


@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
def test_native_capture_retries_reuse_exact_receiver_and_recording(tmp_path, mode):
    backend, radio, store, events = fixture(tmp_path, mode)
    try:
        scheduled = intent(backend)
        assert isinstance(scheduled, HostAdaptiveScheduledScannerIntentV4)
        restored = parse_scheduled_scanner_intent(scheduled.model_dump(mode="json"))
        assert restored == scheduled
        first = backend.capture_scheduled_scanner(restored, cancel=Event())
        second = backend.capture_scheduled_scanner(restored, cancel=Event())
        assert first == second and isinstance(first, ScheduledAdaptiveHopRun)
        assert radio.open_count == 1
        assert (
            first.published.manifest.receipt.plan.classification_receiver
            == scheduled.configuration.receiver_ids[0]
        )
        assert first.published.manifest.receipt.plan.geometry.sample_rate_hz == 10_000_000
        assert first.published.manifest.uncompressed_bytes == 2 * 1_200_000 * 4
        assert (
            events.index("radio.close")
            < events.index("lifecycle.exit")
            < events.index("store.publish")
        )
        assert (
            not first.capture_qualified
        )  # Bounded synthetic cancellation is not a 300s qualification.
    finally:
        store.close()


def test_restart_reproduces_rx_selection_and_mode_change_rejects_old_intent(tmp_path):
    backend, radio, store, _ = fixture(tmp_path)
    try:
        slots = [datetime(2026, 9, 13, tzinfo=UTC) + timedelta(minutes=10 * i) for i in range(20)]
        scheduled = [intent(backend, slot) for slot in slots]
        assert {item.configuration.receiver_ids for item in scheduled} == {(0,), (1,)}
        assert [intent(backend, slot) for slot in slots] == scheduled
        changed = LocalAcquisitionBackend(
            replace(backend.settings, scanner_hop_policy="shadow"), backend.hooks
        )
        with pytest.raises(CliBackendError):
            changed.capture_scheduled_scanner(scheduled[0], cancel=Event())
        assert radio.open_count == 0
    finally:
        store.close()


@pytest.mark.parametrize("fault", ["read", "close"])
def test_native_failure_keeps_evidence_without_reopening_radio(tmp_path, fault):
    backend, radio, store, events = fixture(tmp_path, fault=fault)
    try:
        scheduled = intent(backend)
        with pytest.raises(AdaptiveHopCaptureError):
            backend.capture_scheduled_scanner(scheduled, cancel=Event())
        assert "lifecycle.exit" in events
        with pytest.raises(CliBackendError, match="unpublished evidence"):
            backend.capture_scheduled_scanner(scheduled, cancel=Event())
        assert radio.open_count == 1
    finally:
        store.close()


@pytest.mark.parametrize(
    "update",
    [
        {"scanner_interval_seconds": 1200},
        {"scanner_hop_policy": "fixed"},
        {"scanner_adaptive_sample_rates_hz": (2_500_000,)},
        {"scanner_host_decision_manifest_path": None},
    ],
)
def test_native_settings_reject_incompatible_policy(tmp_path, update):
    backend, _, store, _ = fixture(tmp_path)
    try:
        with pytest.raises(ValueError):
            replace(backend.settings, **update)
    finally:
        store.close()


@pytest.mark.parametrize("previous_state", ["succeeded", "failed"])
def test_profile_switch_preserves_occupied_slot_and_queues_one_native_next_slot(
    tmp_path, previous_state
):
    native, _, store, _ = fixture(tmp_path)
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.analyzed.set()
    start = datetime(2026, 9, 13, tzinfo=UTC)
    key = canonical_scheduled_scanner_operation_key(start)
    old_payload = backend.scheduled_scanner_intent(
        operation_key=key, scheduled_for=start
    ).model_dump(mode="json")
    old = backend.enqueue_acquisition_operation(
        operation_key=key, kind="scanner_sweep", payload=old_payload, scheduled_for=start
    )
    old.state = previous_state
    clock.now = 360
    backend.scanner_schedule = lambda: ScheduledScannerConfiguration(
        interval_seconds=600,
        maximum_lateness_seconds=300,
        run_duration_seconds=300,
        requires_durable_queue=True,
    )
    backend.scheduled_scanner_intent = native.scheduled_scanner_intent
    try:
        result = ContinuousAcquisitionRunner(
            backend, clock=clock, utc_now=lambda: start + timedelta(seconds=clock.now)
        ).run(
            "test-profile",
            radio_ids=("radio-a",),
            extra_tags=(),
            interval_seconds=600,
            maximum_captures=None,
            cancel=_AdvancingCancel(clock),
            scanner_only=True,
            maximum_scanner_runs=1,
        )
        assert result.stopped_reason == "maximum_scanner_runs"
        assert backend.scanner_capture_times == [600.0]
        assert old.payload == old_payload and old.state == previous_state
        assert len(backend.operations) == 2
        new = backend.operations[1]
        assert new.operation_key == canonical_scheduled_scanner_operation_key(
            start + timedelta(minutes=10)
        )
        assert new.payload["schema_version"] == 4
        assert new.payload["operation_key"].startswith(
            new.operation_key + ":" + HOST_ADAPTIVE_PROFILE_ID
        )
    finally:
        store.close()
