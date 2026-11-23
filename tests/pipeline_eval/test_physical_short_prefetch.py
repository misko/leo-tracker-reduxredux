from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import physical_short_prefetch as trial


def test_acquisition_threshold_uses_decimal_bytes_and_full_elapsed_scope():
    compressed, decoded = 154_722_097, 204_800_000
    boundary = 618_888_388
    result = trial.measured_rate(compressed, decoded, boundary)
    assert result["compressed_mb_s"] == pytest.approx(250.0)
    assert result["decoded_mb_s"] == pytest.approx(330.91685, rel=1e-5)
    assert result["reaches_250_mb_s"]
    assert not trial.measured_rate(compressed, decoded, boundary+1)["reaches_250_mb_s"]


def test_prefetch_must_supply_the_original_full_member(monkeypatch):
    def verify(arm, reduced, base, request, chunks):
        assert arm == "dsp"
        reduced.update(dict(raw_authority="sha", metadata_sha256="metadata", probe_sha256="probes", factors=2, probes=256))

    monkeypatch.setattr(trial.physical, "verify_result", verify)
    row = dict(ingress="prefetch", decoded_iq_hashes=[], worker_cpus=[2], checked=dict(calls={"compressed_descriptor": 1}),
               native=dict(native_calls={"full": 32, "short_primary": 224}),
               overlap=dict(submitted=1, hits=1, fallback=0, hit_bytes=17))
    chunks = [SimpleNamespace(compressed_bytes=17)]
    assert trial.validate(row, {}, {}, chunks, {})["factors"] == 2
    for key, value in (("hits", 0), ("hit_bytes", 16), ("fallback", 1)):
        changed = row | {"overlap": row["overlap"] | {key: value}}
        with pytest.raises(ValueError, match="full original member"):
            trial.validate(changed, {}, {}, chunks, {})


def test_release_advice_still_uses_both_demand_descriptor_reads(monkeypatch):
    monkeypatch.setattr(trial.physical, "verify_result", lambda *args: None)
    row = dict(ingress="advice", decoded_iq_hashes=[], checked=dict(calls={"compressed_descriptor": 1}),
               native=dict(native_calls={"full": 32, "short_primary": 224}), overlap=dict(submitted=1))
    with pytest.raises(ValueError, match="Descriptor or receiver schedule"):
        trial.validate(row, {}, {}, (), {})
