import numpy as np
import pytest
from scipy.optimize import OptimizeResult
from test_regional_position_score import synthetic_inputs

from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_score import PositionObjective
from leo.contracts.regional_position import POSITION_SCORES, PositionOrbitBank


def test_solver_success_is_not_attached_to_a_different_returned_state(monkeypatch):
    from types import SimpleNamespace

    from leo.analysis import regional_position_fit as module
    from leo.analysis.regional_position_score import zero_sum_basis

    class TwoWells:
        size = 10
        basis = zero_sum_basis(3)
        bank = SimpleNamespace(numbers=np.arange(3), nodes_s=np.array([-21.0, 31.0]))
        observations = SimpleNamespace(times_s=np.array([0.0, 10.0]))
        prior = SimpleNamespace(radius_km=250.0)

        def evaluate(self, vector):
            x = vector[2] / 200
            value = (x * x - 1) ** 2 + 0.3 * (x * x * x / 3 - x)
            gradient = np.zeros(self.size)
            gradient[2] = (x * x - 1) * (4 * x + 0.3) / 200
            terms = SimpleNamespace(responsibilities=np.ones((1, 1)), residual_hz=np.ones((1, 1)))
            return value, gradient, terms

    def fake_minimize(fun, z, **kwargs):
        fun(z)
        trial = z.copy()
        trial[0] = 0.9
        fun(trial)
        return OptimizeResult(x=z, success=True, status=0, nit=1)

    monkeypatch.setattr(module, "minimize", fake_minimize)
    seed = np.zeros(10)
    seed[2] = -200
    diagnostics = {}
    answer = fit_position(TwoWells(), seed, fixed_position=True, diagnostics=diagnostics)
    assert diagnostics["solver_success"]
    assert diagnostics["terminal"]["converged"]
    assert not answer.converged
    assert answer.objective < diagnostics["terminal"]["objective"]
    assert answer.vector[2] == 180
    assert answer.stop_reason == "optimizer-success-returned-state-nonstationary"


@pytest.mark.parametrize("name", ["T1AT", "V16"])
def test_projected_boundary_seed_receives_a_feasible_evaluation(name):
    observations, bank, prior = synthetic_inputs()
    indices = np.arange(14) % 3
    bank = PositionOrbitBank(
        np.arange(100, 114), bank.nodes_s, bank.position_km[indices], bank.velocity_km_s[indices]
    )
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES[name])
    # A real coarse-search seed whose Helmert reconstruction overshoots +20 s
    # by one ulp. Even a one-iteration fit must evaluate the feasible seed.
    shifts = np.array([-16, 6, 20, -2, 2, -6, 10, 19, 16, 0, -10, 9, 8, 10])
    start = np.zeros(objective.size)
    start[:2] = [3, -5]
    start[7] = shifts.mean()
    start[8:] = objective.basis.T @ shifts
    fit = fit_position(
        objective, start, fixed_position=True, maximum_seconds=5, maximum_iterations=1
    )
    assert fit.evaluations >= 1
    assert np.isfinite(fit.objective)
    assert np.max(abs(fit.vector[7] + objective.basis @ fit.vector[8:])) <= 20


@pytest.mark.parametrize("name", ["T1AT", "V16"])
def test_fixed_point_profile_and_rf_ablation(name):
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES[name])
    start = np.array([3, -5, 100, 0, -100, 0, 35, 0.3, 0, 0], dtype=float)
    fits = []
    for arm in ("fitted-c", "zero-c"):
        seed = start.copy()
        if arm == "zero-c":
            seed[6] = 0
        initial = objective.evaluate(seed)[0]
        fit = fit_position(objective, start, rf_arm=arm, fixed_position=True, maximum_seconds=10)
        assert fit.objective < initial
        np.testing.assert_array_equal(fit.vector[:2], start[:2])
        assert fit.posterior_rms_hz < 100
        assert 0 <= fit.signal_windows <= len(observations.window_ids)
        assert fit.stationarity >= 0 and np.isfinite(fit.stationarity)
        if arm == "zero-c":
            assert fit.vector[6] == 0
        fits.append(fit)
    assert objective.observations is observations  # no per-arm selection
    assert fits[0].objective <= fits[1].objective + 1e-5


def test_continuous_fit_keeps_both_disks_and_timing_bounds():
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES["V16"])
    start = np.array([3.1, -5.2, 0, 0, 0, 0, 0, 0.3, 0, 0], dtype=float)
    fit = fit_position(
        objective, start, maximum_seconds=10, local_center=start[:2], local_radius_km=1
    )
    assert np.linalg.norm(fit.vector[:2] - start[:2]) <= 1 + 1e-6
    assert np.linalg.norm(fit.vector[:2]) <= prior.radius_km
    assert abs(fit.vector[7]) <= 10
    assert np.max(abs(fit.vector[7] + objective.basis @ fit.vector[8:])) <= 20 + 1e-6
    assert fit.objective <= objective.evaluate(start)[0]


def test_deadline_is_not_success_and_bad_bounds_fail():
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES["V16"])
    with pytest.raises(TimeoutError):
        fit_position(objective, np.zeros(objective.size), maximum_seconds=1e-12)
    with pytest.raises(ValueError, match="outside prior"):
        fit_position(objective, np.r_[300, np.zeros(objective.size - 1)])
    with pytest.raises(ValueError, match="local center"):
        fit_position(objective, np.zeros(objective.size), local_radius_km=10)
