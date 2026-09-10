"""Private shared-buffer ownership tests; no worker, radio, or external storage."""

import ctypes as ct

import numpy as np
import pytest

from tests.scanner.test_native_presence_pool import Pool, Request
from tests.scanner.test_native_presence_pool import library as library
from tools.native_presence import pointer


@pytest.fixture(params=[2500000, 5000000])
def held(library, request):
    lib = library
    lib.leo_dwell_pool_enable_held.argtypes = [ct.c_void_p]
    lib.leo_probe_feed_held.argtypes = lib.leo_probe_feed.argtypes
    for name in ("leo_probe_publish_held", "leo_probe_release_held"):
        getattr(lib, name).argtypes = [ct.c_void_p, ct.c_uint32, ct.POINTER(Request)]
    p = Pool(lib, request.param, dwell=True)
    assert lib.leo_dwell_pool_enable_held(p.address) == 0
    try:
        yield p
    finally:
        p.mapping.close()


def fill(p, q):
    assert p.begin(q) == 1
    iq = np.full((q.sample_count, 2), 17000 + q.sequence, dtype=np.int16)
    assert (
        p.lib.leo_probe_feed_held(ct.byref(p.collector), q.probe_start, pointer(iq), len(iq), 2, 0)
        == 1
    )
    return p.collector.slot


def test_three_held_slots_are_invisible_and_reclaimable(held):
    p = held
    requests = [p.request(i) for i in range(3)]
    slots = [fill(p, q) for q in requests]
    assert len(set(slots)) == 3
    assert p.take() is None and p.stats().submitted == 0
    assert p.stats().occupied_slots == 3
    assert p.begin(p.request(3)) == 0
    assert p.lib.leo_probe_release_held(p.address, slots[1], ct.byref(requests[1])) == 0
    newest = p.request(3)
    reused = fill(p, newest)
    assert reused == slots[1]
    # Old identity cannot release a slot after reuse (ABA protection).
    assert p.lib.leo_probe_release_held(p.address, reused, ct.byref(requests[1])) == -1
    assert p.lib.leo_probe_publish_held(p.address, reused, ct.byref(newest)) == 0
    taken, request, iq = p.take()
    assert taken == reused and request.sequence == 3
    assert np.all(iq == 17003)
    assert p.lib.leo_probe_release_held(p.address, reused, ct.byref(newest)) == -1
    assert p.complete(taken, request) == 0
    assert p.read().request.sequence == 3
    assert p.stats().occupied_slots == 2


def test_published_slots_are_not_owner_revocable_and_take_in_sequence_order(held):
    p = held
    q0, q1 = p.request(0), p.request(1)
    slot0, slot1 = fill(p, q0), fill(p, q1)
    assert p.lib.leo_probe_publish_held(p.address, slot1, ct.byref(q1)) == 0
    assert p.lib.leo_probe_publish_held(p.address, slot0, ct.byref(q0)) == 0
    assert p.lib.leo_probe_release_held(p.address, slot0, ct.byref(q0)) == -1
    assert p.lib.leo_probe_publish_held(p.address, slot0, ct.byref(q0)) == -1
    for sequence in range(2):
        slot, q, iq = p.take()
        assert q.sequence == sequence and np.all(iq == 17000 + sequence)
        assert p.complete(slot, q) == 0
    assert p.stats().submitted == p.stats().completed == 2


def test_partial_and_wrong_mode_cannot_publish(held):
    p = held
    q = p.request()
    assert p.lib.leo_dwell_pool_enable_held(p.address) == -1
    assert p.begin(q) == 1
    iq = np.zeros((q.sample_count, 2), dtype=np.int16)
    assert p.feed(q.probe_start, iq) == -1
    assert p.take() is None
    assert p.lib.leo_probe_publish_held(p.address, p.collector.slot, ct.byref(q)) == -1
    p.lib.leo_probe_abort(ct.byref(p.collector))
    assert p.stats().occupied_slots == 0


def test_old_private_mapping_version_is_rejected(held):
    p = held
    lib = p.lib
    lib.leo_probe_pool_configuration.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_uint64),
        ct.POINTER(ct.c_uint64),
        ct.POINTER(ct.c_uint32),
    ]
    session, generation, rate = ct.c_uint64(), ct.c_uint64(), ct.c_uint32()
    # Model only the old magic inventory, not a historical executable.
    ct.c_uint32.from_address(p.address).value = 0x4C505032
    assert (
        lib.leo_probe_pool_configuration(
            p.address, ct.byref(session), ct.byref(generation), ct.byref(rate)
        )
        == -1
    )
