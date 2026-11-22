from unittest.mock import patch

import numpy as np
import pytest

from leo.analysis import polynomial_tracklets as poly
from tools.pipeline_eval.variants.experimental.graph_degree_bound import best_piece


@pytest.mark.parametrize("degree", range(5))
@pytest.mark.parametrize("max_slope", [30., 4000.])
def test_exact_choice_under_support_gaps_slopes_and_alias_wraps(degree, max_slope):
    rng = np.random.default_rng(229)
    for t in (np.arange(80.), np.repeat(np.arange(25.), 3), np.r_[0:10, 90:100]):
        predict = 4300 * t - 17 * t**2
        y = poly._wrap(predict + rng.normal(0, 140, len(t)), 230000)
        cfg = poly.TrackConfig(max_degree=degree, max_slope_hz_s=max_slope,
                               alias_spacing_hz=230000)
        for ix in (np.arange(len(t)), np.arange(8), np.arange(2)):
            actual = best_piece(t, y, ix, predict[ix], cfg)
            stock = poly._best_piece(t, y, ix, predict[ix], cfg)
            assert (actual is None) == (stock is None)
            if stock is not None:
                assert actual.keys() == stock.keys()
                for k in stock:
                    np.testing.assert_array_equal(actual[k], stock[k])


def test_zero_residual_needs_no_higher_degree_fit():
    t = np.arange(50.)
    cfg = poly.TrackConfig()
    y = np.zeros_like(t)
    with patch.object(poly, "_piece", wraps=poly._piece) as fit:
        found = best_piece(t, y, np.arange(len(t)), y, cfg)
    assert found["degree"] == 0 and fit.call_count == 1
