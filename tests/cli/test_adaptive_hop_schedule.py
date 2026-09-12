"""Scheduled adaptive wiring with fixture radios; never an Ethernet connection."""

from dataclasses import replace
from datetime import UTC, datetime
from threading import Event

import pytest

from leo.cli.backend import CliBackendError, ScheduledAdaptiveHopRun, ScheduledPersistentHopRun
from leo.cli.composition import CliSettings, CompositionHooks, LocalAcquisitionBackend
from leo.cli.models import ExitCode
from leo.radio.scanner_glrt_metadata import ScannerGlrtOptions
from leo.scanner.adaptive_hop_application import AdaptiveHopCaptureError
from leo.scanner.ports import ScanRadioIdentity
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_glrt import ScannerGlrtStore
from tests.cli.test_persistent_hop_schedule import (
    _BoundedPersistentRadio,
    _Lifecycle,
    _RecordingAuthority,
    _RecordingWriter,
    _settings,
)
from tests.scanner.adaptive_glrt_publication_fixtures import (
    ALGORITHM,
    CONFIGURATION,
    evidence_fixture,
)
from tests.scanner.adaptive_hop_fixtures import receipt_fixture
from tests.scanner.test_adaptive_hop_application import FixtureRadio

OPTIONS = ScannerGlrtOptions(ALGORITHM, CONFIGURATION, mode="positive-only-v1")


class ScheduledFixtureRadio:
    def __init__(self, events, *, fault=None, count=3):
        self.identity = ScanRadioIdentity("radio-a", "serial-a", "ip:192.168.1.18:30432")
        self.events = events
        self.fault = fault
        self.count = count
        self.open_count = 0
        self.classification_evidence = None
        self.classification_error = None

    def open(self):
        self.open_count += 1
        self.events.append("radio.open")
        return self.identity

    def begin_session(self, plan, *, session_id):
        self.events.append("radio.capture")
        if self.fault == "begin":
            raise RuntimeError("injected capture failure")
        receipt = receipt_fixture(
            plan=plan,
            session_id=session_id,
            count=self.count,
            radio_id=self.identity.radio_id,
            radio_serial=self.identity.serial,
            radio_uri=self.identity.uri,
        )
        self.classification_evidence = evidence_fixture(receipt)
        return FixtureRadio(receipt, fault=self.fault)

    def close(self):
        self.events.append("radio.close")


class RecordingStore(AdaptiveHopIqStore):
    def __init__(self, root, events):
        super().__init__(root)
        self.events = events

    def begin_queued(self, session_id, plan, *, capacity_visits):
        return _RecordingWriter(
            super().begin_queued(session_id, plan, capacity_visits=capacity_visits), self.events
        )


class GlrtStore:
    def __init__(self, root, events):
        self.store = ScannerGlrtStore(root)
        self.events = events

    def publish(self, publication):
        assert self.events[-1] == "claim.release"
        self.events.append("glrt.publish")
        return self.store.publish(publication)

    def read(self, session_id):
        return self.store.read(session_id)


def backend_fixture(tmp_path, *, mode="shadow", fault=None, count=3, lifecycle_failure=None):
    events = []
    settings = _settings(tmp_path, scanner_hop_policy=mode, scanner_glrt=OPTIONS)
    settings.bulk_root.mkdir(exist_ok=True)
    radio = ScheduledFixtureRadio(events, fault=fault, count=count)
    lifecycle = _Lifecycle(
        events,
        enter_error=RuntimeError("injected entry failure")
        if lifecycle_failure == "enter"
        else None,
        exit_error=RuntimeError("injected cleanup failure")
        if lifecycle_failure == "exit"
        else None,
    )
    store = RecordingStore(settings.bulk_root, events)
    backend = LocalAcquisitionBackend(
        settings,
        CompositionHooks(
            adaptive_hop_radio_factory=lambda _: radio,
            adaptive_hop_store_factory=lambda _: store,
            persistent_hop_iiod_lifecycle_factory=lambda _: lifecycle,
            scanner_glrt_store_factory=lambda root: GlrtStore(root, events),
        ),
    )
    backend._capture_authority = _RecordingAuthority(events)
    return backend, radio, lifecycle, store, events


def intent_fixture(backend, minute=20):
    return backend.scheduled_scanner_intent(
        operation_key=f"scheduled-scanner:20260902T00{minute:02}00Z",
        scheduled_for=datetime(2026, 9, 2, 0, minute, tzinfo=UTC),
    )


@pytest.mark.parametrize("diagnostic_error", [False, True])
def test_adaptive_failure_reads_diagnostics_before_cleanup(tmp_path, monkeypatch, diagnostic_error):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path, fault="read")

    def diagnostic_tail():
        events.append("lifecycle.diagnostic")
        if diagnostic_error:
            raise RuntimeError("diagnostic connection lost")
        return "missing_samples=21050"

    monkeypatch.setattr(lifecycle, "diagnostic_tail", diagnostic_tail, raising=False)
    try:
        with pytest.raises(AdaptiveHopCaptureError) as caught:
            backend.capture_scheduled_scanner(intent_fixture(backend), cancel=Event())
        assert events.index("lifecycle.diagnostic") < events.index("lifecycle.exit")
        assert events.index("lifecycle.exit") < events.index("claim.release")
        assert lifecycle.exit_count == 1
        assert "store.publish" not in events
        expected = "diagnostic connection lost" if diagnostic_error else "missing_samples=21050"
        assert expected in "\n".join(caught.value.__notes__)
    finally:
        store.close()


@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
@pytest.mark.parametrize("minute", [0, 20])
def test_scheduled_adaptive_capture_publishes_after_cleanup_and_retry_reads_only(
    tmp_path, mode, minute
):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path, mode=mode)
    intent = intent_fixture(backend, minute)
    first = backend.capture_scheduled_scanner(intent, cancel=Event())
    assert isinstance(first, ScheduledAdaptiveHopRun)
    assert events == [
        "claim.enter",
        "lifecycle.enter",
        "radio.open",
        "radio.capture",
        "radio.close",
        "lifecycle.exit",
        "store.publish",
        "claim.release",
        "glrt.publish",
    ]
    assert first.classification_warning is None
    receipt = first.published.manifest.receipt
    assert receipt.plan.policy.mode == mode
    assert receipt.plan.geometry.sample_rate_hz == intent.configuration.sample_rate_hz
    assert receipt.plan.geometry.bandwidth_hz == receipt.plan.geometry.sample_rate_hz
    assert receipt.plan.geometry.valid_visit_ms == 120
    assert receipt.plan.geometry.nominal_duration_seconds == 300
    assert receipt.plan.geometry.receiver_ids == (0, 1)
    assert receipt.plan.classification_receiver == 1
    assert first.published.manifest.queue_telemetry.capacity_visits == 64
    assert not first.capture_qualified  # cancelled short fixture, not a 300 s success
    assert store.verify(first.published.session_id) == first.published
    publication = ScannerGlrtStore(backend.settings.bulk_root).read(first.published.session_id)
    assert publication.evidence.expected_results == 3
    assert receipt.complete_visit_count == 2
    second = backend.capture_scheduled_scanner(intent, cancel=Event())
    assert second == first
    assert radio.open_count == lifecycle.enter_count == lifecycle.exit_count == 1
    store.close()


def test_shadow_retry_cannot_be_relabelled_adaptive(tmp_path):
    backend, radio, lifecycle, store, _ = backend_fixture(tmp_path)
    intent = intent_fixture(backend)
    first = backend.capture_scheduled_scanner(intent, cancel=Event())
    backend.settings = replace(backend.settings, scanner_hop_policy="adaptive")
    with pytest.raises(CliBackendError, match="disagrees with scheduled policy"):
        backend.capture_scheduled_scanner(intent, cancel=Event())
    assert store.inspect(first.published.session_id) == first.published
    assert radio.open_count == lifecycle.enter_count == 1
    store.close()


@pytest.mark.parametrize(
    "failure", ["begin", "read", "finish", "inventory", "identity", "enter", "exit"]
)
def test_failed_capture_never_publishes_or_retries_reserved_iq(tmp_path, failure):
    backend, radio, lifecycle, store, events = backend_fixture(
        tmp_path, fault=failure, lifecycle_failure=failure
    )
    intent = intent_fixture(backend)
    with pytest.raises((AdaptiveHopCaptureError, RuntimeError)):
        backend.capture_scheduled_scanner(intent, cancel=Event())
    assert store.session_ids() == ()
    assert "store.publish" not in events
    assert "glrt.publish" not in events
    assert events[-1] == "claim.release"
    assert lifecycle.exit_count == (0 if failure == "enter" else 1)
    if failure != "enter":
        with pytest.raises(CliBackendError, match="unpublished evidence"):
            backend.capture_scheduled_scanner(intent, cancel=Event())
        assert radio.open_count == 1
    store.close()


def test_adaptive_slot_cannot_be_recaptured_as_fixed_even_when_unpublished(tmp_path):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path, fault="read")
    intent = intent_fixture(backend)
    with pytest.raises(AdaptiveHopCaptureError):
        backend.capture_scheduled_scanner(intent, cancel=Event())
    backend.settings = replace(backend.settings, scanner_hop_policy="fixed")
    with pytest.raises(CliBackendError, match="different hopping recording kind"):
        backend.capture_scheduled_scanner(intent, cancel=Event())
    assert radio.open_count == lifecycle.enter_count == 1
    store.close()


def test_fixed_slot_cannot_be_recaptured_as_adaptive(tmp_path):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path)
    fixed = _BoundedPersistentRadio(events)
    backend.hooks = replace(backend.hooks, persistent_hop_radio_factory=lambda _: fixed)
    backend.settings = replace(backend.settings, scanner_hop_policy="fixed", scanner_glrt=None)
    intent = intent_fixture(backend)
    backend.capture_scheduled_scanner(intent, cancel=Event())
    backend.settings = replace(
        backend.settings, scanner_hop_policy="adaptive", scanner_glrt=OPTIONS
    )
    with pytest.raises(CliBackendError, match="different hopping recording kind"):
        backend.capture_scheduled_scanner(intent, cancel=Event())
    assert fixed.open_count == lifecycle.enter_count == 1
    assert radio.open_count == 0
    store.close()


def test_conflict_is_rechecked_after_authority_is_acquired(tmp_path):
    from contextlib import contextmanager

    from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopPolicyV1
    from leo.scanner.persistent_hop import compile_scheduled_persistent_hop_plan_v1

    backend, radio, lifecycle, store, _ = backend_fixture(tmp_path)
    intent = intent_fixture(backend)
    session_id = f"scan-hop-{intent.intent_digest.removeprefix('sha256:')[:16]}"
    plan = AdaptiveHopPlanV1(
        geometry=compile_scheduled_persistent_hop_plan_v1(intent),
        policy=AdaptiveHopPolicyV1(mode="shadow", generation=7),
    )

    class RacingAuthority:
        @contextmanager
        def claim(self, *args, **kwargs):
            writer = store.begin(session_id, plan)
            writer.abort()
            yield

    backend._capture_authority = RacingAuthority()
    with pytest.raises(CliBackendError, match="unpublished evidence"):
        backend.capture_scheduled_scanner(intent, cancel=Event())
    assert radio.open_count == lifecycle.enter_count == 0
    store.close()


def test_storage_admission_failure_does_not_enter_radio(tmp_path, monkeypatch):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path)

    def reject(_):
        raise CliBackendError("no space", ExitCode.ADMISSION_REJECTED)

    monkeypatch.setattr(backend, "_admit_persistent_hop_iq", reject)
    with pytest.raises(CliBackendError, match="no space"):
        backend.capture_scheduled_scanner(intent_fixture(backend), cancel=Event())
    assert events == []
    assert radio.open_count == lifecycle.enter_count == 0
    store.close()


def test_pre_cancel_does_not_enter_radio_lifecycle(tmp_path):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path)
    cancel = Event()
    cancel.set()
    with pytest.raises(CliBackendError, match="cancelled before radio setup"):
        backend.capture_scheduled_scanner(intent_fixture(backend), cancel=cancel)
    assert events == []
    assert radio.open_count == lifecycle.enter_count == 0
    assert store.session_ids() == ()
    store.close()


def test_radio_factory_cannot_change_the_admitted_identity(tmp_path):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path)
    radio.identity = ScanRadioIdentity("another-radio", "serial-a", "ip:192.168.1.18:30432")
    with pytest.raises(CliBackendError, match="physical identity"):
        backend.capture_scheduled_scanner(intent_fixture(backend), cancel=Event())
    assert events == []
    assert radio.open_count == lifecycle.enter_count == 0
    store.close()


def test_advisory_publication_failure_preserves_iq_and_retry_does_not_recapture(tmp_path):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path)

    def fail(_):
        raise OSError("classifier disk unavailable")

    backend.hooks = replace(backend.hooks, scanner_glrt_store_factory=fail)
    intent = intent_fixture(backend)
    result = backend.capture_scheduled_scanner(intent, cancel=Event())
    assert "classifier disk unavailable" in result.classification_warning
    assert store.verify(result.published.session_id) == result.published
    retry = backend.capture_scheduled_scanner(intent, cancel=Event())
    assert "classifier disk unavailable" in retry.classification_warning
    assert retry.published == result.published
    assert radio.open_count == lifecycle.enter_count == 1
    store.close()


@pytest.mark.parametrize(
    "update",
    [
        {"scanner_hop_policy": "random"},
        {"scanner_hop_policy": True},
        {"scanner_enabled": False},
        {"scanner_capture_mode": "sequential"},
        {"scanner_glrt": None},
        {"scanner_glrt": replace(OPTIONS, mode="unqualified-evidence")},
    ],
)
def test_opt_in_configuration_is_strict(tmp_path, update):
    settings = _settings(tmp_path, scanner_glrt=OPTIONS, scanner_hop_policy="shadow")
    with pytest.raises(ValueError):
        replace(settings, **update)


def test_default_off_and_exact_options_reach_concrete_adapter(tmp_path, monkeypatch):
    assert CliSettings.from_environ({}).scanner_hop_policy == "fixed"
    with pytest.raises(CliBackendError):
        CliSettings.from_environ({"LEO_SCANNER_HOP_POLICY": "shadow"})
    settings = _settings(tmp_path, scanner_glrt=OPTIONS, scanner_hop_policy="shadow")
    calls = []
    monkeypatch.setattr(
        "leo.cli.composition.PlutoAdaptiveHopRadio", lambda *a, **k: calls.append((a, k))
    )
    LocalAcquisitionBackend(settings)._adaptive_hop_radio(settings.radios[0])
    assert calls == [
        (
            ("192.168.1.18",),
            dict(
                expected_serial="serial-a",
                radio_id="radio-a",
                scanner_glrt=OPTIONS,
                iiod_port=30432,
                read_ahead_visits=8,
            ),
        )
    ]


@pytest.mark.parametrize("minute,adaptive", [(0, True), (20, False)])
def test_rate_allowlist_preserves_geometry_and_selects_qualified_policy(tmp_path, minute, adaptive):
    backend, radio, lifecycle, store, events = backend_fixture(tmp_path, mode="adaptive")
    original_intent = intent_fixture(backend, minute)
    backend.settings = replace(backend.settings, scanner_adaptive_sample_rates_hz=(2_500_000,))
    fixed_radio = _BoundedPersistentRadio(events)
    backend.hooks = replace(backend.hooks, persistent_hop_radio_factory=lambda _: fixed_radio)
    intent = intent_fixture(backend, minute)
    assert intent == original_intent  # No change to cadence, rate, RF bandwidth or dwell.
    result = backend.capture_scheduled_scanner(intent, cancel=Event())
    assert isinstance(result, ScheduledAdaptiveHopRun if adaptive else ScheduledPersistentHopRun)
    assert radio.open_count == int(adaptive)
    assert fixed_radio.open_count == int(not adaptive)
    assert backend.capture_scheduled_scanner(intent, cancel=Event()) == result
    assert lifecycle.enter_count == 1
    if adaptive:
        backend.settings = replace(backend.settings, scanner_adaptive_sample_rates_hz=(5_000_000,))
        with pytest.raises(CliBackendError, match="different hopping recording kind"):
            backend.capture_scheduled_scanner(intent, cancel=Event())
        assert radio.open_count == 1
    store.close()


@pytest.mark.parametrize(
    "rates", [(), (True,), (2_500_000.0,), (1,), (2_500_000,) * 2, [2_500_000]]
)
def test_rate_allowlist_rejects_invalid_runtime_values(tmp_path, rates):
    with pytest.raises(ValueError, match="adaptive sample rates"):
        replace(_settings(tmp_path), scanner_adaptive_sample_rates_hz=rates)


def test_rate_allowlist_environment_is_strict_and_defaults_preserve_both_rates():
    assert CliSettings.from_environ({}).scanner_adaptive_sample_rates_hz == (2_500_000, 5_000_000)
    assert CliSettings.from_environ(
        {"LEO_SCANNER_ADAPTIVE_SAMPLE_RATES_HZ": "2500000"}
    ).scanner_adaptive_sample_rates_hz == (2_500_000,)
    for value in ("", "2500000,", "2500000,2500000", "2500000.0", "true", "1000000"):
        with pytest.raises(CliBackendError):
            CliSettings.from_environ({"LEO_SCANNER_ADAPTIVE_SAMPLE_RATES_HZ": value})
