import numpy as np
import pytest

from leo.analysis.localization_sample_mixture import SampleVarianceMixture
from leo.analysis.robust_likelihood import student_t_logpdf, student_t_weight


def fixture():
    contrasts = np.array([[-1., 1., 0.], [-1., -1., 2.]])
    contrasts /= np.linalg.norm(contrasts, axis=1)[:, None]
    return np.array([[2., .3], [.3, 1.]]), contrasts


def test_zero_probability_recovers_original_density_and_irls():
    covariance, contrasts = fixture()
    mixture = SampleVarianceMixture(covariance, contrasts, 0., 100.)
    residual = np.array([2., -.5])
    score, precision, masks = mixture.evaluate(residual)
    assert score == pytest.approx(student_t_logpdf(residual, covariance, 4.))
    inverse = np.linalg.inv(covariance)
    weight = student_t_weight(float(residual@inverse@residual), 2, 4.)
    np.testing.assert_allclose(precision, weight*inverse)
    np.testing.assert_equal(masks, [0., 0., 0.])


def test_normalized_mask_weights_and_score_gradient():
    covariance, contrasts = fixture()
    mixture = SampleVarianceMixture(covariance, contrasts, .05, 100.)
    weights = np.exp(mixture.log_weights)
    assert weights.sum() == pytest.approx(1.)
    np.testing.assert_allclose(weights@mixture.masks, [.05]*3)
    residual = np.array([2., -.5])
    _, precision, probabilities = mixture.evaluate(residual)
    assert np.all((probabilities >= 0) & (probabilities <= 1))
    for column in range(2):
        delta = np.eye(2)[column]*1e-5
        finite = (mixture.evaluate(residual+delta)[0]-mixture.evaluate(residual-delta)[0])/2e-5
        assert finite == pytest.approx(-(precision@residual)[column], abs=1e-8)


def test_contrast_basis_rotation_invariance_and_invalid_input():
    covariance, contrasts = fixture()
    rotation = np.array([[.6, -.8], [.8, .6]])
    residual = np.array([7., -.5])
    a = SampleVarianceMixture(covariance, contrasts, .05, 100.).evaluate(residual)
    b = SampleVarianceMixture(rotation@covariance@rotation.T, rotation@contrasts,
                              .05, 100.).evaluate(rotation@residual)
    assert a[0] == pytest.approx(b[0])
    np.testing.assert_allclose(b[1], rotation@a[1]@rotation.T)
    np.testing.assert_allclose(a[2], b[2])
    with pytest.raises(ValueError):
        SampleVarianceMixture(covariance, contrasts, 1., 100.)
