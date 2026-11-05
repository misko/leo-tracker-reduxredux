import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_variance_indices import candidate_function

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


@pytest.mark.parametrize('width', [0, 1, 16, 190])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('density', [0., .2, 1.])
def test_all_posterior_fields_exact(width, layout, density):
    rng = np.random.default_rng(2391)
    u = rng.normal(size=(96, width))
    u[rng.random(u.shape) >= density] = 0
    u = np.array(u, order=layout)
    y, s, g = rng.normal(size=96) * 100, rng.uniform(3, 40, 96), np.arange(96) % 5 * 3
    kwargs = dict(prior_groups=np.arange(width) // 5 - 1,
                  powers=np.linspace(.1, 1., 5), iterations=16)
    before = fingerprint((y, u, s, g, kwargs))
    candidate, _, _ = candidate_function()
    assert fingerprint(candidate(y, u, s, g, **kwargs)) == fingerprint(
        hierarchical_bound(y, u, s, g, **kwargs))
    assert fingerprint((y, u, s, g, kwargs)) == before


def test_exact_flat_gather_with_repeated_columns_and_signed_values():
    rng = np.random.default_rng(177)
    for order in ('C', 'F'):
        cov = np.array(rng.normal(size=(49, 49)), order=order)
        columns = np.array([[1, 2, 48], [7, 9, 17], [0, 0, 48]])
        expected = cov[columns[:, :, None], columns[:, None, :]]
        actual = cov.ravel()[columns[:, :, None] * 49 + columns[:, None, :]]
        assert actual.tobytes() == expected.tobytes()
