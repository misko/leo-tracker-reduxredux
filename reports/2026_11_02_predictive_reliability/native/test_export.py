"""Dense covariance and native-boundary tests; no scan fits."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('native_export', Path(__file__).with_name('export.py'))
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_train_conditional_factors_and_cross_blocks_match_dense_covariance():
    rng = np.random.default_rng(42)
    u = rng.normal(size=(8, 5))
    prior = np.array([1., 2., 1., .2, 3.])
    precision = np.linspace(.5, 2., 8)
    sigma = np.linspace(40., 200., 8)
    train = np.array([True, True, False, True, False, True, True, False])
    blocks = dict(one=slice(0, 2), two=slice(2, 5))
    covariance, factor, block_var, cross = export.conditional_components(u, prior, precision, sigma, train, blocks)
    gram = np.diag(prior) + u[train].T @ ((precision[train] / sigma[train] ** 2)[:, None] * u[train])
    expected = np.linalg.inv(gram)
    np.testing.assert_allclose(covariance, expected)
    np.testing.assert_allclose(factor @ factor.T, u @ expected @ u.T)
    np.testing.assert_allclose(sum(block_var.values()) + cross, np.diag(u @ expected @ u.T))
    # Held precision cannot update train-conditioned coefficient covariance.
    changed = precision.copy()
    changed[~train] = 1e15
    _, changed_factor, _, _ = export.conditional_components(u, prior, changed, sigma, train, blocks)
    np.testing.assert_array_equal(factor, changed_factor)


def test_covariance_includes_cross_block_correlation_instead_of_summing_independent_parts():
    u = np.array([[2., 2.], [1., 1.], [3., 1.]])
    covariance, factor, parts, cross = export.conditional_components(
        u, np.ones(2), np.ones(3), np.ones(3), np.array([True, True, False]),
        dict(left=slice(0, 1), right=slice(1, 2)))
    assert covariance[0, 1] < 0
    assert np.any(cross != 0)
    np.testing.assert_allclose(np.sum(factor ** 2, axis=1), sum(parts.values()) + cross)


def test_lines_split_at_native_fragment_boundaries_and_gaps():
    times = np.array([0., 1., 12., 13., 14.])
    fragment = np.array(['a', 'a', 'a', 'b', 'b'])
    assert [segment.tolist() for segment in export.disconnected_segments(times, fragment)] == [[0, 1], [2], [3, 4]]


def test_coefficient_layout_is_checked_instead_of_guessed():
    p = SimpleNamespace(hardware=np.empty((2, 9)), smooth=np.empty((2, 22)), labels=[1, 3], supported=[1], members=[0, 1])
    blocks = export.column_blocks(p, 38)
    assert blocks['physical_orbit'] == slice(33, 36)
    with pytest.raises(ValueError):
        export.column_blocks(p, 39)
