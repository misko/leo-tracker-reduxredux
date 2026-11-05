import numpy as np
import pytest
from probe_algo07v3_assembly import exact_result
from probe_algo07v3_factor_reuse import FactorMismatch, FactorProbe, candidate_function

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


@pytest.mark.parametrize("width", [0, 1, 9, 32])
@pytest.mark.parametrize("order", ["C", "F"])
def test_factor_reuse_matches_sparse_kernel_with_both_layouts(width, order):
    rng = np.random.default_rng(431)
    n = 97
    features = rng.normal(size=(n, width))
    features[rng.random((n, width)) < 0.7] = 0
    features = np.array(features, order=order)
    raw = rng.normal(size=n)
    sigma = rng.uniform(0.5, 2, n)
    groups = np.arange(n) % 5
    prior = np.arange(width) % 3 - 1
    kwargs = dict(prior_groups=prior, powers=np.linspace(0.4, 1, 5), iterations=30)
    candidate, _, _ = candidate_function()
    exact_result(
        hierarchical_bound(raw, features, sigma, groups, **kwargs),
        candidate(raw, features, sigma, groups, **kwargs),
    )


def test_probe_mismatch_cannot_be_swallowed_as_ordinary_scientific_rejection():
    probe = FactorProbe(lambda *a: dict(x=1.0), lambda *a: dict(x=1.0 + 1e-12))
    with pytest.raises(FactorMismatch):
        probe(np.ones(3), np.ones((3, 2)))
    assert probe.failures and not issubclass(FactorMismatch, Exception)


def test_probe_preserves_original_invalid_input_exception():
    def invalid(*args):
        raise ValueError("invalid input")

    probe = FactorProbe(invalid, invalid)
    with pytest.raises(ValueError, match="invalid input"):
        probe(np.ones(3), np.ones((3, 2)))
    assert not probe.failures
