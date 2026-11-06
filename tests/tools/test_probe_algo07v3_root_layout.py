"""Layout may change internally; every returned scientific byte must match."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_root_layout import candidate

from leo.analysis.localization_v3 import hierarchical


@pytest.mark.parametrize('width', [0, 1, 7, 33])
@pytest.mark.parametrize('order', ['C', 'F'])
@pytest.mark.parametrize('learned_prior', [False, True])
def test_complete_likelihood_and_inputs_exact(width, order, learned_prior):
    rng = np.random.default_rng(87)
    features = np.array(rng.normal(size=(90, width)), order=order)
    features[rng.random(features.shape) < .4] = 0
    raw = rng.normal(size=90)
    groups = np.arange(90) % 6
    prior = np.arange(width) % 3 if learned_prior else None
    args = raw, features, np.linspace(.8, 1.3, 90), groups
    kw = dict(prior_groups=prior, iterations=40)
    before = fingerprint((args, kw))
    operation, _, _ = candidate()
    expected = fingerprint(hierarchical.hierarchical_bound(*args, **kw))
    assert fingerprint(operation(*args, **kw)) == expected
    assert fingerprint((args, kw)) == before


def test_factor_layout_and_singular_error():
    operation, _, _ = candidate()
    root = operation.__globals__['_cholesky']
    matrix = np.array([[2., .2], [.2, 1.]])
    result = root(matrix)
    assert result.flags.f_contiguous
    assert fingerprint(result) == fingerprint(hierarchical._cholesky(matrix))
    with pytest.raises(np.linalg.LinAlgError):
        root(np.zeros((2, 2)))
