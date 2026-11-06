import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_covariance import candidate, symmetric_product

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


@pytest.mark.parametrize('width', [0, 1, 7, 33])
def test_workspace_complete_likelihood_preserves_outputs_and_inputs(width):
    rng = np.random.default_rng(137)
    args = (rng.normal(size=60), rng.normal(size=(60, width)),
            np.linspace(.5, 2., 60), np.repeat(np.arange(6), 10))
    kwargs = dict(prior_groups=np.arange(width) % 3, iterations=16)
    before = fingerprint((args, kwargs))
    actual = candidate('workspace')[0](*args, **kwargs)
    assert fingerprint(actual) == fingerprint(hierarchical_bound(*args, **kwargs))
    assert fingerprint((args, kwargs)) == before


def test_symmetric_product_copies_upper_triangle_and_preserves_input():
    a = np.array([[1., 0.], [2., 3.]], order='F')
    before = a.copy()
    result = symmetric_product(a)
    np.testing.assert_array_equal(result, [[5., 6.], [6., 9.]])
    np.testing.assert_array_equal(a, before)
    assert result.flags.c_contiguous


def test_unknown_variant_rejected():
    with pytest.raises(ValueError):
        candidate('approximate')
