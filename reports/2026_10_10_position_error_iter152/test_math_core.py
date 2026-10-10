"""Synthetic analytic oracles; no recording or reference-evaluation adapter."""

import numpy as np
import pytest
from scipy.special import logsumexp, ndtr

from math_core import amplitude_interval, interior_laplace, observed_block


def test_observed_mixture_derivatives_include_missing_information():
    b = np.array([0.2, -0.1])
    y = np.array([0.5, -0.4])
    means = np.array([[0.0, 1.0], [-1.0, 0.7]])
    design = np.array([[[1., .3], [.2, -.8]], [[-.4, 1.], [.6, .1]]])
    masses = np.array([[.4, .5], [.3, .6]])
    precision = np.array([[2., .2], [.2, 1.]])
    def evaluate(v):
        return observed_block(v, y, means, design, masses, .02, .8, precision)
    result = evaluate(b)
    step = 1e-5
    for j in range(2):
        delta = np.eye(2)[j] * step
        left, right = evaluate(b-delta), evaluate(b+delta)
        assert (right['value']-left['value'])/(2*step) == pytest.approx(result['gradient'][j], abs=1e-9, rel=0)
        np.testing.assert_allclose((right['gradient']-left['gradient'])/(2*step), result['hessian'][:, j], atol=1e-8, rtol=0)
    assert np.linalg.eigvalsh(result['responsibility_covariance']).min() >= -1e-12


def test_gaussian_integration_exact_and_constant_design_score_difference():
    design = np.array([[1., .2], [.3, -1.], [-.4, .7]])
    precision = np.diag([2., 3.])
    sigma = .8
    hessian = precision + design.T @ design / sigma**2
    covariance = sigma**2 * np.eye(3) + design @ np.linalg.solve(precision, design.T)
    corrections = []
    for residual in (np.array([1., .2, -.3]), np.array([-.7, .1, .9])):
        mode = np.linalg.solve(hessian, design.T @ residual / sigma**2)
        result = observed_block(mode, residual, np.zeros((3,1)), design[:,None,:], np.ones((3,1)), 0., sigma, precision)
        marginal = interior_laplace(result['value'], hessian, precision)
        exact = .5 * (3*np.log(2*np.pi) + np.linalg.slogdet(covariance)[1] + residual @ np.linalg.solve(covariance, residual))
        assert marginal == pytest.approx(exact, abs=1e-12, rel=0)
        corrections.append(marginal-result['value'])
    assert corrections[0] == pytest.approx(corrections[1], abs=1e-12, rel=0)


def test_basis_units_invariance_and_fixed_mode_quadrature():
    hessian, precision = np.array([[5., .4],[.4, 2.]]), np.diag([1., .5])
    transform = np.array([[2., .3],[-.4, .2]])
    assert interior_laplace(3., hessian, precision) == pytest.approx(
        interior_laplace(3., transform.T@hessian@transform, transform.T@precision@transform), abs=1e-12, rel=0)
    # Independent 1D Gaussian-prior quadrature agrees with its exact Gaussian marginal.
    nodes, weights = np.polynomial.hermite.hermgauss(48)
    prior_sigma, sigma, measured = .7, 1.1, .4
    b = np.sqrt(2)*prior_sigma*nodes
    log_likelihood = -.5*((measured-b)/sigma)**2-np.log(sigma*np.sqrt(2*np.pi))
    integrated = -logsumexp(np.log(weights)-.5*np.log(np.pi)+log_likelihood)
    exact = .5*np.log(2*np.pi*(prior_sigma**2+sigma**2)) + .5*measured**2/(prior_sigma**2+sigma**2)
    assert integrated == pytest.approx(exact, abs=1e-12, rel=0)


def test_mixture_indefiniteness_is_not_repaired_by_a_ridge():
    result = observed_block(np.zeros(1), np.zeros(1), np.array([[-3.,3.]]), np.ones((1,2,1)), np.full((1,2), .5), 0., 1., np.array([[.2]]))
    assert result['complete_curvature'][0,0] == pytest.approx(1.)
    assert result['hessian'][0,0] == pytest.approx(-7.8)
    with pytest.raises(np.linalg.LinAlgError):
        interior_laplace(result['value'], result['hessian'], np.array([[.2]]))


def test_fixed_gaussian_design_finite_box_is_not_an_exact_noop():
    # Unit noise and unit Gaussian prior give posterior N(y/2, 1/2).
    # Both modes lie strictly inside [-1,1], but the missing posterior mass
    # differs. Interior mode alone does not justify the unbounded identity.
    corrections = []
    for measured in (0., 1.):
        posterior_mean = measured / 2
        posterior_sigma = np.sqrt(.5)
        posterior_mass = (ndtr((1-posterior_mean)/posterior_sigma)
                          - ndtr((-1-posterior_mean)/posterior_sigma))
        corrections.append(.5*np.log(2)-np.log(posterior_mass))
    assert corrections[1] > corrections[0]


def test_receiver_disjoint_mixture_has_separable_value_and_hessian():
    b = np.array([.2, -.3])
    measured = np.array([.4, -.7])
    means = np.array([[0., 1.], [-1., .5]])
    design = np.array([[[1., 0.], [1., 0.]], [[0., .8], [0., .8]]])
    masses = np.full((2, 2), .45)
    precision = np.diag([2., 3.])
    full = observed_block(b, measured, means, design, masses, .02, .8, precision)
    separate = [observed_block(
        b[r:r+1], measured[r:r+1], means[r:r+1],
        design[r:r+1, :, r:r+1], masses[r:r+1], .02, .8,
        precision[r:r+1, r:r+1]) for r in (0, 1)]
    assert full['value'] == pytest.approx(sum(x['value'] for x in separate), abs=1e-12, rel=0)
    assert full['hessian'][0, 1] == pytest.approx(0., abs=1e-12, rel=0)
    for r in (0, 1):
        assert full['gradient'][r] == pytest.approx(separate[r]['gradient'][0], abs=1e-12, rel=0)
        assert full['hessian'][r, r] == pytest.approx(separate[r]['hessian'][0, 0], abs=1e-12, rel=0)


def test_actual_coefficient_box_intersection_not_new_amplitude_box():
    direction = np.array([.6, -.8])
    remaining = np.array([100., -200.])
    lower, upper = amplitude_interval(direction, remaining)
    for amplitude in (lower, upper, .5*(lower+upper)):
        assert np.max(abs(remaining+amplitude*direction)) <= 2000 + 1e-10
    with pytest.raises(ValueError):
        amplitude_interval(np.array([1.,0.]), np.array([0.,2001.]))
