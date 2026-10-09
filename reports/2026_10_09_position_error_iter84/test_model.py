import numpy as np
from model import PositionProtectedSlope, SlopePrior
from test_joint_clock import setup


def models(protected_sigma=0.25):
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    centers = np.full(len(base.bank.numbers), 50.0)
    original = SlopePrior(base, old.nodes, knots, centers, 0.5)
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    candidate = PositionProtectedSlope(base, old.nodes, knots, centers, vector,
                                       original.initial_clock, protected_sigma=protected_sigma)
    return original, candidate, vector


def test_equal_sigmas_reproduce_full_existing_objective_and_gradients():
    original, candidate, vector = models(0.5)
    clock = original.initial_clock.copy()
    clock[candidate.slope_slice] = [12, -25]
    old = original.evaluate_joint(vector, clock)
    new = candidate.evaluate_joint(vector, clock)
    for index in range(3):
        np.testing.assert_allclose(new[index], old[index], atol=1e-12, rtol=0)
    np.testing.assert_array_equal(new[3].responsibilities, old[3].responsibilities)


def test_only_slope_precision_changes_and_likelihood_is_identical():
    original, candidate, vector = models()
    assert 0 < candidate.geometry_diagnostics["rank"] <= 2
    change = candidate.precision - original.precision
    outside = change.copy()
    outside[candidate.slope_slice, candidate.slope_slice] = 0
    np.testing.assert_array_equal(outside, 0)
    assert np.linalg.eigvalsh(change).min() >= -1e-14
    clock = original.initial_clock.copy()
    clock[candidate.slope_slice] = [12, -25]
    old = original.evaluate_joint(vector, clock)
    new = candidate.evaluate_joint(vector, clock)
    np.testing.assert_allclose(new[0] - old[0], 0.5 * clock @ change @ clock, atol=1e-10)
    np.testing.assert_allclose(new[2] - old[2], change @ clock, atol=1e-10)
    np.testing.assert_array_equal(new[3].responsibilities, old[3].responsibilities)
    np.testing.assert_array_equal(new[1], old[1])


def test_projector_stays_fixed_and_complete_nuisance_gradient_is_correct():
    _, candidate, vector = models()
    frozen = candidate.precision.copy()
    clock = candidate.initial_clock.copy()
    clock[candidate.slope_slice] = [12, -25]
    _, _, gradient, _ = candidate.evaluate_joint(vector, clock)
    numeric = []
    for delta in np.eye(len(clock)) * 1e-4:
        numeric.append((candidate.evaluate_joint(vector, clock + delta)[0]
                        - candidate.evaluate_joint(vector, clock - delta)[0]) / 2e-4)
    np.testing.assert_allclose(gradient, numeric, atol=2e-4, rtol=2e-4)
    candidate.evaluate_joint(vector + 0.1, clock)
    np.testing.assert_array_equal(candidate.precision, frozen)
