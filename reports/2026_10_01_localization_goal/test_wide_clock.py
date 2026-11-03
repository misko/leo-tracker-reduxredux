"""Isolated prior penalty, derivative and curvature checks."""
import numpy as np
import pytest
from fixed_reference_nuisance import ConditionalObjective
from wide_clock_objective import WideClockObjective, SIGMAS

@pytest.mark.parametrize('arm', SIGMAS)
def test_only_clock_prior_changes(monkeypatch, arm):
    def fake_init(self, unit, mode):
        assert mode == 'control'
        self.initial = np.array([1., 2., 3., 4., 5., 6.])
        self.epochs = [5]
        self.precision = np.array([0., 0., 1., 4., 4., 4.])
        self.ports = []
        self.assignments = []
    monkeypatch.setattr(ConditionalObjective, '__init__', fake_init)
    model = WideClockObjective('synthetic', arm)
    expected = np.array([0., 0., 1 / SIGMAS[arm]**2, 4., 4., 4.])
    np.testing.assert_array_equal(model.initial, [1, 2, 3, 4, 5, 6])
    np.testing.assert_array_equal(model.precision, expected)
    value, gradient = model.evaluate(model.initial)
    assert value == pytest.approx(.5 * np.sum(expected * model.initial**2))
    np.testing.assert_allclose(gradient, expected * model.initial)
    np.testing.assert_array_equal(model.metric(), np.diag(expected))

def test_unknown_arm():
    with pytest.raises(ValueError):
        WideClockObjective('unused', 'unknown')
