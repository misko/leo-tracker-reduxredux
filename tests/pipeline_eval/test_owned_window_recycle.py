import ctypes as ct

import numpy as np
import pytest

from reports.ALGO08.v3.owned_window_recycle import MAX_CAPACITY, WindowArena


def test_descendant_and_buffer_exports_keep_recycled_destination_pinned():
    arena = WindowArena()
    first = arena.borrow(4096)
    initial_address = first.ctypes.data
    ct.memset(initial_address, 23, first.nbytes)
    descendant = first[5:32].view()
    indirect = np.frombuffer(memoryview(descendant), dtype=np.uint8)
    with pytest.raises(ValueError):
        indirect.flags.writeable = True
    del first, descendant
    history = arena.borrow(4096)
    assert history.ctypes.data != initial_address
    assert arena.borrow(4096) is None
    assert indirect.tolist() == [23] * 27
    del indirect
    next_window = arena.borrow(4096)
    assert next_window.ctypes.data == initial_address
    assert arena.receipt() == dict(allocations=2, reuses=1, fallbacks=1, retained_bytes=8192)


def test_unsupported_extents_fall_back_without_replacing_live_storage():
    arena = WindowArena()
    assert arena.borrow(0) is None
    assert arena.borrow(MAX_CAPACITY + 1) is None
    first = arena.borrow(16)
    assert arena.borrow(8) is None
    assert arena.receipt()["retained_bytes"] == 16
    ct.memset(first.ctypes.data, 170, first.nbytes)
    del arena
    assert first.tolist() == [170] * 16
