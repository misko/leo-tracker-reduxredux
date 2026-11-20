import gc
import weakref

import numpy as np
import pytest

from tools.pipeline_eval.variants.v5_sparse_discovery import retain_diagnostics


def diagnostics(passing, cost):
    values = np.arange(12, dtype=np.float64).reshape(4, 3).copy()
    return dict(
        passing=np.array(passing), cost=np.array(cost), residual=values, innovations=-values
    )


def test_keeps_every_visible_passing_row_and_best_visible_nomination():
    terms = diagnostics([True, False, True, True], [1, 0, 3, -4])
    old = terms["residual"]
    old_ref = weakref.ref(old)
    dense, retained, rows = retain_diagnostics(terms, np.array([True, True, True, False]))
    assert rows == 3
    assert dense == 2 * old.nbytes
    assert retained == 2 * old[:3].nbytes + 3 * np.dtype(np.intp).itemsize
    for j in (0, 1, 2):
        np.testing.assert_array_equal(terms["residual"][j], old[j])
        np.testing.assert_array_equal(terms["innovations"][j], -old[j])
    with pytest.raises(IndexError):
        terms["residual"][3]
    del old
    gc.collect()
    assert old_ref() is None


@pytest.mark.parametrize(
    ("visible", "chosen"),
    [
        ([False, True, True, False], 1),
        ([False, False, False, False], 0),
    ],
)
def test_original_fallback_and_ties(visible, chosen):
    terms = diagnostics([False] * 4, [0, 2, 2, -4])
    original = terms["residual"][chosen].copy()
    assert retain_diagnostics(terms, np.array(visible))[2] == 1
    np.testing.assert_array_equal(terms["residual"][chosen], original)
