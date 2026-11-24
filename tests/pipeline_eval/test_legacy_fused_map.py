import json

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3 import legacy_block_multi as multi
from reports.ALGO08.v3 import legacy_block_seek as core
from reports.ALGO08.v3 import legacy_fused_map as fused


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    binary = tmp_path_factory.mktemp("history") / "history.so"
    fused.build(binary)
    return fused.load(binary)


def capture(tmp_path, *, fault=None, literal_only=False):
    # Distances cross bounded ring wraps, and sample windows cross block ends.
    rng = np.random.default_rng(71)
    raw = rng.integers(-4096, 4096, size=655_360, dtype="<i2").reshape(-1, 2, 2)
    data = raw.reshape(-1).view(np.uint8)
    if not literal_only:
        for start in (131_072, 393_216, 917_504):
            data[start+4096:start+12_288] = data[start+64:start+8256].copy()
            data[start+32_000:start+48_000] = data[start-16_000:start]
    windows = [raw[first:first+35_000] for first in range(0, len(raw), 35_000)]
    writer = ShortWindowWriter(
        tmp_path, "capture", configuration={"sample_rate_hz": 10_000_000, "window_ms": 20},
        radio={}, receiver_ids=(0, 1), schema_version=2, chunk_windows=len(windows), compression_level=1,
    )
    for index, values in enumerate(windows):
        writer.append(sequence=index, target_id="test", samples=values,
                      acquisition={"chronology": index}, powers=({}, {}))
    path = writer.finish(stop_reason="test")
    parameters = zstd.ZstdCompressionParameters.from_level(
        1, strategy=zstd.STRATEGY_GREEDY, hash_log=16, chain_log=16, min_match=7,
        window_log=17, write_checksum=True, write_content_size=False)
    if fault == "window":
        data[-123] ^= 1
    frame = bytearray(zstd.ZstdCompressor(compression_params=parameters).compress(data))
    if fault == "checksum":
        frame[-1] ^= 1
    manifest = path / "manifest.json"
    document = json.loads(manifest.read_bytes())
    chunk, = document["chunks"]
    (path / chunk["payload_relative_path"]).write_bytes(frame)
    chunk.update(compressed_bytes=len(frame), compressed_sha256=sha256_digest(frame))
    if fault == "member":
        chunk["uncompressed_sha256"] = sha256_digest(b"different complete member")
    manifest.write_bytes(canonical_json_bytes(document))
    original = ShortWindowReader(path)
    return original, original.manifest.chunks[0], bytes(frame), windows


def test_fused_ring_matches_independent_history_and_existing_map(tmp_path, native):
    reader, chunk, frame, expected = capture(tmp_path)
    output = tmp_path / "map.bin"
    baseline = tuple(reader.windows())

    def consume(visits):
        seen = []
        for view, stock, supplied in zip(visits, baseline, expected, strict=True):
            assert view.index == stock.index
            np.testing.assert_array_equal(view.samples, supplied)
            seen.append(view.index.iq_sha256)
        return seen

    result, timing = fused.analyze_and_seal(reader, chunk, native, None, consume, output)
    assert result == [view.index.iq_sha256 for view in baseline]
    assert timing["history_and_context_bytes"] < chunk.uncompressed_bytes
    assert len(timing["exceptional_ordinals"]) >= 2
    separate = multi.seal(reader, chunk, frame, baseline)
    assert output.read_bytes() == separate
    assert timing["map_sha256"] == sha256_digest(separate)


@pytest.mark.parametrize("fault, expected", [
    ("checksum", "EOF, checksum"), ("window", "differs from its index digest"),
    ("member", "differs from its manifest digest"),
])
def test_reject_bad_original_semantics_before_publication(tmp_path, native, fault, expected):
    reader, chunk, _, windows = capture(tmp_path, fault=fault)
    path = tmp_path / "map.bin"
    seen = []

    def drain(rows):
        for row in rows:
            seen.append(row.index.sequence)

    with pytest.raises(core.MapError, match=expected):
        fused.analyze_and_seal(reader, chunk, native, None, drain, path)
    assert seen == list(range(len(windows) - (fault == "window")))
    assert not path.exists()


def test_drain_and_detector_success_are_both_required_to_seal(tmp_path, native):
    reader, chunk, _, _ = capture(tmp_path)
    path = tmp_path / "map.bin"
    with pytest.raises(core.MapError, match="before clean original EOF"):
        fused.analyze_and_seal(reader, chunk, native, None, next, path)

    def fail_after_eof(rows):
        for _ in rows:
            pass
        raise RuntimeError("detector could not finish")

    with pytest.raises(RuntimeError, match="detector could not finish"):
        fused.analyze_and_seal(reader, chunk, native, None, fail_after_eof, path)
    assert not path.exists()


def test_authentic_literal_layout_falls_back_to_complete_stock(tmp_path, native):
    reader, chunk, _, expected = capture(tmp_path, literal_only=True)
    path = tmp_path / "map.bin"
    result, metrics = fused.analyze_and_seal(reader, chunk, native, None, tuple, path)
    assert len(result) == len(expected)
    assert "literal-only" in metrics["fallback"]
    assert not path.exists()


@pytest.mark.parametrize("literal", [False, True])
def test_first_use_map_reopens_from_the_same_verified_encoded_snapshot(tmp_path, native, literal):
    from reports.ALGO08.v3 import legacy_first_map_input as first

    reader, chunk, _, _ = capture(tmp_path, literal_only=literal)
    library = tmp_path / "replay.so"
    core.build(library)
    active = core.load(library)
    member = fused.FusedMember(reader, chunk, native, None, allow_literal=True)
    try:
        assert sum(window.samples.nbytes for window in member.windows()) == chunk.uncompressed_bytes
        raw, pin = member.sidecar()
        assert bool(member.exceptions) != literal
        result = first.reopen(member, {"map_sha256": pin}, raw, core if literal else multi, active)
        assert result["original_encoded_reused"] == chunk.compressed_bytes
        assert result["prefix_bytes"] == member.rows[0].payload_bytes
        assert result["prefix_sha256"] == member.prefixes[0]
        plan = {"members": [{"map": "member.json", "map_sha256": pin}]}
        assert first.publish_bundle(tmp_path / "maps", plan, {"member.json": raw}) == sha256_digest(
            (tmp_path / "maps/custody.json").read_bytes())
        assert (tmp_path / "maps/member.json").read_bytes() == raw
        with pytest.raises(BundleCorruptionError, match="Map changed"):
            first.publish_bundle(tmp_path / "damaged", plan, {"member.json": raw + b" "})
        assert not (tmp_path / "damaged").exists()
    finally:
        member.close()
