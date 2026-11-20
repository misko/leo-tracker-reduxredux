import json
from collections import Counter

import numpy as np
import pytest

from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.qualification.raw_stream_reader import READ_BYTES, streamed_windows


@pytest.fixture
def sealed_short_windows(tmp_path):
    writer = ShortWindowWriter(
        tmp_path,
        "sealed",
        configuration=dict(sample_rate_hz=10_000_000, window_ms=20),
        radio={},
        receiver_ids=(0, 1),
        chunk_windows=3,
        schema_version=2,
    )
    rng = np.random.default_rng(831)
    for seq, size in enumerate((30_000, 0, 200_000, 17)):
        writer.append(
            sequence=seq,
            target_id="fixture",
            samples=rng.integers(-32_000, 32_000, size=(size, 2, 2), dtype="<i2"),
            acquisition={"complete": size == 200_000},
            powers=({}, {}),
        )
    return writer.finish(stop_reason="finished")


def test_bound_reader_matches_all_stock_windows_including_empty_capture(sealed_short_windows):
    source = ShortWindowReader(sealed_short_windows)
    stats = Counter()
    actual = list(streamed_windows(source, stats))
    expected = list(source.windows())
    for row, archived in zip(actual, expected, strict=True):
        assert row.index == archived.index
        assert not row.samples.flags.writeable and row.samples.flags.c_contiguous
        np.testing.assert_array_equal(row.samples, archived.samples)
    assert stats["decoded_bytes"] == sum(row.samples.nbytes for row in expected)
    assert stats["compressed_bytes"] == sum(c.compressed_bytes for c in source.manifest.chunks)
    assert stats["decoded_visits"] == len(expected) == 4
    assert stats["largest_read_bytes"] == READ_BYTES < stats["largest_compressed_member_bytes"]


def test_partial_selection_still_verifies_entire_overlapping_compressed_member(
    sealed_short_windows,
):
    source = ShortWindowReader(sealed_short_windows)
    stats = Counter()
    selected = list(streamed_windows(source, stats, start_sequence=2, stop_sequence=3))
    assert [row.index.sequence for row in selected] == [2]
    assert stats["chunks"] == 1 and stats["decoded_visits"] == 3
    assert stats["compressed_bytes"] == source.manifest.chunks[0].compressed_bytes
    assert stats["decoded_bytes"] == source.manifest.chunks[0].uncompressed_bytes


@pytest.mark.parametrize("kind", ["compressed", "uncompressed"])
def test_last_window_needs_authenticated_chunk_end_to_finish(sealed_short_windows, kind):
    manifest = sealed_short_windows / "manifest.json"
    contents = json.loads(manifest.read_bytes())
    contents["chunks"][0][f"{kind}_sha256"] = "sha256:" + "00" * 32
    manifest.write_text(json.dumps(contents))
    stats = Counter()
    windows = streamed_windows(ShortWindowReader(sealed_short_windows), stats)
    assert [next(windows).index.sequence for _ in range(3)] == [0, 1, 2]
    with pytest.raises(
        BundleCorruptionError, match="compressed IQ changed|chunk geometry or digest changed"
    ):
        next(windows)
    assert stats["chunks"] == 0


def test_size_mismatch_fails_before_window_delivery(sealed_short_windows):
    source = ShortWindowReader(sealed_short_windows)
    member = sealed_short_windows / source.manifest.chunks[0].payload_relative_path
    with member.open("ab") as stream:
        stream.write(b"extra")
    with pytest.raises(BundleCorruptionError, match="outside its sealed file geometry"):
        next(streamed_windows(source, Counter()))
