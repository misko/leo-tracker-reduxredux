from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.radio.persistent_hop_iiod_lifecycle import (
    PersistentHopIiodLifecycleConfiguration,
)
from leo.radio.pluto_userspace_iiod_lifecycle import (
    PlutoUserspaceIiodLifecycleError,
    create_pluto_userspace_iiod_lifecycle,
)


def _configuration(tmp_path: Path) -> PersistentHopIiodLifecycleConfiguration:
    binary = tmp_path / "release/runtime/scanner-iiod/iiod"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"exact ARM iiOD payload")
    binary.chmod(0o550)
    return PersistentHopIiodLifecycleConfiguration(
        radio_id="radio-a",
        expected_serial="serial-a",
        host="192.168.1.20",
        port=30_432,
        binary_path=binary,
        known_hosts_path=tmp_path / "credentials/known-hosts",
        password_path=tmp_path / "credentials/password",
    )


def test_default_adapter_lazily_constructs_exact_ppu_deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class Deployment:
        def __init__(self, **kwargs) -> None:
            events.append(("construct", kwargs))

        def enter_and_attest(self) -> None:
            events.append("enter")

        def exit_and_verify(self) -> None:
            events.append("exit")

    monkeypatch.setattr(
        "leo.radio.pluto_userspace_iiod_lifecycle.importlib.import_module",
        lambda name: (
            events.append(("import", name)) or SimpleNamespace(UserspaceIiodDeployment=Deployment)
        ),
    )
    configuration = _configuration(tmp_path)

    lifecycle = create_pluto_userspace_iiod_lifecycle(configuration)

    assert events[0] == ("import", "pluto_plus.userspace_iiod")
    constructor = events[1]
    assert isinstance(constructor, tuple)
    arguments = constructor[1]
    assert arguments["host"] == "192.168.1.20"
    assert arguments["expected_serial"] == "serial-a"
    assert arguments["binary_path"] == configuration.binary_path
    assert arguments["known_hosts_path"] == configuration.known_hosts_path
    assert arguments["password_path"] == configuration.password_path
    lifecycle.enter_and_attest()
    lifecycle.exit_and_verify()

    assert events[-2:] == ["enter", "exit"]


def test_default_adapter_fails_closed_when_installed_ppu_lacks_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_name: str):
        raise ImportError("not installed")

    monkeypatch.setattr(
        "leo.radio.pluto_userspace_iiod_lifecycle.importlib.import_module",
        unavailable,
    )

    with pytest.raises(PlutoUserspaceIiodLifecycleError, match="lacks"):
        create_pluto_userspace_iiod_lifecycle(_configuration(tmp_path))


def test_default_adapter_delegates_binary_validation_to_ppu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Deployment:
        def __init__(self, **kwargs) -> None:
            if not kwargs["binary_path"].stat().st_mode & 0o100:
                raise ValueError("binary rejected by PPU")

    monkeypatch.setattr(
        "leo.radio.pluto_userspace_iiod_lifecycle.importlib.import_module",
        lambda _name: SimpleNamespace(UserspaceIiodDeployment=Deployment),
    )
    configuration = _configuration(tmp_path)
    configuration.binary_path.chmod(0o440)
    with pytest.raises(ValueError, match="rejected by PPU"):
        create_pluto_userspace_iiod_lifecycle(configuration)
