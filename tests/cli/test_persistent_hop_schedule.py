from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest

from leo.cli.backend import CliBackendError, ScheduledPersistentHopRun
from leo.cli.composition import (
    CliSettings,
    CompositionHooks,
    LocalAcquisitionBackend,
    RadioConfigurationV1,
)
from leo.radio import (
    PERSISTENT_HOP_IIOD_KNOWN_HOSTS_CREDENTIAL,
    PERSISTENT_HOP_IIOD_PASSWORD_CREDENTIAL,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.storage import PersistentHopIqStore


class _ClosedSession:
    def __init__(self, plan, block, receipt) -> None:
        self.plan = plan
        self._block = block
        self._receipt = receipt
        self._read = False

    @property
    def complete(self) -> bool:
        return self._read

    def read_visit(self):
        if self._read:
            raise StopIteration
        self._read = True
        return self._block

    def request_cancel(self) -> None:
        raise AssertionError("closed fixture cannot be cancelled")

    def finish(self):
        return self._receipt


class _BoundedPersistentRadio:
    def __init__(self, events: list[str] | None = None) -> None:
        self._source = FakePersistentHopRadio(radio_id="radio-a", serial="serial-a")
        self.identity = self._source.identity
        self.open_count = 0
        self.close_count = 0
        self.events = events

    def open(self):
        if self.events is not None:
            self.events.append("radio.open")
        self.open_count += 1
        return self.identity

    def begin_session(self, plan, *, session_id: str):
        if self.events is not None:
            self.events.append("radio.capture")
        self._source.open()
        source = self._source.begin_session(plan, session_id=session_id)
        block = source.read_visit()
        source.request_cancel()
        receipt = source.finish()
        self._source.close()
        return _ClosedSession(plan, block, receipt)

    def close(self) -> None:
        if self.events is not None:
            self.events.append("radio.close")
        self.close_count += 1


class _Lifecycle:
    def __init__(
        self,
        events: list[str] | None = None,
        *,
        enter_error: Exception | None = None,
        exit_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.enter_error = enter_error
        self.exit_error = exit_error
        self.enter_count = 0
        self.exit_count = 0

    def enter_and_attest(self) -> None:
        self.enter_count += 1
        if self.events is not None:
            self.events.append("lifecycle.enter")
        if self.enter_error is not None:
            raise self.enter_error

    def exit_and_verify(self) -> None:
        self.exit_count += 1
        if self.events is not None:
            self.events.append("lifecycle.exit")
        if self.exit_error is not None:
            raise self.exit_error


class _CaptureFailureRadio(_BoundedPersistentRadio):
    def begin_session(self, plan, *, session_id: str):
        if self.events is not None:
            self.events.append("radio.capture")
        raise RuntimeError("injected capture failure")


class _RecordingWriter:
    def __init__(self, writer, events: list[str]) -> None:
        self._writer = writer
        self._events = events

    def append(self, block) -> None:
        self._writer.append(block)

    def finish(self, receipt):
        self._events.append("store.publish")
        return self._writer.finish(receipt)

    def abort(self) -> None:
        self._events.append("store.abort")
        self._writer.abort()


class _RecordingStore:
    def __init__(self, root: Path, events: list[str]) -> None:
        self._store = PersistentHopIqStore(root)
        self._events = events

    def verify(self, session_id: str):
        return self._store.verify(session_id)

    def begin_queued(self, session_id, plan, *, capacity_visits: int):
        return _RecordingWriter(
            self._store.begin_queued(
                session_id,
                plan,
                capacity_visits=capacity_visits,
            ),
            self._events,
        )


class _RecordingAuthority:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    @contextmanager
    def claim(self, *_args, **_kwargs):
        self._events.append("claim.enter")
        try:
            yield
        finally:
            self._events.append("claim.release")


def _settings(tmp_path, **updates) -> CliSettings:
    binary = tmp_path / "release/runtime/scanner-iiod/iiod"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"test ARM iiOD")
    binary.chmod(0o550)
    credentials = tmp_path / "credentials"
    credentials.mkdir(exist_ok=True)
    for name, payload in (
        (PERSISTENT_HOP_IIOD_KNOWN_HOSTS_CREDENTIAL, "test known host\n"),
        (PERSISTENT_HOP_IIOD_PASSWORD_CREDENTIAL, "test password\n"),
    ):
        path = credentials / name
        path.write_text(payload)
        path.chmod(0o400)
    values = {
        "profile_root": tmp_path / "profiles",
        "bulk_root": tmp_path / "bulk",
        "radio_backend": "pluto",
        "radios": (
            RadioConfigurationV1(
                radio_id="radio-a",
                serial="serial-a",
                host="192.168.1.18",
            ),
        ),
        "safety_reserve_bytes": 0,
        "scanner_enabled": True,
        "scanner_capture_mode": "persistent_hop",
        "scanner_radio_id": "radio-a",
        "scanner_persistent_iiod_binary_path": binary,
        "scanner_persistent_credentials_directory": credentials,
        "scanner_report_root": tmp_path / "bulk" / "scanner-reports",
    }
    values.update(updates)
    return CliSettings(**values)


def test_persistent_hop_mode_is_default_off() -> None:
    settings = CliSettings.from_environ({})

    assert settings.scanner_capture_mode == "sequential"


def test_persistent_hop_credentials_are_derived_from_fixed_systemd_names(tmp_path) -> None:
    settings = _settings(tmp_path)

    assert settings.scanner_persistent_iiod_known_hosts_path == (
        tmp_path / "credentials" / PERSISTENT_HOP_IIOD_KNOWN_HOSTS_CREDENTIAL
    )
    assert settings.scanner_persistent_iiod_password_path == (
        tmp_path / "credentials" / PERSISTENT_HOP_IIOD_PASSWORD_CREDENTIAL
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"scanner_persistent_iiod_binary_path": None}, "release-local iiOD binary"),
        ({"scanner_persistent_credentials_directory": None}, "systemd-managed SSH credentials"),
    ),
)
def test_enabled_persistent_hop_fails_closed_without_bundle_or_credentials(
    tmp_path,
    updates,
    message,
) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(tmp_path, **updates)


@pytest.mark.parametrize(
    "updates",
    [
        {"scanner_interval_seconds": 600},
        {"scanner_run_seconds": 120},
        {"scanner_dwell_ms": 100},
        {"scanner_persistent_iiod_port": 30_431},
        {
            "radios": (
                RadioConfigurationV1(
                    radio_id="radio-a",
                    serial="serial-a",
                    host="192.0.2.18",
                ),
            )
        },
    ],
)
def test_persistent_hop_mode_rejects_noncanonical_cadence_or_host(
    tmp_path,
    updates,
) -> None:
    with pytest.raises(ValueError, match="persistent hopping requires"):
        _settings(tmp_path, **updates)


def test_scheduled_persistent_hop_publishes_and_reuses_one_session(tmp_path) -> None:
    radio = _BoundedPersistentRadio()
    lifecycle = _Lifecycle()
    backend = LocalAcquisitionBackend(
        _settings(tmp_path),
        CompositionHooks(
            persistent_hop_radio_factory=lambda _configuration: radio,
            persistent_hop_iiod_lifecycle_factory=lambda _configuration: lifecycle,
        ),
    )
    scheduled_for = datetime(2026, 9, 2, 0, 20, tzinfo=UTC)
    intent = backend.scheduled_scanner_intent(
        operation_key="scheduled-scanner:20260902T002000Z",
        scheduled_for=scheduled_for,
    )

    first = backend.capture_scheduled_scanner(intent, cancel=Event())
    second = backend.capture_scheduled_scanner(intent, cancel=Event())

    assert isinstance(first, ScheduledPersistentHopRun)
    assert isinstance(second, ScheduledPersistentHopRun)
    assert first.published.manifest.plan.sample_rate_hz == 5_000_000
    assert first.published.manifest.plan.bandwidth_hz == 5_000_000
    assert first.published.manifest.plan.transition_guard_samples == 25_000
    assert first.published.manifest.receipt.capture_outcome == "cancelled"
    assert first.published.manifest.receipt.valid_sample_count == 600_000
    assert first.published.manifest.queue_telemetry is not None
    assert first.published.manifest.queue_telemetry.capacity_visits == 64
    assert second.published.manifest_sha256 == first.published.manifest_sha256
    assert (radio.open_count, radio.close_count) == (1, 1)
    assert (lifecycle.enter_count, lifecycle.exit_count) == (1, 1)


def _recording_backend(tmp_path, radio, lifecycle, events):
    configurations = []

    def lifecycle_factory(configuration):
        events.append("lifecycle.factory")
        configurations.append(configuration)
        return lifecycle

    backend = LocalAcquisitionBackend(
        _settings(tmp_path),
        CompositionHooks(
            persistent_hop_radio_factory=lambda _configuration: radio,
            persistent_hop_iiod_lifecycle_factory=lifecycle_factory,
            persistent_hop_store_factory=lambda root: _RecordingStore(root, events),
        ),
    )
    backend._capture_authority = _RecordingAuthority(events)  # type: ignore[assignment]
    scheduled_for = datetime(2026, 9, 2, 0, 20, tzinfo=UTC)
    intent = backend.scheduled_scanner_intent(
        operation_key="scheduled-scanner:20260902T002000Z",
        scheduled_for=scheduled_for,
    )
    return backend, intent, configurations


def test_lifecycle_is_attested_and_cleaned_inside_claim_before_publish(tmp_path) -> None:
    events: list[str] = []
    radio = _BoundedPersistentRadio(events)
    lifecycle = _Lifecycle(events)
    backend, intent, configurations = _recording_backend(tmp_path, radio, lifecycle, events)

    backend.capture_scheduled_scanner(intent, cancel=Event())

    assert events == [
        "claim.enter",
        "lifecycle.factory",
        "lifecycle.enter",
        "radio.open",
        "radio.capture",
        "radio.close",
        "lifecycle.exit",
        "store.publish",
        "claim.release",
    ]
    assert len(configurations) == 1
    configuration = configurations[0]
    assert configuration.host == "192.168.1.18"
    assert configuration.expected_serial == "serial-a"
    assert configuration.port == 30_432
    assert configuration.binary_path == tmp_path / "release/runtime/scanner-iiod/iiod"
    assert configuration.known_hosts_path.name == PERSISTENT_HOP_IIOD_KNOWN_HOSTS_CREDENTIAL
    assert configuration.password_path.name == PERSISTENT_HOP_IIOD_PASSWORD_CREDENTIAL


def test_lifecycle_startup_failure_relies_on_transactional_entry_and_never_captures(
    tmp_path,
) -> None:
    events: list[str] = []
    radio = _BoundedPersistentRadio(events)
    lifecycle = _Lifecycle(events, enter_error=RuntimeError("injected startup failure"))
    backend, intent, _configurations = _recording_backend(tmp_path, radio, lifecycle, events)

    with pytest.raises(RuntimeError, match="startup failure"):
        backend.capture_scheduled_scanner(intent, cancel=Event())

    assert events == [
        "claim.enter",
        "lifecycle.factory",
        "lifecycle.enter",
        "claim.release",
    ]
    assert radio.open_count == 0


def test_capture_failure_aborts_then_cleans_before_claim_release(tmp_path) -> None:
    events: list[str] = []
    radio = _CaptureFailureRadio(events)
    lifecycle = _Lifecycle(events)
    backend, intent, _configurations = _recording_backend(tmp_path, radio, lifecycle, events)

    with pytest.raises(Exception, match="injected capture failure"):
        backend.capture_scheduled_scanner(intent, cancel=Event())

    assert "store.publish" not in events
    assert events[-3:] == ["store.abort", "lifecycle.exit", "claim.release"]
    assert (radio.open_count, radio.close_count) == (1, 1)


def test_cleanup_failure_is_attempted_once_and_prevents_publish(tmp_path) -> None:
    events: list[str] = []
    radio = _BoundedPersistentRadio(events)
    lifecycle = _Lifecycle(events, exit_error=RuntimeError("injected cleanup failure"))
    backend, intent, _configurations = _recording_backend(tmp_path, radio, lifecycle, events)

    with pytest.raises(RuntimeError, match="cleanup failure"):
        backend.capture_scheduled_scanner(intent, cancel=Event())

    assert lifecycle.exit_count == 1
    assert "store.publish" not in events
    assert events[-3:] == ["lifecycle.exit", "store.abort", "claim.release"]


def test_scheduled_persistent_hop_rejects_noncanonical_slot_identity(tmp_path) -> None:
    backend = LocalAcquisitionBackend(_settings(tmp_path))
    scheduled_for = datetime(2026, 9, 2, 0, 20, tzinfo=UTC)

    with pytest.raises(CliBackendError, match="operation key disagrees"):
        backend.scheduled_scanner_intent(
            operation_key="scheduled-scanner:20260903T012000Z",
            scheduled_for=scheduled_for,
        )
