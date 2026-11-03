"""Posterior moments must remain coherent under precomputed matrix indexing."""

import numpy as np
import pytest
from dsx01_hierarchical_bound import hierarchical_bound


@pytest.mark.parametrize('width', [0, 1, 6])
def test_finite_bound_with_empty_or_sparse_nuisance_support(width):
    rng = np.random.default_rng(20261103)
    y = rng.normal(size=30)
    features = rng.normal(size=(30, width))
    features[10:20, :] = 0
    groups = np.repeat([0, 5, 10], 10)
    result = hierarchical_bound(y, features, 1., groups, iterations=256)
    assert result['coefficient'].shape == (width,)
    assert result['precision_iterations'] >= 1
    assert np.isfinite(result['negative_twice_elbo'])
    np.testing.assert_allclose(result['conditional_residual_hz'],
                               y-features@result['coefficient'], atol=0, rtol=0)
    assert result['negative_twice_elbo'] == (
        result['residual']@result['residual']+result['normalization_constant'])


def test_triangular_experiment_matches_well_conditioned_posterior():
    from experimental_hierarchical_triangular import hierarchical_bound as candidate

    rng = np.random.default_rng(842)
    args = (rng.normal(size=40), rng.normal(size=(40, 8)), 1., np.repeat([0, 1], 20))
    kwargs = dict(prior_groups=np.array([-1, -1, 0, 0, 1, 1, 1, 1]))
    expected, actual = hierarchical_bound(*args, **kwargs), candidate(*args, **kwargs)
    assert actual.keys() == expected.keys()
    for key in expected:
        np.testing.assert_allclose(actual[key], expected[key], atol=1e-12, rtol=1e-12)
