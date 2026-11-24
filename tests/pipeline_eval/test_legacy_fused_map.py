import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3 import legacy_block_multi as multi
from reports.ALGO08.v3 import legacy_block_seek as core
from reports.ALGO08.v3 import legacy_fused_map as fused
from reports.ALGO08.v3 import legacy_block_input as port
from reports.ALGO08.v3 import legacy_first_map_input as first


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    binary = tmp_path_factory.mktemp("history") / "history.so"
    fused.build(binary)
    return fused.load(binary)


def capture(tmp_path, *, fault=None, literal_only=False, empty_tail=False):
    # Distances cross bounded ring wraps, and sample windows cross block ends.
    rng = np.random.default_rng(71)
    raw = rng.integers(-4096, 4096, size=655_360, dtype="<i2").reshape(-1, 2, 2)
    data = raw.reshape(-1).view(np.uint8)
    if not literal_only:
        for start in (131_072, 393_216, 917_504):
            data[start+4096:start+12_288] = data[start+64:start+8256].copy()
            data[start+32_000:start+48_000] = data[start-16_000:start]
    windows = [raw[first:first+35_000] for first in range(0, len(raw), 35_000)]
    if empty_tail:
        windows.append(raw[:0])
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


def test_first_use_literal_map_preserves_partial_and_zero_visit(tmp_path, native):
    reader, chunk, frame, samples = capture(tmp_path, literal_only=True, empty_tail=True)
    expected = list(reader.windows())
    assert 0 < expected[-2].samples.shape[0] < expected[0].samples.shape[0]
    assert expected[-1].samples.shape == (0, 2, 2)
    control, control_pin, _ = core.seal_map(reader, chunk, frame, expected)
    library = tmp_path/"replay.so"
    core.build(library)
    member = fused.FusedMember(reader, chunk, native, None, allow_literal=True)
    try:
        for row, wanted in zip(member.windows(), samples, strict=True):
            np.testing.assert_array_equal(row.samples, wanted)
        document, pin = member.sidecar()
        assert (document, pin) == (control, control_pin)
        replay = core.Selective(reader, chunk, document, pin, core.load(library))
        try:
            for index in (-2, -1):
                np.testing.assert_array_equal(replay.read(replay.rows[index], full=False), samples[index][:80_000])
        finally:
            replay.close()
    finally:
        member.close()


@pytest.mark.parametrize("decision", ["complete", "withheld"])
def test_verified_terminal_issuance_accepts_both_normal_outcomes(decision):
    from reports.ALGO08.v3.legacy_first_map_entry import require_verified_terminal

    terminal = dict(decision=decision, session_id="session", window_count=29)
    plan = dict(session="session", windows=29, raw_authority="verified original")
    audit = dict(finished_raw_authority="verified original")
    require_verified_terminal(terminal, plan, audit)
    with pytest.raises(ValueError, match="No complete first-use"):
        require_verified_terminal(terminal, plan, {})
    with pytest.raises(ValueError, match="No complete first-use"):
        require_verified_terminal(terminal | {"window_count": 28}, plan, audit)


def unsupported_capture(path, *, bad_checksum=False):
    writer = ShortWindowWriter(
        path, "unsupported", configuration={"sample_rate_hz": 10_000_000, "window_ms": 20},
        radio={}, receiver_ids=(0, 1), schema_version=2, chunk_windows=2, compression_level=1,
    )
    for seq, count in enumerate((0, 17_777)):
        writer.append(sequence=seq, target_id="test", samples=np.zeros((count, 2, 2), dtype="<i2"),
                      acquisition={"chronology": seq}, powers=({}, {}))
    folder = writer.finish(stop_reason="test")
    if bad_checksum:
        manifest = folder / "manifest.json"
        record = json.loads(manifest.read_bytes())
        chunk, = record["chunks"]
        payload = folder / chunk["payload_relative_path"]
        frame = bytearray(payload.read_bytes())
        frame[-1] ^= 1
        payload.write_bytes(frame)
        chunk["compressed_sha256"] = sha256_digest(frame)
        manifest.write_bytes(canonical_json_bytes(record))
    return ShortWindowReader(folder)


def acquire_without_preparing_maps(readers, history, replay, pending, audit, *, expected=None):
    class Source:
        def __init__(self, entry):
            self.reader = ShortWindowReader(Path(entry["path"]))
            self.start_sequence = 0
            self.stop_sequence = self.reader.manifest.window_count
            self.targets = {"test": {"target_id": "test"}}

        def windows(self):
            raise AssertionError("Expected the real first-use source binding")

    inventory = dict(
        segments=[dict(path=str(reader.path), windows=reader.manifest.window_count,
                       manifest_digest=reader.manifest_sha256) for reader in readers],
        window_count=sum(reader.manifest.window_count for reader in readers))
    pin = canonical_digest(inventory)

    def staged(_sources, detector=None):
        def acquire(_session, digest, actual, _assets):
            hashes = []
            for entry in actual["segments"]:
                for visit in Source(entry).windows():
                    assert sha256_digest(memoryview(visit.samples.reshape(-1)).cast("B")) == visit.iq_sha256
                    hashes.append(visit.iq_sha256)
            return dict(source=dict(raw_recording_authority_digest=port.raw_authority(digest, hashes)))

        return SimpleNamespace(FastSegmentSource=Source, acquire=acquire)

    boot = SimpleNamespace(staged_scanner=staged)
    with first.binding(boot, expected, history, None, replay, pending, audit):
        scan = boot.staged_scanner({}, detector=True)
        scan.acquire("fresh", pin, inventory, None)
    return inventory, pin


def test_discover_literal_exception_and_ordinary_custody_without_a_prior_map(tmp_path, native):
    literal, _, _, _ = capture(tmp_path / "literal", literal_only=True)
    stock = unsupported_capture(tmp_path / "stock")
    exception, _, _, _ = capture(tmp_path / "exception")
    binary = tmp_path / "selective.so"
    core.build(binary)
    replay = core.load(binary)
    pending, audit, encoded_reads = {}, {}, []
    storage_read = ShortWindowReader._member

    def count(reader, name, size, pin):
        if name.endswith(".zst"):
            encoded_reads.append(reader.path)
        return storage_read(reader, name, size, pin)

    readers = (literal, stock, exception)
    with patch.object(ShortWindowReader, "_member", count):
        inventory, pin = acquire_without_preparing_maps(readers, native, replay, pending, audit)
    assert encoded_reads == [reader.path for reader in readers]
    plan = audit["verified_plan"]
    assert [row["map_kind"] for row in plan["members"]] == ["literal", "ordinary", "exception"]
    assert list(pending) == ["member-000000.json", "member-000002.json"]
    assert audit["members"][1]["fallback"]
    output = tmp_path / "maps"
    assert first.publish_bundle(output, plan, pending) == sha256_digest((output / "custody.json").read_bytes())
    parts = port.all_parts(json.loads((output / "custody.json").read_bytes()), "fresh", pin, inventory)
    for reader in readers:
        chunk, = reader.manifest.chunks
        member = parts[(reader.manifest_sha256, chunk.chunk_index)]
        if member["map"] is None:
            assert [window.samples.shape[0] for window in reader.windows()] == [0, 17_777]
            continue
        codec = core if member["map_kind"] == "literal" else multi
        selected = codec.Selective(reader, chunk, (output / member["map"]).read_bytes(),
                                   member["map_sha256"], replay)
        try:
            for row, original in zip(selected.rows, reader.windows(), strict=True):
                np.testing.assert_array_equal(selected.read(row, full=False), original.samples[:80_000])
        finally:
            selected.close()
    again, compared = {}, {}
    acquire_without_preparing_maps(readers, native, replay, again, compared, expected=plan)
    assert compared["verified_plan"] == plan and pending == again


@pytest.mark.parametrize("fault", ["encoded", "unsupported-checksum"])
def test_later_corruption_clears_provisional_maps_and_cannot_publish(tmp_path, native, fault):
    valid, _, _, _ = capture(tmp_path / "valid", literal_only=True)
    if fault == "encoded":
        broken, chunk, frame, _ = capture(tmp_path / "broken")
        modified = bytearray(frame)
        modified[-1] ^= 1
        (broken.path / chunk.payload_relative_path).write_bytes(modified)
    else:
        broken = unsupported_capture(tmp_path / "broken", bad_checksum=True)
    binary = tmp_path / "selective.so"
    core.build(binary)
    pending, audit = {}, {}
    with pytest.raises(BundleCorruptionError):
        acquire_without_preparing_maps((valid, broken), native, core.load(binary), pending, audit)
    assert not pending and not audit["members"] and "verified_plan" not in audit
    assert not (tmp_path / "maps").exists()
