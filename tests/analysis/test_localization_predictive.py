import math

import numpy as np
import pytest

from leo.analysis.localization_predictive import conditional_student_logpdf


def density(r, c, nu):
    n = len(r)
    return (math.lgamma((nu+n)/2)-math.lgamma(nu/2)-n/2*math.log(nu*math.pi)
            - .5*np.linalg.slogdet(c)[1]
            - (nu+n)/2*math.log1p(float(r @ np.linalg.solve(c, r))/nu))


def test_conditional_matches_joint_minus_marginal():
    rng = np.random.default_rng(51)
    a = rng.normal(size=(7, 7))
    c = a @ a.T+np.eye(7)
    r = rng.normal(size=7)
    for k in [1, 3, 6]:
        assert conditional_student_logpdf(r, c, k) == pytest.approx(
            density(r, c, 4)-density(r[:k], c[:k, :k], 4), abs=1e-12)


def test_training_coordinate_change_leaves_conditional_density_unchanged():
    r = np.array([2., -1., 3.])
    c = np.array([[2., .1, .3], [.1, 4., -.2], [.3, -.2, 3.]])
    a = np.array([[2., 1., 0.], [-1., 3., 0.], [0., 0., 1.]])
    assert conditional_student_logpdf(a@r, a@c@a.T, 2) == pytest.approx(
        conditional_student_logpdf(r, c, 2), abs=1e-12)


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        conditional_student_logpdf([1., 2.], np.eye(2), 2)
    with pytest.raises(np.linalg.LinAlgError):
        conditional_student_logpdf([1., 2.], [[1., 2.], [2., 1.]], 1)
