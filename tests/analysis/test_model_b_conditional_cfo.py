"""Unit frequency density, explicit event mass, full-bank budget and analytic tails."""

import numpy as np
import pytest

from leo.analysis.regional_position_score import ALIAS_HZ, zero_sum_basis
from leo.analysis.research import model_b_conditional_cfo as core
from leo.contracts.regional_position import POSITION_SCORES

CONFIG = POSITION_SCORES["V16"]


@pytest.mark.parametrize("visible_row", [[1, 1, 1], [1, 0, 1], [0, 0, 0]])
def test_periodic_quadrature_unit_CFO_and_exact_legacy_single_event_mass(visible_row):
    count = 16384
    measured = np.linspace(-ALIAS_HZ/2, ALIAS_HZ/2, count, endpoint=False)
    prediction = np.tile([ALIAS_HZ*.49, 100., 500.], (count, 1))
    visible = np.tile(visible_row, (count, 1)).astype(bool)
    sigma, q = np.full(count, 125.), np.full(3, 1.6/3)
    normalized, details = core.score(measured, prediction, visible, sigma, q, CONFIG,
                                      conditional=True)
    legacy, old = core.score(measured, prediction, visible, sigma, q, CONFIG,
                             conditional=False)
    assert np.exp(-details["row_nll"]).mean()*ALIAS_HZ == pytest.approx(1., abs=1e-10)
    expected = float(np.exp(details["log_integrated_event_mass"][0]))
    assert 0 < expected < 1
    assert np.exp(-old["row_nll"]).mean()*ALIAS_HZ == pytest.approx(expected, abs=1e-10)
    assert normalized.nll-legacy.nll == pytest.approx(
        details["log_integrated_event_mass"].sum(), abs=1e-9)
    np.testing.assert_allclose(normalized.responsibilities, legacy.responsibilities, atol=0)
    np.testing.assert_allclose(normalized.prediction_gradient, legacy.prediction_gradient, atol=0)
    if not any(visible_row):
        assert not normalized.responsibilities.any()
        assert not details["sigma_log_gradient"].any()
        assert not details["detection_probability_gradient"].any()


@pytest.mark.parametrize("conditional", [False, True])
def test_catalogue_budget_jacobian_and_normalized_sigma_q_gradients(conditional):
    basis = zero_sum_basis(5)
    theta = np.array([.2, -.1, .3, -.4])
    q, jacobian, _ = core.detection_probabilities(basis, theta, 1.6)
    assert q.sum() == pytest.approx(1.6, abs=1e-12)
    np.testing.assert_allclose(jacobian.sum(axis=0), 0, atol=1e-15)
    measured = np.array([15., 25., 125., -99.])
    prediction = np.tile(np.array([10., 100., 180., -50., 45.]), (4, 1))
    visible = np.ones_like(prediction, bool)
    visible[0, 1] = False
    visible[3] = False
    log_sigma = np.array([.1, -.2, .15, .3])

    def evaluate(t, log_width):
        probabilities = core.detection_probabilities(basis, t, 1.6)[0]
        return core.score(measured, prediction, visible, 125*np.exp(log_width), probabilities,
                          CONFIG, conditional=conditional)

    _, details = evaluate(theta, log_sigma)
    actual = np.r_[jacobian.T@details["detection_probability_gradient"],
                   details["sigma_log_gradient"]]
    vector = np.r_[theta, log_sigma]
    finite = []
    for i in range(len(vector)):
        delta = np.eye(len(vector))[i]*1e-5
        plus, minus = vector+delta, vector-delta
        finite.append((evaluate(plus[:4], plus[4:])[0].nll-
                       evaluate(minus[:4], minus[4:])[0].nll)/2e-5)
    np.testing.assert_allclose(actual, finite, atol=2e-8, rtol=1e-6)


def test_invalid_inventory_sigma_probability_and_budget_fail():
    p, visible = np.zeros((2, 3)), np.ones((2, 3), bool)
    with pytest.raises(ValueError, match="full-bank q budget"):
        core.score([0, 1], p, visible, [125, 125], [.1, .1, .1], CONFIG, conditional=True)
    with pytest.raises(ValueError, match="narrow-Gaussian"):
        core.score([0, 1], p, visible, [125, 1001], np.full(3, 1.6/3), CONFIG, conditional=True)
    with pytest.raises(ValueError, match="detection budget"):
        core.detection_probabilities(zero_sum_basis(2), [0], 2)
