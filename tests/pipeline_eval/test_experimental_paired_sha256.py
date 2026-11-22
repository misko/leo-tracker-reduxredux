import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from random import Random

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.variants.experimental.paired_sha256 import (
    PairedSha256,
    paired_decoded_hashes,
)


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("paired SHA-256 probe requires a C compiler and OpenSSL headers")
    source = (Path(__file__).resolve().parents[2]
              / "tools/pipeline_eval/variants/experimental/paired_sha256.c")
    library = tmp_path_factory.mktemp("sha-ni") / "paired.so"
    subprocess.run([compiler, "-fPIC", "-shared", "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-deprecated-declarations", source, "-o", library, "-lcrypto"], check=True)
    if not PairedSha256(library).hardware:
        pytest.skip("paired native SHA-256 requires x86 SHA-NI, SSSE3 and SSE4.1")
    return library


def compare_hashes(hashes):
    rng = Random(723)
    expected = sha256()
    lengths = (0, 64, 128, 512, 0, 55, 9, 4096, 56, 8, 63, 1, 4096, 65, 127, 1024)
    for length in (*lengths, *rng.choices(range(1, 2048), k=50)):
        # Include unaligned pointers as well as unaligned chunk state.
        window = memoryview(rng.randbytes(length + 2))[1:-1]
        assert hashes.digest() == expected.digest()
        assert hashes.window(window) == sha256(window).digest()
        expected.update(window)
    assert hashes.digest() == expected.digest()


@pytest.mark.hardware
def test_native_pair_matches_independent_hashes_at_all_window_boundaries(native):
    compare_hashes(PairedSha256(native))


def test_unavailable_library_uses_standard_hashes(tmp_path):
    hashes = PairedSha256(tmp_path / "missing.so")
    assert not hashes.hardware
    compare_hashes(hashes)


def _sealed(tmp_path):
    writer = ShortWindowWriter(tmp_path, "sealed", configuration={"window_ms": 20},
                               radio={"id": "synthetic"}, receiver_ids=(0, 1), chunk_windows=4)
    for sequence, length in enumerate((16, 24, 17, 7, 24, 16)):
        samples = np.random.default_rng(sequence).integers(-128, 129, (length, 2, 2), dtype="<i2")
        writer.append(sequence=sequence, target_id="t", samples=samples,
                      acquisition={"sample_start": 2500 * sequence}, powers=({}, {}))
    return writer.finish(stop_reason="max_visits")


def _read_events(consume):
    events = []
    try:
        for window in consume:
            assert not window.samples.flags.writeable
            events.append((window.index.model_dump(mode="json"), window.samples.tobytes()))
    except BundleCorruptionError as error:
        return events, str(error), type(error.__cause__)
    return events, None, None


@pytest.mark.hardware
@pytest.mark.parametrize("damage", [
    None, "compressed_digest", "index_digest", "skipped_window_digest", "chunk_digest",
    "index_geometry", "short_frame", "extra_decoded_bytes", "wrong_decoded_size",
])
def test_paired_reader_preserves_member_validation_and_prefix_scope(tmp_path, native, damage):
    path = _sealed(tmp_path)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][0]
    payload_path = path / chunk["payload_relative_path"]
    index_path = path / chunk["index_relative_path"]
    payload = payload_path.read_bytes()
    if damage == "compressed_digest":
        payload_path.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    elif damage == "index_digest":
        index_path.write_bytes(index_path.read_bytes().replace(b'"t"', b'"u"'))
    elif damage in ("skipped_window_digest", "index_geometry"):
        rows = [json.loads(line) for line in index_path.read_bytes().splitlines()]
        if damage == "skipped_window_digest":
            rows[3]["iq_sha256"] = "sha256:" + "0" * 64
        else:
            rows[3]["payload_offset_bytes"] += 1
        index = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index_path.write_bytes(index)
        chunk["index_bytes"], chunk["index_sha256"] = len(index), sha256_digest(index)
    elif damage == "chunk_digest":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    elif damage == "wrong_decoded_size":
        chunk["uncompressed_bytes"] += 1
    elif damage in ("short_frame", "extra_decoded_bytes"):
        decoded = zstd.ZstdDecompressor().decompress(
            payload, max_output_size=chunk["uncompressed_bytes"],
        )
        raw = decoded[:-1] if damage == "short_frame" else decoded + b"extra"
        payload = zstd.ZstdCompressor().compress(raw)
        payload_path.write_bytes(payload)
        chunk["compressed_bytes"], chunk["compressed_sha256"] = len(payload), sha256_digest(payload)
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    reader = ShortWindowReader(path)
    scope = dict(start_sequence=1, stop_sequence=2 if damage else 5)
    control = _read_events(reader.windows(**scope))
    with paired_decoded_hashes(native):
        assert _read_events(reader.windows(**scope)) == control
    if damage:
        assert control[1]
    else:
        assert [index["sequence"] for index, _ in control[0]] == [1, 2, 3, 4]
        assert control[1] is None
