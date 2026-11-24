import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from runpy import run_path

import numpy as np
import pytest

from leo.storage.errors import BundleCorruptionError
from reports.ALGO08.v3.legacy_snapshot_reuse import SnapshotSlot, descriptor_port


def test_retained_numpy_consumer_prevents_overwrite_even_across_workers():
    pool = SnapshotSlot(32)
    lease = pool.borrow(16)
    pointer = lease.ctypes.data
    lease[:] = 7
    exported = np.frombuffer(memoryview(lease).toreadonly(), dtype=np.uint8)
    del lease
    assert pool.in_use
    with ThreadPoolExecutor(max_workers=1) as worker:
        unrelated = worker.submit(pool.borrow, 16).result()
        unrelated[:] = 33
        assert unrelated.ctypes.data != pointer
        assert not exported.flags.writeable
        assert (exported == 7).all()
        del exported
        same = worker.submit(pool.borrow, 8).result()
    assert same.ctypes.data == pointer
    assert pool.counts == {"allocations": 1, "reuses": 1, "ordinary": 1, "peak_bytes": 16}


def test_closed_or_excess_slot_falls_back_to_a_private_allocation():
    pool = SnapshotSlot(32)
    verify = pool.borrow(8)
    verify[:] = 53
    pool.close()
    assert pool.borrow(8).ctypes.data != verify.ctypes.data
    assert pool.borrow(64).shape == (64,)
    assert (verify == 53).all()
    assert pool.counts["ordinary"] == 2


def test_descriptor_keeps_complete_original_checks(tmp_path):
    root = Path(__file__).resolve().parents[2]
    ingress = run_path(str(root / "tools/pipeline_eval/variants/experimental/receiver_ingress.py"))
    pool = SnapshotSlot(64)
    candidate = descriptor_port(ingress["read_regular_descriptor"], pool)
    source = tmp_path / "iq.zst"
    source.write_bytes(bytes(range(32)))
    with source.open("rb") as stream:
        view = candidate(stream.fileno(), 32)
        assert view.readonly and bytes(view) == bytes(range(32))
    del view
    with source.open("rb") as stream:
        with pytest.raises(BundleCorruptionError, match="exceeds its declared bound"):
            candidate(stream.fileno(), 31)
    with source.open("rb") as stream:
        assert bytes(candidate(stream.fileno(), 32)) == bytes(range(32))
    os.link(source, tmp_path / "hard-link")
    with source.open("rb") as stream:
        with pytest.raises(BundleCorruptionError, match="not one regular file"):
            candidate(stream.fileno(), 32)
    assert pool.counts["allocations"] == pool.counts["reuses"] == 1
