import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_posterior_assembly import candidate_function, kernel

from leo.analysis.localization_v3 import hierarchical, position


@pytest.mark.parametrize('width', [0, 1, 16, 190])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('density', [0., .2, 1.])
def test_complete_likelihood_is_exact_and_inputs_unchanged(width, layout, density):
    rng = np.random.default_rng(2391)
    u = rng.normal(size=(96, width))
    u[rng.random(u.shape) >= density] = 0
    u = np.array(u, order=layout)
    y, s, g = rng.normal(size=96) * 100, rng.uniform(3, 40, 96), np.arange(96) % 5 * 3
    kwargs = dict(prior_groups=np.arange(width) // 5 - 1,
                  powers=np.linspace(.1, 1., 5), iterations=16)
    inputs = fingerprint((y, u, s, g, kwargs))
    candidate, _, _ = candidate_function()
    assert fingerprint(candidate(y, u, s, g, **kwargs)) == fingerprint(
        hierarchical.hierarchical_bound(y, u, s, g, **kwargs))
    assert fingerprint((y, u, s, g, kwargs)) == inputs


def test_kernel_substitution_restored_on_failure():
    original = position.hierarchical_bound
    candidate, _, _ = candidate_function()
    with pytest.raises(RuntimeError), kernel(candidate):
        assert position.hierarchical_bound is candidate
        raise RuntimeError('abort')
    assert position.hierarchical_bound is original


def test_assembly_preserves_duplicate_addition_order_with_extreme_cancellation():
    indices = np.array([0, 0, 1, 0, 1, 0, 1])
    values = np.array([1e100, 1., -1e100, -1e100, 1., -0., 1e100])
    original = np.array([2., 3., 4.])
    expected = original.copy()
    np.add.at(expected, indices, values)
    actual = np.bincount(np.r_[np.arange(3), indices], weights=np.r_[original, values],
                         minlength=3)
    assert expected.tobytes() == actual.tobytes()
