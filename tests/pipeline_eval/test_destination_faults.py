import numpy as np
import pytest

from reports.ALGO08.v3 import destination_faults as trial
from reports.ALGO08.v3.signed_ingress_reuse import CompressedSlots


def test_prefault_covers_partial_final_page_and_stays_inside_destination():
    allocation = np.full(24, 7, dtype=np.uint8)
    view = allocation[2:19]
    trial.touch_pages(view, 5)
    assert np.flatnonzero(allocation == 0).tolist() == [2, 7, 12, 17, 18]


def test_allocation_monitor_does_not_prefault_stock_or_change_pool_ownership(monkeypatch):
    monkeypatch.setattr(trial.ceiling, "COMPRESSED", 64)
    pool = CompressedSlots(64)
    monitor = trial.Monitor()
    chooser = trial.Allocator(monitor, "pool", pool)
    with pytest.raises(ValueError, match="single signed member"):
        chooser.empty(65, np.uint8)
    first = chooser.empty(64, np.uint8)
    pointer = first.ctypes.data
    keep = memoryview(first).toreadonly()
    del first
    other = chooser.empty(64, np.uint8)
    assert other.ctypes.data != pointer
    del keep
    resumed = chooser.empty(64, np.uint8)
    assert resumed.ctypes.data == pointer
    assert pool.counts == {"allocation": 2, "reuse": 1}
    assert monitor.stats["allocation"]["calls"] == 3
    assert "pre_touch" not in monitor.stats


def test_source_port_rejects_waveform_roots_outside_staged_path(monkeypatch, tmp_path):
    monkeypatch.setattr(trial, "STAGED", tmp_path)
    with pytest.raises(ValueError, match="only the previously staged tmpfs member"):
        trial.tmpfs_member({"entry": {"path": "/srv/bulk/anything"}})
