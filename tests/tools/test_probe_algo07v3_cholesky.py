import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_cholesky import candidate, hierarchical, root


def test_factor_retains_input_and_layout():
    gram = np.array([[4., 2.], [2., 5.]])
    before = gram.copy()
    result = root(gram)
    assert result.flags.c_contiguous
    assert result.tobytes() == np.linalg.cholesky(gram).tobytes()
    np.testing.assert_array_equal(gram, before)


def test_empty_and_non_positive_definite():
    assert root(np.empty((0, 0))).shape == (0, 0)
    with pytest.raises(np.linalg.LinAlgError):
        root(np.array([[1., 2.], [2., 1.]]))


def test_source_extraction_keeps_single_cholesky_boundary():
    function, original, changed = candidate()
    assert callable(function)
    assert changed == original.replace('root = np.linalg.cholesky(gram)', 'root = _root(gram)')


@pytest.mark.parametrize('width', [0, 1, 9, 32, 64, 175])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('learned_prior', [False, True])
def test_complete_likelihood_exact_on_seeded_sparse_dense_and_prior_cases(
    width, layout, learned_prior
):
    rng = np.random.default_rng(20261106 + width)
    features = rng.normal(size=(300, width))
    features[rng.uniform(size=features.shape) < .7] = 0
    features = np.array(features, order=layout)
    raw = rng.normal(size=300) * 150
    groups = np.repeat(np.arange(6), 50)
    sigma = rng.uniform(60, 200, size=300)
    prior = np.arange(width) % 4 if learned_prior else None
    if learned_prior:
        prior[::3] = -1
    keywords = dict(prior_groups=prior, powers=rng.uniform(.5, 1, size=6), iterations=16)
    before = fingerprint((features, raw, groups, sigma, keywords))
    operation, _, _ = candidate()
    expected = hierarchical.hierarchical_bound(raw, features, sigma, groups, **keywords)
    result = operation(raw, features, sigma, groups, **keywords)
    assert fingerprint(result) == fingerprint(expected)
    assert before == fingerprint((features, raw, groups, sigma, keywords))
