import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.localization_shared_scale import SelectedResidualBlock, SharedScalePort
from leo.analysis.robust_likelihood import student_t_logpdf, student_t_weight


def block(y, c, h, prefix):
    return SelectedResidualBlock(y, tuple(prefix+str(i) for i in range(len(y))), c,
                                 lambda x: Prediction(h@x, h, c, True), np.log(.4))


def test_singleton_and_group_match_dense_normalized_density_and_gradient():
    y1, c1, h1 = np.array([2., -1.]), np.array([[2., .3], [.3, 1.]]), np.eye(2)
    y2, c2, h2 = np.array([3.]), np.array([[.5]]), np.array([[.3, -.7]])
    b1, b2 = block(y1, c1, h1, 'a'), block(y2, c2, h2, 'b')
    x = np.array([.2, -.4])
    single = SharedScalePort([b1])
    np.testing.assert_allclose(single.score_selected(x, 0),
                               student_t_logpdf(y1-h1@x, c1, 4.)+np.log(.4), rtol=1e-12)
    group = SharedScalePort([b1, b2])
    dense_c = np.zeros((3, 3))
    dense_c[:2, :2], dense_c[2:, 2:] = c1, c2
    residual = np.r_[y1, y2]-np.vstack([h1, h2])@x
    expected = student_t_logpdf(residual, dense_c, 4.)+2*np.log(.4)
    np.testing.assert_allclose(group.score_selected(x, 0), expected, rtol=1e-12)
    np.testing.assert_allclose(SharedScalePort([b2, b1]).score_selected(x, 0), expected)
    p = group.predict_selected(x, 0)
    r = group.observation-p.mean
    analytic = student_t_weight(float(r@r), len(r), 4.)*p.jacobian.T@r
    for j in range(2):
        step = np.eye(2)[j]*1e-5
        finite = (group.score_selected(x+step, 0)-group.score_selected(x-step, 0))/2e-5
        np.testing.assert_allclose(finite, analytic[j], atol=1e-9)


def test_shared_precision_differs_from_independent_scales_and_rejects_reuse():
    b1 = block(np.array([.1]), np.eye(1), np.ones((1, 2)), 'a')
    b2 = block(np.array([10.]), np.eye(1), np.ones((1, 2)), 'b')
    x = np.zeros(2)
    independent = sum(SharedScalePort([b]).score_selected(x, 0) for b in [b1, b2])
    assert abs(SharedScalePort([b1, b2]).score_selected(x, 0)-independent) > .1
    with pytest.raises(ValueError, match='reused'):
        SharedScalePort([b1, b1])
    with pytest.raises(ValueError):
        SharedScalePort([])
