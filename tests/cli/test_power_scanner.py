from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from leo.cli.power_scanner import control_power, start_power
from leo.storage.power_scanner import read_power_checkpoint


@pytest.fixture
def public_power_ports(monkeypatch, tmp_path):
    events = []
    status = {
        "schema": "leo.power-scanner.status.v1",
        "session": 1,
        "generation": 2,
        "latest": [],
        "history": [],
        "device_terminal": False,
        "device_restored": False,
        "cursor_lost": 0,
        "next_cursor": 0,
        "table_sha256": "a" * 64,
        "guard_samples": 50000,
        "adc12_qualified": False,
        "threshold_energy": [1, 1],
    }

    @dataclass
    class Target:
        profile: int
        frequency_hz: int
        profile_crc32: int

    fixture_targets = tuple(
        Target(index, 1800000000 + index * 10000000, index + 1) for index in range(8)
    )
    status["table_sha256"] = hashlib.sha256(
        "".join(
            f"{target.profile} {target.frequency_hz} {target.profile_crc32}\n"
            for target in fixture_targets
        ).encode("ascii")
    ).hexdigest()

    @dataclass
    class Request:
        session: int = 1
        generation: int = 2
        targets: tuple = fixture_targets
        guard_samples: int = 50000
        adc12_qualified: bool = False
        threshold_energy: tuple = (1, 1)

    @dataclass
    class Restoration:
        observed_kernel_buffers: int = 4
        fastlock_inactive: bool = True

    class Client:
        def __init__(self, *_):
            pass

        def status(self, session, generation, cursor):
            events.append(("status", cursor))
            return status

    class Owner:
        @staticmethod
        def start(uri, serial, setup, **options):
            request = Request(setup.session, setup.generation)
            options["on_prepared"]({"original": "settings"}, request)
            checkpoint = read_power_checkpoint(tmp_path, "run")
            assert checkpoint.state == "prepared" and checkpoint.preparation == {
                "snapshot": "owned"
            }
            events.append("START after durable snapshot")
            status.update(session=setup.session, generation=setup.generation)
            return SimpleNamespace(status=status)

    def drained(*_, **__):
        events.append("device release attested")
        return status | {"device_terminal": True, "device_restored": True}

    def restore(value):
        assert value == {"snapshot": "owned"}
        events.append("host restore")
        return Restoration()

    standalone = SimpleNamespace(
        StandalonePowerClient=Client, threshold_energy=lambda _: 1, PowerResult=object
    )
    owner = SimpleNamespace(
        StandalonePowerRadioOwner=Owner,
        preparation_snapshot=lambda _: {"snapshot": "owned"},
        preparation_from_snapshot=lambda value: value,
        stop_and_drain=drained,
    )
    monkeypatch.setitem(
        sys.modules,
        "pluto_plus.continuous_scan",
        SimpleNamespace(build_continuous_setup=lambda **options: SimpleNamespace(**options)),
    )
    monkeypatch.setitem(sys.modules, "pluto_plus.standalone_power", standalone)
    monkeypatch.setitem(sys.modules, "pluto_plus.standalone_power_radio", owner)
    monkeypatch.setitem(
        sys.modules,
        "pluto_plus.adaptive_scan_radio",
        SimpleNamespace(restore_adaptive_scan_radio=restore),
    )
    return events, owner


def test_power_prepare_persist_detached_status_stop_restore_and_idempotence(
    tmp_path, public_power_ports
):
    events, _ = public_power_ports
    result = start_power(
        root=tmp_path,
        host="fixture",
        serial="serial",
        run_id="run",
        frequencies_hz=tuple(1800000000 + index * 10000000 for index in range(8)),
    )
    assert result["state"] == "running"
    assert events == ["START after durable snapshot"]
    latest = control_power(tmp_path, "run", after_cursor=123)
    assert latest["history"] == [] and events[-1] == ("status", 123)
    final = control_power(tmp_path, "run", stop=True)
    assert final["state"] == "stopped" and final["host_restoration"]["fastlock_inactive"]
    assert events[-2:] == ["device release attested", "host restore"]
    assert control_power(tmp_path, "run", stop=True) == final
    assert {path.name for path in (tmp_path / "run").iterdir()} == {"power.json", "control.lock"}


def test_power_failed_device_release_keeps_recovery_snapshot_without_host_restore(
    tmp_path, public_power_ports
):
    events, owner = public_power_ports
    start_power(
        root=tmp_path,
        host="fixture",
        serial="serial",
        run_id="run",
        frequencies_hz=tuple(1800000000 + index * 10000000 for index in range(8)),
    )

    def failed(*_, **__):
        raise RuntimeError("device restoration unattested")

    owner.stop_and_drain = failed
    with pytest.raises(RuntimeError, match="unattested"):
        control_power(tmp_path, "run", stop=True)
    checkpoint = read_power_checkpoint(tmp_path, "run")
    assert checkpoint.state == "recovery_required" and checkpoint.host_restoration is None
    assert "host restore" not in events


def test_power_dry_run_never_creates_checkpoint_or_acquires(public_power_ports, tmp_path):
    events, _ = public_power_ports
    result = start_power(
        root=tmp_path / "absent",
        host="fixture",
        serial="serial",
        run_id="run",
        frequencies_hz=tuple(1800000000 + index * 10000000 for index in range(8)),
        dry_run=True,
    )
    assert result["iq_dma"] is False and events == []
    assert not (tmp_path / "absent").exists()
