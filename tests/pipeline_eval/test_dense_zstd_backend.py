"""Exercise the Zstandard bridge with the host libzstd runtime and CPython."""

from collections import Counter
import json

import numpy as np
import pytest
import zstandard

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.dense_zstd_backend import Backend, StreamBridge, timed_decoder
from reports.ALGO08.v3.signed_ingress_reuse import AcquisitionCosts
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer


@pytest.fixture(scope="module")
def system():
    return Backend.system("libzstd.so.1")


def outcome(opener, compressed):
    results = []
    try:
        with opener(compressed) as reader:
            for size in (0, 56, 81, 8192, 56, 1):
                results.append(reader.read(size))
    except zstandard.ZstdError:
        return results, zstandard.ZstdError
    return results, None


@pytest.mark.parametrize("layout", ("standard", "multi", "empty", "incomplete", "corrupt", "trailing"))
def test_read_sizes_layout_fallback_and_original_decoder_errors(system, layout):
    frame = zstandard.ZstdCompressor(write_checksum=True).compress(bytes(range(256)) * 5)
    compressed = {
        "standard": frame, "multi": frame + frame, "empty": b"", "incomplete": frame[:-3],
        "corrupt": frame[:-1] + bytes([frame[-1] ^ 128]), "trailing": frame + b"junk",
    }[layout]
    records = Counter()
    candidate = StreamBridge(system, zstandard, records)
    assert outcome(candidate.stream_reader, compressed) == outcome(zstandard.ZstdDecompressor().stream_reader, compressed)
    if layout in ("standard", "corrupt"):
        assert records["standard_frames"] == 1 and records["steps"]
        assert records["error_fallbacks"] == (layout == "corrupt")
    else:
        assert records["layout_fallbacks"] == 1


def observed(path):
    rows = []
    try:
        for result in ShortWindowReader(path).windows(stop_sequence=3):
            rows.append((result.index, result.samples.tobytes()))
    except BundleCorruptionError as error:
        return rows, str(error)
    return rows, None


@pytest.mark.parametrize("damage", (None, "compressed", "index", "window", "member"))
def test_signed_digest_levels_and_window_bytes_are_unchanged(system, tmp_path, damage):
    writer = ShortWindowWriter(tmp_path, "sealed", configuration={"window_ms": 20},
                               radio={"id": "test"}, receiver_ids=(0, 1), chunk_windows=2)
    for i in range(4):
        writer.append(sequence=i, target_id="carrier", samples=np.full((60, 2, 2), i, dtype="<i2"),
                      acquisition={}, powers=({}, {}))
    sealed = writer.finish(stop_reason="max_visits")
    manifest_path = sealed / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][-1]
    if damage == "compressed":
        payload = sealed / chunk["payload_relative_path"]
        payload.write_bytes(payload.read_bytes()[:-1])
    elif damage in ("index", "window"):
        index = sealed / chunk["index_relative_path"]
        rows = [json.loads(line) for line in index.read_bytes().splitlines()]
        rows[-1]["iq_sha256"] = "sha256:" + "0" * 64
        contents = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index.write_bytes(contents)
        if damage == "window":
            chunk["index_sha256"] = sha256_digest(contents)
    elif damage == "member":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    with compressed_input_buffer():
        expected = observed(sealed)
    calls = Counter()
    with timed_decoder(compressed_input_buffer, AcquisitionCosts(), system, calls):
        assert observed(sealed) == expected
    assert bool(expected[1]) == (damage is not None)
    assert calls["standard_frames"] == (1 if damage in ("compressed", "index") else 2)
