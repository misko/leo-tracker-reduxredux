from types import SimpleNamespace

import pytest

from leo.radio import scanner_iio_compat as compat


@pytest.mark.parametrize("transmit_core", [True, False])
def test_facade_uses_one_context_and_rx_init_only_without_dds(monkeypatch, transmit_core):
    events = []
    context = SimpleNamespace(find_device=lambda name: object() if transmit_core else None)

    class Ad9361:
        def __init__(self, *, uri_ctx):
            assert uri_ctx is context
            events.append("transceiver")

    class Rx:
        def __init__(self, *, uri_ctx):
            assert uri_ctx is context
            events.append("receiver")

    def verify(abi):
        assert abi == 3
        events.append("verify-runtime")

    def create(uri):
        assert uri == "ip:192.168.1.20:30432"
        events.append("context")
        return context

    modules = {
        "pluto_plus.hardware.preflight": SimpleNamespace(verify_metadata_runtime=verify),
        "adi": SimpleNamespace(ad9361=Ad9361),
        "adi.rx_tx": SimpleNamespace(rx_def=Rx),
        "iio": SimpleNamespace(Context=create),
    }
    monkeypatch.setattr(compat.importlib, "import_module", modules.__getitem__)
    device = compat.scanner_adi_module().ad9361(uri="ip:192.168.1.20:30432")
    assert events == ["verify-runtime", "context", "transceiver" if transmit_core else "receiver"]
    if not transmit_core:
        assert device.disable_dds is None


@pytest.mark.parametrize("port", [30431, 30432])
@pytest.mark.parametrize("failure", [None, "serial", "abi", "capabilities"])
def test_endpoint_retains_identity_abi_and_alternate_capability_gates(monkeypatch, port, failure):
    import pluto_plus.hardware.iio_persistent_hop as ppu
    from pluto_plus.persistent_hop import PERSISTENT_HOP_CAPABILITIES

    attrs = {"hw_serial": "serial", "iio,buffer-metadata": "3"}
    attrs.update({key: "1" for key in PERSISTENT_HOP_CAPABILITIES})
    if failure == "serial":
        attrs["hw_serial"] = "wrong"
    if failure == "abi":
        attrs["iio,buffer-metadata"] = "2"
    if failure == "capabilities":
        attrs.pop(PERSISTENT_HOP_CAPABILITIES[0])
    events = []

    class Backend:
        def __init__(self, uri, **kwargs):
            assert uri == f"ip:192.168.1.20:{port}"
            assert kwargs["expected_serial"] == "serial"
            assert callable(kwargs["adi_module"].ad9361)

        def open(self):
            events.append("open")

        def close(self):
            events.append("close")

        def context_attributes(self):
            return attrs

    monkeypatch.setattr(ppu, "IioPersistentHopBackend", Backend)
    if failure in ("serial", "abi") or (failure == "capabilities" and port == 30432):
        with pytest.raises(ValueError):
            compat.verify_endpoint("192.168.1.20", port, "serial")
    else:
        compat.verify_endpoint("192.168.1.20", port, "serial")
    assert events == ["open", "close"]


def test_child_probe_has_finite_timeout_and_rejects_unverified_output(monkeypatch):
    def run(command, **kwargs):
        assert command[1:3] == ["-m", "leo.radio.scanner_iio_probe"]
        assert kwargs["timeout"] == 3
        return SimpleNamespace(returncode=0, stdout=b"not verified")

    monkeypatch.setattr(compat.subprocess, "run", run)
    assert not compat.endpoint_probe("192.168.1.20", 30431, "serial", 3)
    with pytest.raises(ValueError):
        compat.endpoint_probe("192.168.1.20", 22, "serial", 3)


def test_adaptive_loader_keeps_extension_and_injects_receive_facade(monkeypatch):
    import pluto_plus.hardware.iio_adaptive_hop as ppu

    from leo.radio.pluto_adaptive_hop import _load_client

    extension = object()
    client = object()

    def create(uri, *, expected_serial, metadata_extension, adi_module):
        assert (uri, expected_serial) == ("ip:192.168.1.20:30432", "serial")
        assert metadata_extension is extension
        assert callable(adi_module.ad9361)
        return client

    monkeypatch.setattr(ppu, "iio_adaptive_hop_client", create)
    assert _load_client("ip:192.168.1.20:30432", "serial", metadata_extension=extension) is client
