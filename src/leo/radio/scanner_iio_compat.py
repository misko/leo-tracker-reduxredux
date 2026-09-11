"""Receive-only pyadi facade and bounded scanner endpoint identity probes."""

from __future__ import annotations

import importlib
import subprocess
import sys
from types import SimpleNamespace


def scanner_adi_module() -> SimpleNamespace:
    # PPU's public injection port keeps this optional hardware dependency lazy.
    return SimpleNamespace(ad9361=_ad9361)


def _ad9361(*, uri: str):
    preflight = importlib.import_module("pluto_plus.hardware.preflight")
    preflight.verify_metadata_runtime(3)
    adi = importlib.import_module("adi")
    iio = importlib.import_module("iio")
    context = iio.Context(uri)
    if context.find_device("cf-ad9361-dds-core-lpc") is not None:
        return adi.ad9361(uri_ctx=context)
    rx_def = importlib.import_module("adi.rx_tx").rx_def

    def initialize(receiver):
        rx_def.__init__(receiver, uri_ctx=context)

    # No DDS device exists in this context. PHY TX attenuation and all other
    # PPU receive/identity/restoration checks still run unchanged.
    facade = type("ReceiveOnlyAd9361", (adi.ad9361,), {"__init__": initialize, "disable_dds": None})
    return facade()


def endpoint_probe(host: str, port: int, expected_serial: str, timeout_s: float) -> bool:
    if port not in (30431, 30432) or not 0 < timeout_s <= 60:
        raise ValueError("scanner endpoint probe requires a reviewed port and timeout")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "leo.radio.scanner_iio_probe", host, str(port), expected_serial],
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout == b"scanner-endpoint-verified\n"


def verify_endpoint(host: str, port: int, expected_serial: str) -> None:
    from pluto_plus.hardware.iio_persistent_hop import IioPersistentHopBackend
    from pluto_plus.persistent_hop import (
        PERSISTENT_HOP_CAPABILITIES,
        PERSISTENT_HOP_METADATA_ABI,
    )

    if port not in (30431, 30432):
        raise ValueError("unsupported scanner endpoint port")
    backend = IioPersistentHopBackend(
        f"ip:{host}:{port}", expected_serial=expected_serial, adi_module=scanner_adi_module()
    )
    try:
        backend.open()
        attributes = backend.context_attributes()
        if attributes.get("hw_serial") != expected_serial:
            raise ValueError("scanner endpoint serial differs")
        if attributes.get("iio,buffer-metadata") != PERSISTENT_HOP_METADATA_ABI:
            raise ValueError("scanner endpoint requires exact metadata ABI 3")
        if port == 30432 and any(
            attributes.get(capability) != "1" for capability in PERSISTENT_HOP_CAPABILITIES
        ):
            raise ValueError("scanner endpoint lacks persistent-hop capabilities")
    finally:
        backend.close()
