import numpy as np
import pytest

from ds23_feasible_position import feasible_fit, noise_slacks, residual_slacks
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def test_slacks_match_existing_noise_gates_for_noise_and_structured_residuals():
    rng = np.random.default_rng(937)
    t = np.linspace(0, 90, 80)
    x = (t-t.mean())/np.ptp(t)
    for _ in range(30):
        noise = rng.normal(0, 80, len(t))
        for r in (noise, noise+160, noise+800*x, noise+1200*x*x,
                  noise+400*(x>0), np.cumsum(noise)):
            gate = batch_noise_screen(r[None, :], t)['noise_screen_pass'][0]
            assert (min(noise_slacks(r, t).values()) >= 0) == gate
            full = residual_slacks(r, t)
            assert (min(full.values()) >= 0) == (gate and np.sqrt(np.mean(r*r)) <= 450)


def test_constrained_fit_finds_boundary_instead_of_invalid_unconstrained_minimum():
    result = feasible_fit(lambda x: (x[0]-2)**2+(x[1]+1)**2,
                          lambda x: np.array([1-x[0], x[1]+2]),
                          [0, 0], [-3, -3], [3, 3])
    assert result['feasible']
    assert result['parameters'] == pytest.approx([1, -1], abs=.003)
    assert result['minimum_gate_slack'] >= 0


def test_infeasible_problem_never_reports_successful_association():
    result = feasible_fit(lambda x: x@x, lambda x: np.array([-1.]),
                          [0, 0], [-1, -1], [1, 1], iterations=3)
    assert not result['feasible']


def test_invalid_gates_fail_closed():
    with pytest.raises(ValueError, match='gate slacks'):
        feasible_fit(lambda x: x@x, lambda x: np.array([np.nan]),
                     [0, 0], [-1, -1], [1, 1])
