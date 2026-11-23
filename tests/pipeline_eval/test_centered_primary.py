from io import BytesIO
import errno
import os

import pytest

from reports.ALGO08.v3 import centered_primary as centered
from reports.ALGO08.v3.centered_primary_cached import RWF_NOWAIT, cached_stream


def test_same_frame_epoch_on_both_native_grids():
    assert centered.SHIFT + centered.APERTURE == 160000
    assert centered.SHIFT % centered.PERIOD == 1
    for frame in range(8):
        # Exact-verifier full-rate spacing and scout spacing for its stride 4.
        assert (40000 * (frame+3) + 1)//3 - (40000 * frame + 1)//3 == centered.SHIFT
        for stride in (1, 4):
            previous = round(frame * 1e7 / (750. * stride))
            shifted = round((frame+3) * 1e7 / (750. * stride))
            assert (shifted-previous)*stride == centered.SHIFT


def test_only_the_uniquely_bound_native_entry_changes():
    entry = b"int cancellation_primary_factors() { return 0; }"
    extension = b"\nint cancellation_primary_factors() { return primary_on_aperture(); }"
    got = centered.source_with_center(entry, extension)
    assert got.startswith(b"static int primary_on_aperture()") and got.endswith(extension)
    for other in (b"", entry + entry):
        with pytest.raises(ValueError, match="pinned signed primary"):
            centered.source_with_center(other, extension)


def test_stock_primary_and_margin_winner_are_scored_separately():
    primary = (0, 0, -0.25, -10_000, 0.3, 0.1)
    residual = (1, 401, 0.1, 20_000, 0.7, 0.1)
    proposal = (0, centered.PERIOD-1, 0.25, -10_100, 0.3, 0.1)
    extra = (0, 401, 0, -20_000, 0.3, 0.1)
    rows = [dict(installed=[residual, primary], prefix=[proposal], centered=[extra], lane=1)]
    score = centered.score(rows)
    assert score["prefix"]["rank_zero_matches"] == 1
    assert score["prefix"]["selected_matches_lane_1"] == 0
    assert score["centered"]["new_proposals"] == 1
    assert not centered.match(residual, extra)["hit"]


def test_cache_only_stream_short_reads_and_explicit_nowait(tmp_path, monkeypatch):
    path = tmp_path / "saved"
    path.write_bytes(b"abcd")
    original = os.preadv
    offsets = []

    def mock(fd, buffers, offset, flags):
        assert flags == RWF_NOWAIT
        offsets.append(offset)
        return original(fd, [buffers[0][:2]], offset)

    monkeypatch.setattr(os, "preadv", mock)
    out = BytesIO()
    cached_stream(path, 4, out)
    assert out.getvalue() == b"abcd" and offsets == [0, 2]
    with pytest.raises(ValueError, match="extent"):
        cached_stream(path, 3, out)


def test_cache_miss_does_not_retry_as_a_blocking_read(tmp_path, monkeypatch):
    path = tmp_path / "saved"
    path.write_bytes(b"a")
    calls = []

    def missing(_fd, _buffers, offset, flags):
        calls.append((offset, flags))
        raise BlockingIOError(errno.EAGAIN, "not resident")

    monkeypatch.setattr(os, "preadv", missing)
    with pytest.raises(BlockingIOError):
        cached_stream(path, 4, BytesIO())
    assert calls == [(0, RWF_NOWAIT)]
