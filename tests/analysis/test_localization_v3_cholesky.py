"""Owned factorization path against the frozen pre-change full likelihood."""

import ast
import inspect

import algo07v3_precholesky_hierarchical_oracle as reference
import algo07v3_preworkspace_hierarchical_oracle as preworkspace
import numpy as np
import pytest

from leo.analysis.localization_v3 import hierarchical


def test_qualified_factorization_boundary_is_preserved_before_workspace_change():
    expected = inspect.getsource(reference.hierarchical_bound).replace(
        'root = np.linalg.cholesky(gram)', 'root = _cholesky(gram)')
    assert ast.dump(ast.parse(inspect.getsource(preworkspace.hierarchical_bound))) == (
        ast.dump(ast.parse(expected)))
    assert ast.dump(ast.parse(inspect.getsource(hierarchical._cholesky))) == (
        ast.dump(ast.parse(inspect.getsource(preworkspace._cholesky))))


@pytest.mark.parametrize('width', [0, 1, 9, 32, 64, 175])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('learned_prior', [False, True])
def test_full_likelihood_is_byte_exact(width, layout, learned_prior):
    rng = np.random.default_rng(20261106 + width)
    features = rng.normal(size=(300, width))
    features[rng.uniform(size=features.shape) < .7] = 0
    features = np.array(features, order=layout)
    raw = rng.normal(size=300) * 150
    groups, sigma = np.repeat(np.arange(6), 50), rng.uniform(60, 200, size=300)
    prior = np.arange(width) % 4 if learned_prior else None
    if learned_prior:
        prior[::3] = -1
    keywords = dict(prior_groups=prior, powers=rng.uniform(.5, 1, size=6), iterations=16)
    inputs = (raw, features, sigma, groups)
    before = [v.tobytes() for v in inputs]
    expected = reference.hierarchical_bound(*inputs, **keywords)
    actual = hierarchical.hierarchical_bound(*inputs, **keywords)
    assert actual.keys() == expected.keys()
    for name in expected:
        a, b = np.asarray(actual[name]), np.asarray(expected[name])
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), name
    assert before == [v.tobytes() for v in inputs]


def test_factor_layout_zero_dimension_and_failure():
    gram = np.array([[4., 2.], [2., 5.]])
    before = gram.tobytes()
    result = hierarchical._cholesky(gram)
    assert result.flags.c_contiguous
    assert result.tobytes() == np.linalg.cholesky(gram).tobytes()
    assert gram.tobytes() == before
    assert hierarchical._cholesky(np.empty((0, 0))).shape == (0, 0)
    with pytest.raises(np.linalg.LinAlgError, match='positive definite'):
        hierarchical._cholesky(np.array([[1., 2.], [2., 1.]]))


def test_lapack_failure_is_not_a_scientific_result(monkeypatch):
    monkeypatch.setattr(hierarchical, 'dpotrf', lambda *a, **k: (np.eye(2), 1))
    with pytest.raises(np.linalg.LinAlgError):
        hierarchical._cholesky(np.eye(2))
