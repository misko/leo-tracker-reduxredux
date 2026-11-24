import json

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3 import legacy_block_multi as trial, legacy_block_seek as core


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    library = tmp_path_factory.mktemp("block-multi") / "seek.so"
    core.build(library)
    return core.load(library), trial.load_history()


def distinct_history_blocks():
    rng = np.random.default_rng(534)
    values = [rng.integers(-4096, 4096, size=count, dtype="<i2").tobytes()
              for count in (20_000, 28_596, 43_008)]
    values[0] = values[0][:1_000] + values[0][100:814] + values[0][1_714:]
    values[1] = values[1][:1_100] + values[0][2_500:3_900] + values[1][2_500:]
    values[2] = values[2][:2_500] + values[1][4_000:4_600] + values[2][3_100:]
    compressor = zstd.ZstdCompressor(write_checksum=True, write_content_size=False).compressobj()
    encoded = [compressor.compress(block) + compressor.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK) for block in values[:-1]]
    encoded.append(compressor.compress(values[-1]) + compressor.flush())
    return b"".join(encoded), values


def test_native_boundaries_recover_several_nonmaximal_blocks_with_real_history(native):
    _, history = native
    frame, blocks = distinct_history_blocks()
    expected = b"".join(blocks)
    description, ordinals, owner = trial.describe(frame, len(expected))
    assert ordinals == (0, 1, 2) and owner is None
    assert [entry[4] for entry in description] == [1, 1, 1]
    returned, mapped = trial.decode_boundaries(history, frame, len(expected), description)
    assert returned == expected
    assert [row[3] for row in mapped] == [40_000, 57_192, 86_016]
    assert [row[2] for row in mapped] == [0, 40_000, 97_192]
    corrupt = frame[:-1] + bytes([frame[-1] ^ 1])
    with pytest.raises(core.MapError, match="checksum"):
        trial.decode_boundaries(history, corrupt, len(expected), description)


def test_visits_cross_distinct_exception_blocks_with_exact_full_and_prefix_attestation(tmp_path, native, monkeypatch):
    library, history = native
    frame, blocks = distinct_history_blocks()
    raw = b"".join(blocks)
    writer = ShortWindowWriter(tmp_path, "fixture", configuration={"sample_rate_hz": 10_000_000, "window_ms": 20},
        radio={}, receiver_ids=(0, 1), schema_version=2, chunk_windows=3)
    for i, (begin, stop) in enumerate(((0, 28_000), (28_000, 116_000), (116_000, len(raw)))):
        values = np.frombuffer(raw[begin:stop], dtype="<i2").reshape(-1, 2, 2)
        writer.append(sequence=i, target_id="test", samples=values, acquisition={}, powers=({}, {}))
    path = writer.finish(stop_reason="test")
    manifest = path / "manifest.json"
    body = json.loads(manifest.read_bytes())
    chunk, = body["chunks"]
    (path / chunk["payload_relative_path"]).write_bytes(frame)
    chunk.update(compressed_bytes=len(frame), compressed_sha256=sha256_digest(frame))
    manifest.write_bytes(canonical_json_bytes(body))
    reader = ShortWindowReader(path)
    chunk, = reader.manifest.chunks
    windows = tuple(reader.windows())
    monkeypatch.setattr(trial, "PREFIX", 24_000)
    side = trial.seal(reader, chunk, frame, windows, history=history)
    pin = sha256_digest(side)
    assert trial.open_optional(reader, chunk, None, None, library) is None
    with pytest.raises(core.MapError, match="externally pinned"):
        trial.open_optional(reader, chunk, side+b"!", pin, library)
    selected = trial.open_optional(reader, chunk, side, pin, library)
    try:
        mid = selected.read(selected.rows[1], full=True)
        np.testing.assert_array_equal(mid, windows[1].samples)
        assert selected.requests["exception_spans"] == 3
        later = selected.read(selected.rows[2], full=False)
        assert later.tobytes() == windows[2].samples[:3_000].tobytes()
        assert not later.flags.writeable
        assert selected.counts.requested_blocks == 0
    finally:
        selected.close()
    with pytest.raises(core.MapError, match="tainted"):
        selected.read(selected.rows[1], full=True)


def test_seal_validates_every_declared_block_and_partition():
    rows = [(9, 30, 0, 16, 1, 28), (42, 30, 0, 16, 0, 29), (75, 30, 2, 16, 1, 28)]
    exceptional = bytes(range(20))
    header = {"blocks": [[9, 30, 0, 20, 0], [42, 30, 20, 16, 0], [75, 30, 36, 20, 2]],
              "exceptions": [[0, sha256_digest(exceptional)], [2, sha256_digest(exceptional)]]}
    blocks, exceptions = trial.bind_map(header, memoryview(exceptional*2), rows, (0, 2), 56)
    assert blocks == header["blocks"] and [(start, end) for start, end, _ in exceptions] == [(0, 20), (36, 56)]
    header["blocks"][1][3] += 1
    with pytest.raises(core.MapError, match="decoded extent"):
        trial.bind_map(header, memoryview(exceptional*2), rows, (0, 2), 56)
