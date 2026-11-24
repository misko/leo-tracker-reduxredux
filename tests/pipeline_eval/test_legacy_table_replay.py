import ctypes as ct

import numpy as np
import pytest
import zstandard as zstd

from reports.ALGO08.v3 import legacy_block_seek as core
from reports.ALGO08.v3.legacy_block_exception import exception_layout


def checked_frame(*, multiple=False):
    # Level-one libzstd reuses its first table with this deterministic sample.
    # The explicit block flush makes the nonfinal decoded extent below 128 KiB.
    rng = np.random.default_rng(42)
    first = 125_056
    for draw in (32_768, 65_536, 80_000):
        rng.integers(-4096, 4096, size=draw, dtype="<i2")
    raw = rng.integers(-4096, 4096, size=first, dtype="<i2").view(np.uint8)
    raw[1096:1106] = raw[252:262]
    if multiple:
        raw[first + 1096:first + 1106] = raw[first + 252:first + 262]
    parameters = zstd.ZstdCompressionParameters.from_level(
        1, min_match=7, write_checksum=True, write_content_size=False)
    op = zstd.ZstdCompressor(compression_params=parameters).compressobj()
    frame = (op.compress(raw[:first]) + op.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK)
             + op.compress(raw[first:]) + op.flush())
    with zstd.ZstdDecompressor().stream_reader(frame) as stock:
        assert stock.read(len(raw)) == raw.tobytes()
        assert not stock.read(1)
    return frame, raw, first


def test_authentic_table_replay_never_exposes_owner_and_respects_exact_length(tmp_path):
    frame, raw, first = checked_frame()
    rows, owner, seed = exception_layout(frame, len(raw))
    assert owner == 0 and [row[4] for row in rows] == [0, 0]
    assert rows[0][3] == first < 128 * 1024
    assert first - seed[2] == 10
    library = tmp_path / "legacy.so"
    core.build(library)
    native = core.load(library)
    state = native.legacy_open()
    assert state
    try:
        assert native.legacy_configure_origin(state, *seed)
        bounds = (core.Block * len(rows))(*(core.Block(*record) for record in rows))
        output = np.zeros(first, dtype=np.uint8)
        counts = core.Counts()
        assert not native.legacy_span(state, frame, len(frame), bounds, len(bounds),
                                      owner, 0, 1, output.ctypes.data, ct.byref(counts))
        assert not counts.requested_blocks and not native.legacy_origin_replays(state)
        assert native.legacy_span(state, frame, len(frame), bounds, len(bounds),
                                  1, first, first, output.ctypes.data, ct.byref(counts))
        np.testing.assert_array_equal(output, raw[first:])
        assert native.legacy_origin_replays(state) == 1
        assert counts.dependency_blocks == 1 and counts.dependency_decoded == first - 10
    finally:
        native.legacy_close(state)


def test_aggregate_lengths_cannot_certify_more_than_one_mixed_block():
    frame, raw, _ = checked_frame(multiple=True)
    with pytest.raises(ValueError, match="exactly one match-bearing block"):
        exception_layout(frame, len(raw))
