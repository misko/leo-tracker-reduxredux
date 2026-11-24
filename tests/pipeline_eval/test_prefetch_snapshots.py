from contextlib import contextmanager
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.prefetch_snapshots import AlternatingSnapshots, binding


def test_outstanding_descendants_survive_alternation_refusal_and_close():
    pool = AlternatingSnapshots(16)

    def export(value):
        destination = pool.borrow(8)
        destination[:] = value
        return np.frombuffer(memoryview(destination).toreadonly(), dtype=np.uint8)

    first, second, third = export(1), export(2), export(3)
    assert len({a.ctypes.data for a in (first, second, third)}) == 3
    assert pool.counts()[0]["ordinary"] == 1
    released = second.ctypes.data
    del second
    fourth = export(4)
    assert fourth.ctypes.data == released
    assert pool.counts()[1]["reuses"] == 1
    assert pool.borrow(32).size == 32
    pool.close()
    assert (first == 1).all() and (third == 3).all() and (fourth == 4).all()
    assert export(5).ctypes.data != first.ctypes.data


def test_original_producer_binding_restores_after_cancelled_acquisition(tmp_path):
    root = Path(__file__).resolve().parents[2]
    original = run_path(str(root / "tools/pipeline_eval/variants/experimental/receiver_ingress.py"))[
        "read_regular_descriptor"]
    namespace = {"contextmanager": contextmanager, "read_regular_descriptor": original}
    exec("@contextmanager\ndef fetch():\n    yield read_regular_descriptor\n", namespace)
    frontier = SimpleNamespace(load_prefetch=lambda: namespace["fetch"])
    file = tmp_path / "original"
    file.write_bytes(b"signed bytes")
    ordinary, audit = frontier.load_prefetch, []
    with pytest.raises(RuntimeError, match="cancel acquisition"), binding(frontier, audit):
        fetch = frontier.load_prefetch()
        with fetch() as observed, file.open("rb") as fd:
            assert observed is not original
            output = observed(fd.fileno(), 12)
            raise RuntimeError("cancel acquisition")

    assert frontier.load_prefetch is ordinary
    assert namespace["read_regular_descriptor"] is original
    assert output.readonly and bytes(output) == b"signed bytes"
    assert audit == [[{"allocations": 1, "peak_bytes": 12}, {}]]
