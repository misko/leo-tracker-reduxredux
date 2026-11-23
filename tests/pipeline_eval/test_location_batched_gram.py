import ctypes as ct

import numpy as np
import pytest

from reports.ALGO08.v3.location_batched_budget import floor, occupancy
from reports.ALGO08.v3.location_batched_gram import BatchGram, build


def scalar_stats(y, u, sigma, groups):
    gram, rhs = [], []
    for ident in sorted(set(groups)):
        indices = np.flatnonzero(groups == ident)
        active = np.flatnonzero(np.any(u[indices] != 0, axis=0))
        width = len(active)
        block = [0.]*(width*width)
        products = [0.]*width
        for i in indices:
            row = [float(u[i, j])/float(sigma[i]) for j in active]
            response = float(y[i])/float(sigma[i])
            for j, value in enumerate(row):
                products[j] += value*response
                for h, other in enumerate(row):
                    block[j*width+h] += value*other
        gram.extend(block)
        rhs.extend(products)
    return np.array(gram+rhs)


@pytest.mark.hardware
def test_four_native_locations_keep_independent_ordered_gram_and_rhs(tmp_path):
    binary, _ = build(tmp_path / "batch")
    batch = BatchGram(binary)
    layout = batch.lib.nb_layout
    layout.argtypes = [ct.c_int]*3 + [ct.c_void_p]*3
    layout.restype = ct.c_void_p
    free = batch.lib.nb_free
    free.argtypes, free.restype = [ct.c_void_p], None
    groups = np.array([0, 1, 0, 1, 0, 1], dtype=np.int64)
    sigma = np.array([1., 5., 3., 2., 10., 20.])
    design = np.array([[1., 2., 0., 3.], [2., 1., -2., 0.]]*3)
    points = [(np.arange(6, dtype=np.float64)+(l+.25),
               design*np.array([1., 1.+l, 3.+l, -2.-l])) for l in range(4)]
    code = ct.c_int()
    address = layout(6, 4, 2, groups.ctypes.data, points[0][1].ctypes.data, ct.byref(code))
    assert address and code.value == 0
    try:
        result = batch.batch(address, points, sigma, groups)
        for row, (y, u) in zip(result, points, strict=True):
            assert row.tobytes() == scalar_stats(y, u, sigma, groups).tobytes()
        with pytest.raises(ValueError, match="four complete points"):
            batch.batch(address, points[:3], sigma, groups)
    finally:
        free(address)


def test_occupancy_counts_final_posterior_and_partial_last_batch():
    result = occupancy([4, 0, 2, 1, 1], 4)
    assert result["posterior_passes"] == 13
    assert result["vector_steps"] == 7
    assert result["slots"] == 28
    assert result["batches_with_unequal_stops"] == 1
    assert result["utilization"] == 13/28


def test_free_stage_bound_cannot_credit_overlapping_or_missing_work():
    assert floor(26., 6., 14.)["residual_gap_s"] == 6.
    with pytest.raises(ValueError):
        floor(3., 4., 1.)
