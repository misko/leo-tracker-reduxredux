import json

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3 import legacy_block_seek as trial


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    path = tmp_path_factory.mktemp("zstd-block") / "test.so"
    trial.build(path)
    return trial.load(path)


def original(tmp_path, *, matches=False):
    writer = ShortWindowWriter(
        tmp_path, "capture", configuration={"sample_rate_hz": 10_000_000, "window_ms": 20},
        radio={}, receiver_ids=(0, 1), schema_version=2, chunk_windows=12, compression_level=1,
    )
    rng = np.random.default_rng(501)
    shape = (12, 16_384, 2, 2)
    data = (np.zeros(shape, dtype="<i2") if matches
            else rng.integers(-4096, 4096, size=shape, dtype="<i2"))
    for seq, samples in enumerate(data):
        writer.append(sequence=seq, target_id="test", samples=samples,
                      acquisition={"chronology": seq}, powers=({}, {}))
    path = writer.finish(stop_reason="test")
    if not matches:
        # A long min_match makes this deterministic synthetic case literal-only.
        # The released reader independently verifies its full frame afterwards.
        options = zstd.ZstdCompressionParameters.from_level(
            1, min_match=7, write_checksum=True, write_content_size=False)
        frame = zstd.ZstdCompressor(compression_params=options).compress(data.reshape(-1))
        manifest = path / "manifest.json"
        document = json.loads(manifest.read_bytes())
        chunk, = document["chunks"]
        (path / chunk["payload_relative_path"]).write_bytes(frame)
        chunk.update(compressed_bytes=len(frame), compressed_sha256=sha256_digest(frame))
        manifest.write_bytes(canonical_json_bytes(document))
    reader = ShortWindowReader(path)
    chunk, = reader.manifest.chunks
    frame = (path / chunk.payload_relative_path).read_bytes()
    windows = tuple(reader.windows())
    assert len(windows) == len(data)
    return reader, chunk, frame, windows


def test_sparse_treeless_block_replays_only_the_required_origin(tmp_path, native):
    reader, chunk, frame, windows = original(tmp_path)
    table, pin, _ = trial.seal_map(reader, chunk, frame, windows)
    blocks = json.loads(table)["blocks"]
    assert len(blocks) == len(windows)
    seek = next(i for i, row in enumerate(blocks) if row[4] < i)
    selected = trial.Selective(reader, chunk, table, pin, native)
    try:
        got = selected.read(selected.rows[seek], full=False)
        np.testing.assert_array_equal(got, windows[seek].samples)
        assert selected.counts.requested_blocks == 1
        assert selected.counts.dependency_blocks == 1
        assert not got.flags.writeable
    finally:
        selected.close()


def test_decline_matches_and_authenticate_original_before_any_decode(tmp_path, native):
    reader, chunk, frame, _ = original(tmp_path, matches=True)
    with pytest.raises(trial.UnsupportedLayout, match="zero matches"):
        trial.block_map(frame, chunk.uncompressed_bytes)
    assert trial.open_source(reader, chunk, None, None, native) is None
    assert len(tuple(reader.windows())) == 12


def test_map_and_member_mutations_fail_under_original_pins(tmp_path, native):
    reader, chunk, frame, windows = original(tmp_path)
    table, pin, _ = trial.seal_map(reader, chunk, frame, windows)
    with pytest.raises(trial.MapError, match="independently pinned"):
        trial.Selective(reader, chunk, table + b" ", pin, native)
    document = json.loads(table)
    document["blocks"][1][1] += 1
    counterfeit = canonical_json_bytes(document)
    with pytest.raises(trial.MapError, match="block structure"):
        trial.Selective(reader, chunk, counterfeit, sha256_digest(counterfeit), native)
    data = bytearray(frame)
    data[-8] ^= 1
    (reader.path / chunk.payload_relative_path).write_bytes(data)
    with pytest.raises(BundleCorruptionError, match="short-window member changed"):
        trial.Selective(reader, chunk, table, pin, native)
    with pytest.raises(BundleCorruptionError, match="short-window member changed"):
        next(reader.windows())


def test_provisional_decode_only_retries_unsupported_layout(monkeypatch):
    attempts = []

    def attempt(mode, *_, **__):
        attempts.append(mode)
        if mode == "selective":
            raise trial.UnsupportedLayout("compressed match")
        return {"actual_reader": mode}, "fresh stock evidence", None, []

    monkeypatch.setattr(trial, "measure_attempt", attempt)
    timing, proof, _, _ = trial.measure("selective", None, None, b"map", "pin", None, [])
    assert attempts == ["selective", "stock"]
    assert timing["actual_reader"] == "stock" and proof == "fresh stock evidence"
    assert "fallback_including_declined_work" in timing

    def wrong_pin(*_, **__):
        raise trial.MapError("wrong pin")

    monkeypatch.setattr(trial, "measure_attempt", wrong_pin)
    with pytest.raises(trial.MapError, match="wrong pin"):
        trial.measure("selective", None, None, b"map", "pin", None, [])
