import numpy as np
import pytest

from plot_responsibilities import counts_above, manual_responsibilities, summarize


def test_threshold_and_nonzero_semantics():
    p = np.array([[.8, .01, 1e-300], [0., .005, 0.]])
    np.testing.assert_array_equal(counts_above(p, 0), [3, 1])
    np.testing.assert_array_equal(counts_above(p, .01), [2, 0])
    stats = summarize(p, 1-p.sum(axis=1))
    assert stats['positive_pairs'] == 4
    assert stats['thresholds']['0.01']['multiple'] == 1
    assert stats['thresholds']['0.01']['zero'] == 1


def test_probabilities_include_clutter_and_exclude_invisible_satellite():
    p, clutter = manual_responsibilities(np.array([0.]), np.array([[0., 0., 0.]]),
                                        np.array([[True, True, False]]), 200., .8/3, 2., 1/4.4e-6)
    assert p[0, 0] == p[0, 1]
    assert p[0, 2] == 0
    assert 0 < p[0, 0] < .5
    np.testing.assert_allclose(p.sum(axis=1)+clutter, 1.)


def test_bad_inputs_rejected():
    with pytest.raises(ValueError):
        counts_above(np.array([[np.nan]]), 0)
    with pytest.raises(ValueError):
        summarize(np.array([[.8, .6]]), np.array([.1]))
