"""Prepared analytic/fake-objective checks; no recordings or numerical fitting."""

from types import SimpleNamespace

import numpy as np
import pytest
from scipy.special import ndtr

from conditional import ConditionalModes


def fixture():
    class Model:
        size = 8
        smooth_clock_count = 4
        fixed_rf_drift = False
        observations = SimpleNamespace(receiver=np.array([0, 1]))
        precision = np.diag([.25, 1., .25, 1., .01, .01])
        clock_design = np.array([[1., 0, 0, 0, 0, 0], [0, 0, 1., 0, 0, 0]])
        calls = 0

        def evaluate_joint(self, vector, clock):
            self.calls += 1
            residual = self.clock_design @ clock - np.array([2., -1.])
            value = 17. + .5 * residual @ residual + .5 * clock @ self.precision @ clock
            gradient = self.clock_design.T @ residual + self.precision @ clock
            return value, np.zeros(8), gradient, None

    return Model(), np.zeros(8), np.array([.3, .2, -.4, .1, 0, 0])


def test_scalar_factorization_gradient_and_unchanged_inputs():
    model, vector, clock = fixture()
    before = clock.copy()
    modes = ConditionalModes(model, vector, clock, arm="zero-c")
    assert model.calls == 1
    assert modes.scalar(0, modes.amplitudes[0])["difference"] == 0
    first, second = modes.scalar(0, 1.2), modes.scalar(1, -.8)
    joint = clock.copy(); joint[0] = 1.2; joint[2] = -.8
    exact = model.evaluate_joint(vector, joint)[0]
    assert modes.anchor_value + first["difference"] + second["difference"] == pytest.approx(exact, abs=1e-12, rel=0)
    assert first["gradient"] == pytest.approx(1.25 * 1.2 - 2)
    assert second["gradient"] == pytest.approx(1.25 * -.8 + 1)
    np.testing.assert_array_equal(clock, before)
    np.testing.assert_array_equal(vector, np.zeros(8))
    assert modes.intervals == ((-2000., 2000.), (-2000., 2000.))
    assert not modes.clock.flags.writeable


def test_analytic_gaussian_prior_normalization_counted_once():
    model, vector, clock = fixture()
    modes = ConditionalModes(model, vector, clock, arm="fitted-c")
    lam, h = .25, 1.25
    logs, exact = [], 17. + .5 * (clock[1]**2 + clock[3]**2)
    for r, y in enumerate((2., -1.)):
        a = modes.amplitudes[r]
        lower, upper = modes.intervals[r]
        mass = ndtr(np.sqrt(h) * (upper - y / h)) - ndtr(np.sqrt(h) * (lower - y / h))
        f_anchor = .5 * (a - y)**2 + .5 * lam * a*a
        minimum = .5 * y*y - .5 * y*y / h
        logs.append(f_anchor - minimum + .5 * np.log(2*np.pi/h) + np.log(mass))
        exact += minimum + .5 * np.log(h / lam) - np.log(mass)
    assert modes.marginal_score(logs) == pytest.approx(exact, abs=1e-12, rel=0)


@pytest.mark.parametrize("failure", ["cross-prior", "cross-design", "unequal", "improper", "ambiguous", "static-c", "rf-time", "box"])
def test_invalid_block_rejected_before_objective(failure):
    model, vector, clock = fixture()
    model.precision = model.precision.copy(); model.clock_design = model.clock_design.copy()
    if failure == "cross-prior": model.precision[0, 2] = model.precision[2, 0] = .01
    if failure == "cross-design": model.clock_design[1, 0] = .1
    if failure == "unequal": model.precision[2, 2] = .3
    if failure == "improper": model.precision[0, 0] = model.precision[2, 2] = 0
    if failure == "ambiguous": model.precision[:4, :4] = np.eye(4)
    if failure == "static-c": vector[6] = 1
    if failure == "rf-time": clock[-1] = 1
    if failure == "box": clock[0] = 2001
    with pytest.raises(ValueError): ConditionalModes(model, vector, clock, arm="zero-c")
    assert model.calls == 0


def test_domain_failure_and_anchor_callback_mutation_isolation():
    model, vector, clock = fixture()
    original = model.evaluate_joint
    def callback(v, c):
        result = original(v, c)
        v[:] = 99; c[:] = 99
        return result
    model.evaluate_joint = callback
    modes = ConditionalModes(model, vector, clock, arm="zero-c")
    np.testing.assert_array_equal(modes.clock, clock)
    np.testing.assert_array_equal(modes.vector, vector)
    with pytest.raises(ValueError): modes.scalar(0, 2001)
    with pytest.raises(ValueError): modes.marginal_score([0, np.nan])
