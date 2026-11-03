import sys
from types import SimpleNamespace

from leo.acquisition.power_scanner_ppu import power_measurements
from tests.contracts.test_power_scanner_contracts import measurement


def test_power_port_converts_only_metadata_with_explicit_counter_and_authority(monkeypatch):
    value = measurement().model_dump()
    for key in (
        "schema_version",
        "kind",
        "sample_rate_hz",
        "counter_authority",
        "counter_identity",
        "table_sha256",
        "table_digest_authority",
        "guard_identity",
        "guard_samples",
        "adc12_qualified",
        "threshold_energy",
        "threshold_rounding_rule",
        "datapath_caps",
    ):
        value.pop(key)

    class Decoder:
        @staticmethod
        def decode(raw, *, session, generation):
            assert raw == {"record": "raw"} and (session, generation) == (1, 2)
            return SimpleNamespace(measurement=lambda: value)

    monkeypatch.setitem(
        sys.modules, "pluto_plus.standalone_power", SimpleNamespace(PowerResult=Decoder)
    )
    status = dict(
        session=1,
        generation=2,
        table_sha256="a" * 64,
        guard_samples=50000,
        adc12_qualified=True,
        threshold_energy=[1, 1],
        history=[{"record": "raw"}],
    )
    result = power_measurements(status, "history")[0]
    assert result["sample_end_exclusive"] > 1 << 32
    assert result["counter_identity"] == "prepack_preincrement_v1"
    assert result["table_digest_authority"] == "host_declared"
    assert "samples" not in result and "iq_bytes" not in result
