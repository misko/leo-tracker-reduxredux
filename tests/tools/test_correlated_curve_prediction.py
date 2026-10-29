import numpy as np
import pytest

from correlated_curve_prediction import shared_kernel, gaussian, conditional, randomized_blocks


def test_shared_measurements_are_not_counted_as_independent():
    cov = np.eye(2) + shared_kernel([0, 0], [1, 1], 10, 5)
    joint = gaussian([1, 1], cov)
    independent = gaussian([1, 1], np.eye(2))
    assert joint['quadratic'] == pytest.approx(2/201)
    assert joint['quadratic'] < independent['quadratic']
    assert joint['logdet'] == pytest.approx(np.log(201))
    assert shared_kernel([0, 0], [1, 2], 10, 5)[0, 1] == 0


def test_conditional_matches_gaussian_identity_and_does_not_fit_withheld_y():
    cov = np.array([[4., 2.], [2., 9.]])
    a = conditional([3., 7.], cov, [True, False])
    b = conditional([3., 700.], cov, [True, False])
    assert a['prediction_hz'][0] == b['prediction_hz'][0] == 1.5
    assert a['prediction_sigma_hz'][0] == pytest.approx(np.sqrt(8))
    assert a['objective'] == pytest.approx(gaussian([3., 7.], cov)['objective']-gaussian([3.], [[4.]])['objective'])


def test_random_blocks_keep_simultaneous_channels_together():
    times = np.repeat(np.arange(60., 150., 2.), 2)
    mask, receipt = randomized_blocks(times)
    np.testing.assert_array_equal(mask[::2], mask[1::2])
    np.testing.assert_array_equal(mask, randomized_blocks(times)[0])
    assert mask.any() and (~mask).any()
    assert receipt['seed'] == 20261029


def test_invalid_covariance_is_not_silently_repaired():
    with pytest.raises(ValueError, match='symmetric'):
        gaussian([1., 2.], [[1., 2.], [0., 1.]])
    with pytest.raises(np.linalg.LinAlgError):
        gaussian([1., 2.], [[1., 2.], [2., 1.]])


def test_dense_covariance_matches_existing_predictive_likelihood():
    from ds23_predictive_linear import predictive_residual
    rng=np.random.default_rng(19)
    y=rng.normal(size=7);design=rng.normal(size=(7,3));gram=np.diag([2.,3.,4.])
    sigma=np.linspace(1.,2.,7);groups=np.array([0,0,0,1,1,1,1])
    cov=np.diag(sigma**2)+design@np.linalg.solve(gram,design.T)+9*(groups[:,None]==groups[None,:])
    direct=gaussian(y,cov)
    legacy=predictive_residual(y,design,gram,sigma,groups,bias_sigma=3.)
    assert direct['objective']==pytest.approx(legacy['objective'],abs=1e-10)
