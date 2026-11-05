import numpy as np
import pytest

from leo.analysis.localization_v3.feasible import feasible_fit, noise_slacks, residual_slacks
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def test_constrained_optimizer_respects_gates_when_unconstrained_minimum_is_invalid():
    def objective(x):
        return (x[0]-2.)**2+(x[1]+1.)**2
    def gates(x):
        return np.array([.5-x[0], x[1]+.5])
    result = feasible_fit(objective, gates, [0., 0.], [-5., -5.], [5., 5.])
    assert result['feasible'] and result['minimum_gate_slack'] >= 0
    np.testing.assert_allclose(result['parameters'], [.5, -.5], atol=1e-3)


def test_solver_termination_does_not_create_feasibility():
    result = feasible_fit(lambda x: x@x, lambda x: np.array([-1.]),
                          [0., 0.], [-1., -1.], [1., 1.], iterations=2)
    assert not result['feasible'] and result['minimum_gate_slack'] == -1.
    with pytest.raises(ValueError, match='nonempty'):
        feasible_fit(lambda x: x@x, lambda x: [], [0.], [-1.], [1.])


@pytest.mark.parametrize('structure', ['noise', 'mean', 'slope', 'step'])
def test_slacks_preserve_original_noise_screen_decision(structure):
    t = np.arange(100.)
    y = np.random.default_rng(2301).normal(size=100)
    if structure == 'mean':
        y += 10
    elif structure == 'slope':
        y += (t-50)*.5
    elif structure == 'step':
        y += (t >= 50)*10
    expected = batch_noise_screen(y[None, :], t)['noise_screen_pass'][0]
    assert (min(noise_slacks(y, t).values()) >= 0) == expected
    assert residual_slacks(y, t)['rms'] == pytest.approx(1-np.sqrt(np.mean(y*y))/450)
