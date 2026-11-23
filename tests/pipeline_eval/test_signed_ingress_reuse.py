import json

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.signed_ingress_reuse import AcquisitionCosts, CompressedSlots, measured_ingress
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer


def test_two_live_views_force_owned_fallback_and_release_allows_reuse():
    pool = CompressedSlots(64)
    first = pool.empty(16, np.uint8)
    first[:] = 3
    readonly = memoryview(first).toreadonly()[2:10]
    descendant = np.frombuffer(readonly, dtype=np.uint8)[::2]
    address = first.ctypes.data
    del first, readonly
    second = pool.empty(64, np.uint8)
    second[:] = 9
    fallback = pool.empty(32, np.uint8)
    fallback[:] = 7
    assert not descendant.flags.writeable
    assert np.all(descendant == 3) and np.all(second == 9)
    assert pool.counts == {"allocation": 2, "fallback": 1}
    del descendant
    resumed = pool.empty(64, np.uint8)
    assert resumed.ctypes.data == address
    assert pool.counts["reuse"] == 1
    assert np.all(second == 9) and np.all(fallback == 7)


def test_large_compressed_input_is_independently_owned():
    pool = CompressedSlots(64)
    buffer = pool.empty(65, np.uint8)
    assert len(buffer) == 65 and buffer.flags.owndata
    assert pool.counts == {"fallback": 1}


@pytest.fixture
def sealed(tmp_path):
    writer = ShortWindowWriter(tmp_path, "signed", configuration={"window_ms": 20},
                               radio={"id": "synthetic"}, receiver_ids=(0, 1), chunk_windows=2)
    for i in range(6):
        writer.append(sequence=i, target_id="t", samples=np.full((24, 2, 2), i, dtype="<i2"),
                      acquisition={}, powers=({}, {}))
    return writer.finish(stop_reason="max_visits")


def observed(path):
    rows = []
    try:
        for window in ShortWindowReader(path).windows(stop_sequence=5):
            rows.append((window.index, window.samples.tobytes()))
    except BundleCorruptionError as error:
        return rows, str(error), type(error.__cause__)
    return rows, None, None


@pytest.mark.parametrize("damage", (None, "compressed", "index", "decoded_window", "decoded_member"))
def test_exact_window_output_and_independent_integrity_rejections(sealed, damage):
    manifest_file = sealed / "manifest.json"
    manifest = json.loads(manifest_file.read_bytes())
    chunk = manifest["chunks"][2]
    if damage == "compressed":
        payload = sealed / chunk["payload_relative_path"]
        payload.write_bytes(payload.read_bytes()[:-1])
    elif damage in ("index", "decoded_window"):
        index = sealed / chunk["index_relative_path"]
        rows = [json.loads(line) for line in index.read_bytes().splitlines()]
        rows[-1]["iq_sha256"] = "sha256:" + "0" * 64
        data = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index.write_bytes(data)
        if damage == "decoded_window":
            chunk["index_sha256"] = sha256_digest(data)
    elif damage == "decoded_member":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    manifest_file.write_bytes(canonical_json_bytes(manifest))

    with compressed_input_buffer():
        reference = observed(sealed)
    costs = AcquisitionCosts()
    pool = CompressedSlots(4096)
    with measured_ingress(compressed_input_buffer, costs, pool):
        assert observed(sealed) == reference
    if damage is None:
        assert reference[1] is None and len(reference[0]) == 5
        assert len(costs.members) == 6 and costs.calls["compressed_descriptor"] == 3
        assert pool.counts == {"allocation": 2, "reuse": 1}
    else:
        assert reference[1]
