from contextlib import ExitStack

import numpy as np

from tools.pipeline_eval.variants import v5_recovery_cache_memory as cache
from tools.pipeline_eval.variants import v5_stream_recovery as scratch


def test_syncs_and_evicts_completed_pages_without_changing_orbit_bytes(tmp_path, monkeypatch):
    events = []

    def sync(fd):
        events.append(("sync", fd))

    def advise(fd, start, length, advice):
        assert advice == cache.os.POSIX_FADV_DONTNEED
        events.append(("drop", fd, start, length))

    monkeypatch.setattr(cache.os, "fdatasync", sync)
    monkeypatch.setattr(cache.os, "posix_fadvise", advise)
    monkeypatch.setattr(cache, "WRITE_WINDOW_BYTES", 8192)
    previous = scratch.OrbitRows.append, scratch.receipt
    values = np.arange(6 * 100 * 3.0).reshape(6, 100, 3)
    with ExitStack() as files:
        p, v = scratch.new_components(files, tmp_path, 100)
        with cache.bounded_scratch_cache() as metrics:
            for row, data in ((p, values), (v, -values)):
                row.append(data[:5])
                row.append(data[5:])
            result = scratch.receipt(p, v)
        np.testing.assert_array_equal(p[:6], values)
        np.testing.assert_array_equal(v[:6], -values)
        assert result["scratch_bytes"] == 2 * values.nbytes
        assert metrics == dict(syncs=4, max_sync_range_bytes=8192, advised_bytes=24576)
        for row in (p, v):
            fd = row.file.fileno()
            assert [e for e in events if e[1] == fd] == [
                ("sync", fd),
                ("drop", fd, 0, 8192),
                ("sync", fd),
                ("drop", fd, 8192, 4096),
            ]
    assert (scratch.OrbitRows.append, scratch.receipt) == previous
