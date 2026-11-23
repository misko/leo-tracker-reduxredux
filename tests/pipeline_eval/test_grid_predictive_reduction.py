from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import solve_triangular

from reports.ALGO08.v3.grid_predictive_reduction import collapse_biases, reduced_predictive, reduced_whiten
from tools.pipeline_eval.variants.algo08_posterior_handoff import predictive_factor


def test_zero_rhs_prefix_drops_only_the_triangular_leading_block():
    lower = np.array([[1., 0., 0.], [.7, 2., 0.], [.2, -.4, 3.]])
    order = np.array([1, 2, 0])
    scale = np.array([2., .3, 1.])
    design = np.array([[3., 0., 9.], [0., 0., 11.]])
    original = solve_triangular(lower, (design[:, order]*scale[order]).T, lower=True).T
    reduced, prefix = reduced_whiten(design, lower, order, scale)
    assert prefix == 1
    assert np.all(original[:, :prefix] == 0)
    np.testing.assert_allclose(reduced, original[:, prefix:])
    assert reduced_whiten(np.zeros_like(design), lower, order, scale)[0].shape == (2, 0)


@pytest.mark.parametrize("width,prefix", ((9, 4), (9, 0), (9, 9)))
def test_eliminated_bias_objective_matches_existing_checked_posterior_kernel(width, prefix):
    rng = np.random.default_rng(764 + prefix)
    order = rng.permutation(width)
    lower = np.tril(rng.normal(size=(width, width))) * .1 + 3*np.eye(width)
    capture = SimpleNamespace(width=width, lower=lower, order=order)
    design = rng.normal(size=(33, width)) * 140.
    design[:, order[:prefix]] = 0
    raw = rng.normal(size=len(design))*850.
    sigma = np.exp(rng.uniform(0, 3, len(design)))
    by_curve = np.repeat([1, 4, 6, 7], [2, 7, 13, 11])
    old = predictive_factor(raw, design, sigma, by_curve, capture, 3)
    new, counts = reduced_predictive(raw, design, sigma, by_curve, capture, 3)
    assert new["objective"] == pytest.approx(old["objective"], rel=1e-12, abs=1e-8)
    assert new["normalization_constant"] == old["normalization_constant"]
    assert (counts["prefix"], counts["biases"]) == (prefix, 4)


def test_declines_nonmonotone_groups_or_nonpositive_noise():
    with pytest.raises(ValueError, match="curve labels"):
        collapse_biases(np.ones(3), np.ones((3, 4)), np.ones(3), np.array([0, 1, 0]))
    with pytest.raises(ValueError, match="noise scales"):
        collapse_biases(np.ones(3), np.ones((3, 4)), np.zeros(3), np.array([0, 0, 1]))
