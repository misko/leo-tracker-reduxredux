import numpy as np
import pytest
from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.robust_likelihood import student_t_logpdf
from shared_scale_port import SharedScalePort


class Port:
    candidate_count = 2
    def __init__(self, name, A, y, C, prior):
        self.observation_ids = tuple(f'{name}:{i}' for i in range(len(y)))
        self.A = A; self.observation = y; self.C = C; self.prior = prior
    def predict_selected(self, x, index): return Prediction(self.A@x, self.A, self.C)
    def score_selected(self, x, index): return self.prior+student_t_logpdf(self.observation-self.A@x, self.C, 4.)


def members():
    rng = np.random.default_rng(711)
    return [(Port(str(i), rng.normal(size=(d, 3)), rng.normal(size=d), np.eye(d)*(i+1), -2.-i), 0)
            for i, d in enumerate((2, 4))]


def test_normalized_group_density_preserves_physical_priors():
    group = SharedScalePort(members()); x = np.array([.3, -.4, .2]); pred = group.predict_selected(x, 0)
    expected = -5+student_t_logpdf(group.observation-pred.mean, pred.covariance, 4.)
    np.testing.assert_allclose(group.score_selected(x, 0), expected, atol=1e-12)
    assert np.isneginf(group.score_all(x)[1])


def test_singleton_exact_score_and_prediction():
    p, i = members()[0]; group = SharedScalePort([(p, i)]); x = np.zeros(3)
    assert group.score_selected(x, 0) == p.score_selected(x, i)
    np.testing.assert_array_equal(group.predict_selected(x, 0).jacobian, p.A)


def test_group_gradient_matches_finite_difference():
    group = SharedScalePort(members()); x = np.array([.3, -.4, .2]); p = group.predict_selected(x, 0)
    r = group.observation-p.mean; v = np.linalg.solve(p.covariance, r)
    gradient = (4+len(r))/(4+r@v)*p.jacobian.T@v
    numeric = []
    for j in range(3):
        s = np.eye(3)[j]*1e-5; numeric.append((group.score_selected(x+s, 0)-group.score_selected(x-s, 0))/2e-5)
    np.testing.assert_allclose(gradient, numeric, atol=1e-8)


def test_duplicate_evidence_and_background_members_rejected():
    m = members()[0]
    with pytest.raises(ValueError): SharedScalePort([m, m])
    with pytest.raises(ValueError): SharedScalePort([(m[0], m[0].candidate_count)])
