from collections import Counter
import json

import numpy as np
import pytest
import zstandard

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.fused_window_ring import Ring, ring_windows
from reports.ALGO08.v3.fused_window_ring_trial import build
from reports.ALGO08.v3.sparse_cold_input import PAYLOAD
from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes


pytestmark = pytest.mark.hardware  # Installed Gauss libzstd and packed SHA library.


@pytest.fixture(scope="module")
def ring(tmp_path_factory):
    library = tmp_path_factory.mktemp("decoder-ring") / "ring.so"
    build(library)
    return Ring(library)


@pytest.fixture
def sealed(tmp_path):
    writer = ShortWindowWriter(tmp_path, "ring", configuration={"window_ms": 20},
                               radio={"id": "test"}, receiver_ids=(0, 1), chunk_windows=22)
    # Each repeat is far enough to span three real Zstandard blocks. A varying
    # signed row size exercises the carry when a window ends inside a block.
    tile = np.random.default_rng(21).bytes(384 * 1024)
    signal = tile * 18
    sizes = [180_000 + 8*i for i in range(22)]
    offset = 0
    for visit, size in enumerate(sizes):
        values = np.frombuffer(signal[offset:offset+size], dtype="<i2").reshape(-1, 2, 2)
        writer.append(sequence=visit, target_id="t", samples=values, acquisition={}, powers=({}, {}))
        offset += size
    return writer.finish(stop_reason="max_visits"), signal[:offset]


def observe(path):
    rows = []
    try:
        for row in ShortWindowReader(path).windows():
            rows.append(row)
    except BundleCorruptionError as error:
        return rows, str(error)
    return rows, None


@pytest.mark.parametrize("change", (None, "window", "member", "many_frames", "history"))
def test_wrap_with_remaining_history_and_retained_views(sealed, ring, change):
    path, signal = sealed
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk, = manifest["chunks"]
    payload = path / chunk["payload_relative_path"]
    parameters = zstandard.ZstdCompressionParameters.from_level(
        3, window_log=24 if change == "history" else 19, write_content_size=False, write_checksum=True)
    with payload.open("wb") as out:
        with zstandard.ZstdCompressor(compression_params=parameters).stream_writer(out, closefd=False) as encoder:
            encoder.write(signal)
        if change == "many_frames":
            out.write(zstandard.ZstdCompressor().compress(b""))
    compressed = payload.read_bytes()
    if change not in ("history", "many_frames"):
        assert zstandard.get_frame_parameters(compressed).window_size == 512 * 1024
        assert len(compressed) < len(signal) / 5
    chunk.update(compressed_bytes=len(compressed), compressed_sha256=sha256_digest(compressed))
    if change == "window":
        index = path / chunk["index_relative_path"]
        rows = [json.loads(line) for line in index.read_bytes().splitlines()]
        rows[11]["iq_sha256"] = "sha256:" + "0"*64
        data = b"".join(canonical_json_bytes(row)+b"\n" for row in rows)
        index.write_bytes(data)
        chunk.update(index_bytes=len(data), index_sha256=sha256_digest(data))
    elif change == "member":
        chunk["uncompressed_sha256"] = "sha256:" + "0"*64
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    paired = PAYLOAD / "paired-sha256.so"
    with paired_decoded_hashes(paired):
        stock, stock_error = observe(path)
    stats = Counter()
    with ring_windows(ring, paired, stats):
        candidate, candidate_error = observe(path)
    assert stock_error == candidate_error
    assert bool(stock_error) == (change in {"window", "member"})
    for a, b in zip(stock, candidate, strict=True):
        assert a.index == b.index and not b.samples.flags.writeable
        np.testing.assert_array_equal(a.samples, b.samples)
    if change in ("many_frames", "history"):
        assert stats == {"fallbacks": 1}
    elif change != "window":
        assert stats["ring_bytes"] < 1024 * 1024
        assert stats["copied_bytes"] == len(signal) and stats["wraps"] >= 4
