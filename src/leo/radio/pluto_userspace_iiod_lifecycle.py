"""Lazy adapter from Leo's acquisition lifecycle port to Pluto+ utilities."""

from __future__ import annotations

import importlib

from leo.radio.persistent_hop_iiod_lifecycle import (
    PersistentHopIiodLifecycle,
    PersistentHopIiodLifecycleConfiguration,
)
from leo.radio.scanner_iio_compat import endpoint_probe


class PlutoUserspaceIiodLifecycleError(RuntimeError):
    """The concrete no-flash lifecycle dependency could not be used safely."""


def create_pluto_userspace_iiod_lifecycle(
    configuration: PersistentHopIiodLifecycleConfiguration,
) -> PersistentHopIiodLifecycle:
    """Build the production provider without importing PPU at CLI import time."""

    if configuration.port != 30_432:
        raise ValueError("userspace iiOD lifecycle requires alternate port 30432")
    try:
        module = importlib.import_module("pluto_plus.userspace_iiod")
        deployment_type = module.UserspaceIiodDeployment
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
        serial_probe=endpoint_probe,
        **companion_options,
    )
