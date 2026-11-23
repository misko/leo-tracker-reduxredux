from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest
from leo.storage.scanner import ScannerIqStore

from reports.ALGO08.v3 import physical_stage_envelope as envelope
from reports.ALGO08.v3.signed_ingress_reuse import AcquisitionCosts


def chunk(index):
    return SimpleNamespace(index_relative_path=f"index-{index}.jsonl", index_bytes=3, index_sha256="index",
                           payload_relative_path=f"iq-{index}.zst", compressed_bytes=7, compressed_sha256="compressed",
                           uncompressed_sha256="raw")


def test_read_scope_uses_released_ports_and_discards_bytes(tmp_path, monkeypatch):
    calls = []

    def read(path, size):
        calls.append([path.name, size])
        return memoryview(bytearray(size))

    monkeypatch.setattr(ScannerIqStore, "_read_regular", staticmethod(read))
    costs = AcquisitionCosts()
    got = envelope.transfer_only({"path": str(tmp_path)}, [chunk(0), chunk(1)], 2, nullcontext, costs)
    assert calls == [["manifest.json", 2], ["index-0.jsonl", 3], ["iq-0.zst", 7],
                     ["index-1.jsonl", 3], ["iq-1.zst", 7]]
    assert got == {"read_extents": calls}
    assert costs.receipt()["calls"] == {"other_descriptors": 3, "compressed_descriptor": 2}
    assert not costs.receipt()["verified_members"]


def test_read_scope_rejects_truncated_descriptor(tmp_path, monkeypatch):
    monkeypatch.setattr(ScannerIqStore, "_read_regular", staticmethod(lambda _, size: bytes(size-1)))
    with pytest.raises(ValueError, match="incomplete original member"):
        envelope.transfer_only({"path": str(tmp_path)}, [chunk(0)], 2, nullcontext, AcquisitionCosts())


def signed_example(arm):
    request = dict(inventory_digest="original")
    probe = dict(visit_index=0, candidates=[{"signed_hz": -123}])
    metadata = [dict(probe, candidates=[])]
    expected = dict(probes=[probe], metadata=metadata, iq=["iq"], clocks=["clock"], clock_anchor="anchor")
    provenance = dict(invalid_capture=0, window_count=envelope.WINDOWS)
    authority = canonical_digest([request["inventory_digest"], expected["iq"]])
    doc = dict(source=dict(probes=[probe] if arm == "dsp" else metadata,
                           raw_recording_authority_digest=authority),
               clock_anchor=expected["clock_anchor"], delivery_clocks=expected["clocks"], provenance=provenance)
    chunks = [chunk(0), chunk(1)]
    work = dict(verified_members=[[c.index_relative_path, 3, "index"] for c in chunks],
                calls=dict(decoded_sha=130, zstd_read=130), decoded_members=["raw", "raw"])
    for i, c in enumerate(chunks):
        work["verified_members"].insert(i*2+1, [c.payload_relative_path, 7, "compressed"])
    native = dict(native_calls={"full": 32, "short_primary": 224}) if arm == "dsp" else None
    return dict(doc=doc, work=work, decoded_iq_hashes=["iq"], native=native), expected, request, chunks


@pytest.mark.parametrize("arm, factors", [("dsp", 1), ("verify", 0)])
def test_verified_scopes_require_the_same_input_but_distinct_factor_work(arm, factors):
    row, expected, request, chunks = signed_example(arm)
    envelope.verify_result(arm, row, expected, request, chunks)
    assert row["metadata_sha256"] == canonical_digest(expected["metadata"])
    assert row["factors"] == factors


@pytest.mark.parametrize("field", ["decoded_members", "verified_members"])
def test_original_window_and_member_verification_are_mandatory(field):
    row, expected, request, chunks = signed_example("verify")
    row["work"][field][-1] = "bad"
    with pytest.raises(ValueError, match="Original authenticated input"):
        envelope.verify_result("verify", row, expected, request, chunks)
