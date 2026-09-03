from __future__ import annotations

from datetime import UTC, datetime
from threading import Event

import pytest

from leo.cli.backend import ScheduledPersistentHopRun
from leo.cli.composition import (
    CliSettings,
    CompositionHooks,
    LocalAcquisitionBackend,
    RadioConfigurationV1,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio


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
    def __init__(self) -> None:
        self._source = FakePersistentHopRadio(radio_id="radio-a", serial="serial-a")
        self.identity = self._source.identity
        self.open_count = 0
        self.close_count = 0

    def open(self):
        self.open_count += 1
        return self.identity

    def begin_session(self, plan, *, session_id: str):
        self._source.open()
        source = self._source.begin_session(plan, session_id=session_id)
        block = source.read_visit()
        source.request_cancel()
        receipt = source.finish()
        self._source.close()
        return _ClosedSession(plan, block, receipt)

    def close(self) -> None:
        self.close_count += 1


def _settings(tmp_path, **updates) -> CliSettings:
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
        "scanner_report_root": tmp_path / "bulk" / "scanner-reports",
    }
    values.update(updates)
    return CliSettings(**values)


def test_persistent_hop_mode_is_default_off() -> None:
    settings = CliSettings.from_environ({})

    assert settings.scanner_capture_mode == "sequential"


@pytest.mark.parametrize(
    "updates",
    [
        {"scanner_interval_seconds": 600},
        {"scanner_run_seconds": 120},
        {"scanner_dwell_ms": 100},
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
    backend = LocalAcquisitionBackend(
        _settings(tmp_path),
        CompositionHooks(persistent_hop_radio_factory=lambda _configuration: radio),
    )
    scheduled_for = datetime(2026, 9, 2, 0, 20, tzinfo=UTC)
    intent = backend.scheduled_scanner_intent(
        operation_key="scheduled-scanner:20260903T012000Z",
        scheduled_for=scheduled_for,
    )

    first = backend.capture_scheduled_scanner(intent, cancel=Event())
    second = backend.capture_scheduled_scanner(intent, cancel=Event())

    assert isinstance(first, ScheduledPersistentHopRun)
    assert isinstance(second, ScheduledPersistentHopRun)
    assert first.published.manifest.plan.sample_rate_hz == 5_000_000
    assert first.published.manifest.plan.bandwidth_hz == 5_000_000
    assert first.published.manifest.receipt.capture_outcome == "cancelled"
    assert first.published.manifest.receipt.valid_sample_count == 600_000
    assert first.published.manifest.queue_telemetry is not None
    assert second.published.manifest_sha256 == first.published.manifest_sha256
    assert (radio.open_count, radio.close_count) == (1, 1)
