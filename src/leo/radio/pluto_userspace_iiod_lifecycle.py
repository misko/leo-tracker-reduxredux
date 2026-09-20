"""Lazy adapter from Leo's acquisition lifecycle port to Pluto+ utilities."""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from leo.radio.persistent_hop_iiod_lifecycle import (
    PersistentHopIiodLifecycle,
    PersistentHopIiodLifecycleConfiguration,
)


class PlutoUserspaceIiodLifecycleError(RuntimeError):
    """The concrete no-flash lifecycle dependency could not be used safely."""


def _firmware_compatible_endpoint_probe(
    host: str,
    port: int,
    expected_serial: str,
    timeout_s: float,
    *,
    persistent_probe: Callable[[str, int, str, float], bool],
) -> bool:
    """Attest v0.53 stock iiOD without assuming its expanded scan-channel inventory."""

    if port != 30_431:
        return persistent_probe(host, port, expected_serial, timeout_s)
    iio_info = Path(sys.executable).with_name("iio_info")
    try:
        completed = subprocess.run(  # noqa: S603
            (str(iio_info), "-u", f"ip:{host}:{port}"),
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0 or len(completed.stdout) > 4 * 1024 * 1024:
        return False
    fields = {}
    for raw_line in completed.stdout.decode(errors="replace").splitlines():
        line = raw_line.strip()
        if ": " in line:
            key, value = line.split(": ", 1)
            if key in ("hw_serial", "iio,buffer-metadata"):
                fields[key] = value
    return fields == {"hw_serial": expected_serial, "iio,buffer-metadata": "3"}


def create_pluto_userspace_iiod_lifecycle(
    configuration: PersistentHopIiodLifecycleConfiguration,
) -> PersistentHopIiodLifecycle:
    """Build the production provider without importing PPU at CLI import time."""

    if configuration.port != 30_432:
        raise ValueError("userspace iiOD lifecycle requires alternate port 30432")
    try:
        module = importlib.import_module("pluto_plus.userspace_iiod")
        deployment_type = module.UserspaceIiodDeployment
        persistent_probe = module.persistent_hop_endpoint_probe
    except (AttributeError, ImportError) as error:
        raise PlutoUserspaceIiodLifecycleError(
            "installed pluto-plus-utils lacks the userspace iiOD deployment"
        ) from error
    companion_options = (
        {"bundle_manifest_path": configuration.bundle_manifest_path}
        if configuration.bundle_manifest_path is not None
        else {}
    )
    return deployment_type(
        host=configuration.host,
        expected_serial=configuration.expected_serial,
        binary_path=configuration.binary_path,
        known_hosts_path=configuration.known_hosts_path,
        password_path=configuration.password_path,
        serial_probe=lambda host, port, serial, timeout: _firmware_compatible_endpoint_probe(
            host,
            port,
            serial,
            timeout,
            persistent_probe=persistent_probe,
        ),
        **companion_options,
    )
