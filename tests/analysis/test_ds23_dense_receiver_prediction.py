from types import SimpleNamespace
import numpy as np
import pytest
from probe_ds23_dense_receiver_prediction import derivative, folds, predictive, expand
from dsx01_satellite_prior_controls import SatellitePriorControls


def test_actual_runtime_prediction_includes_phase_and_all_five_shape_coordinates():
    # The observable is reference-frequency Hz; hardware/fragment columns are excluded.
    p = SimpleNamespace(hardware=np.zeros((1, 1)), smooth=np.zeros((1, 1)), members=[0], q=np.array([2.]))
    p.calculate = lambda x: dict(intercept=np.array([10.]),
        features=np.array([[1000., 2000., 1., 2., 3., 5., 7., 11., 1000.]]),
        coefficient=np.ones(9), elevation=np.array([42.]))
    frequency, elevation = SatellitePriorControls.conditional_frequency(p, None)
    np.testing.assert_allclose(frequency, [24.5])
    np.testing.assert_array_equal(elevation, [42.])


def test_derivative_includes_added_physical_columns_and_freezes_coefficients():
    rng = np.random.default_rng(32)
    d = rng.normal(size=(12, 2))
    extra = rng.normal(size=(12, 5, 2))
    a = rng.normal(size=5)
    p = SimpleNamespace(q=np.linspace(.9, 1.1, 12))
    p.calculate = lambda x: dict(intercept=d @ x, features=np.einsum('nck,k->nc', extra, x), coefficient=a + x.sum())
    expected = p.q[:, None] * d + np.einsum('nck,c->nk', extra, a)
    np.testing.assert_allclose(derivative(p, np.array([2., 3.]), a), expected, rtol=1e-10, atol=1e-10)


def test_complete_predictive_covariance_matches_independent_dense_normal_solution():
    rng = np.random.default_rng(41)
    n, width = 30, 7
    d, u = rng.normal(size=(n, 2)), rng.normal(size=(n, width))
    train = np.arange(n) < 20
    test = ~train
    noise = np.linspace(2, 5, n)
    prior = np.linspace(.5, 2, width)
    residual = rng.normal(size=n)
    p = SimpleNamespace(q=np.ones(n), keep=train, labels=[7], flat_labels=np.zeros(n, int),
        flat_times=np.arange(n), noise_groups=np.zeros(n, int), point_noise=noise)
    p.calculate = lambda x: dict(intercept=d @ x, features=u, coefficient=np.zeros(width),
        coefficient_prior_precision=prior, noise_precision=np.array([.7]), conditional_residual_hz=residual)
    result = predictive(p, np.zeros(2), train, test, np.array([.8]), 7)
    design = np.column_stack((d, u))
    weights = .8 * .7 / noise[train]**2
    gram = np.diag(np.r_[0., 0., prior]) + design[train].T @ np.diag(weights) @ design[train]
    covariance = np.diag(2 * noise[test]**2) + design[test] @ np.linalg.inv(gram) @ design[test].T
    expected = residual[test] @ np.linalg.solve(covariance, residual[test]) + np.linalg.slogdet(covariance)[1] + test.sum() * np.log(2 * np.pi)
    np.testing.assert_allclose(result['negative_twice_log_density'], expected)
    p.keep = np.ones(n, bool)
    with pytest.raises(ValueError, match='training-only'):
        predictive(p, np.zeros(2), train, test, np.array([.8]), 7)


def test_folds_select_support_without_values_and_partition_original_mask():
    rows = [dict(candidate_index=j) for j in (0, 0, 1, 1, 2)]
    tracks = [dict(receiver=r) for r in (1, 2, 1, 2, 1)]
    p = SimpleNamespace(labels=[0, 1, 2], rows=rows, members=list(range(5)),
        slices=[slice(4*k, 4*k+4) for k in range(5)], scan=SimpleNamespace(tracks=tracks))
    keep = np.ones(20, bool)
    keep[0] = False
    result = folds(p, keep, maximum=1)
    assert len(result) == 2 and all(r['family'] == 1 for r in result)
    for r in result:
        assert not np.any(r['train'] & r['test'])
        np.testing.assert_array_equal(r['train'] | r['test'], keep)


def test_RX1_only_extra_covariance_preserves_RX2_and_does_not_mutate_input():
    tracks = [dict(times=np.arange(20.), receiver=r, channel=ch) for r, ch in ((1, 1), (2, 7))]
    slow = [np.ones((20, 3)) for _ in tracks]
    scan = SimpleNamespace(tracks=tracks, rx_basis=slow)
    node = dict(seed=dict(state=dict(smooth=np.ones((2, 3)))))
    changed, seed = expand(scan, node, 'fast_rx1')
    assert np.linalg.norm(changed.rx_basis[0][:, 3:]) > 0
    np.testing.assert_array_equal(changed.rx_basis[1][:, 3:], 0)
    assert scan.rx_basis[0].shape == (20, 3) and node['seed']['state']['smooth'].shape == (2, 3)
    assert seed['seed']['state']['smooth'].shape[1] == changed.rx_basis[0].shape[1]
