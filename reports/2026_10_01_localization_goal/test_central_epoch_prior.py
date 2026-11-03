"""Check actual normalized prior and its matched central shrinkage."""
import numpy as np

from leo.analysis.localization_prior import ScalarStudentPriorPort


def test_central_curvature_and_tail_derivative():
    port = ScalarStudentPriorPort(0, 1, .625, 'epoch')
    def nll(x):
        return -port.score_selected(np.array([x]), 0)
    step = .0001
    curvature = (nll(step)-2*nll(0)+nll(-step))/step**2
    assert abs(curvature-4) < 1e-6
    for x in [-4., -.5, 0., .5, 4.]:
        finite = (nll(x+step)-nll(x-step))/(2*step)
        assert abs(finite-5*x/(1.25+x*x)) < 1e-7
    assert nll(4)-nll(0) < 2*4**2


def test_prior_mass_and_variance():
    # Independent closed form of normalized t4 density, transformed to a
    # finite interval for normalization and variance integration.
    nodes, weights = np.polynomial.legendre.leggauss(200)
    angles = nodes*np.pi/2
    x = np.tan(angles)
    port = ScalarStudentPriorPort(0, 1, .625, 'epoch')
    density = np.exp([port.score_selected(np.array([v]), 0) for v in x])
    integral_weights = weights*np.pi/2/np.cos(angles)**2
    assert abs(integral_weights@density-1) < 1e-9
    assert abs(integral_weights@(density*x*x)-.625) < 1e-8
