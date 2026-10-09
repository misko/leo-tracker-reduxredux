"""Known-answer constrained quadratic checks; no recording access or fit."""

from types import SimpleNamespace

import numpy as np
import pytest
from coordinate_polish import polish, projected_gradient

from leo.analysis.hard60_bounded_fit import _Problem


class Quadratic:
    size = 9
    basis = np.array([[1], [-1]]) / np.sqrt(2)
    bank = SimpleNamespace(numbers=np.array([1, 2]), nodes_s=np.array([-1000, 1000]))
    observations = SimpleNamespace(times_s=np.array([0, 100]))
    prior = SimpleNamespace(radius_km=250)
    scales = np.array([1, 1, 200, 2, 200, 2, 200, 1, 1])

    def __init__(self, target=None):
        self.target = np.zeros(9) if target is None else np.asarray(target)
        self.calls = 0

    def evaluate(self, vector):
        self.calls += 1
        delta = vector / self.scales - self.target
        return float(0.5 * delta @ delta), delta / self.scales, None


def test_small_quadratic_polish_is_monotone_and_independently_qualified():
    objective = Quadratic()
    start = np.zeros(9)
    start[[2, 4]] = [2.4, -0.6]
    result = polish(objective, start)
    assert result["converged"] and result["stationarity"] <= 0.001
    assert result["objective"] < result["initial_objective"]
    assert result["evaluations"] == objective.calls <= 160
    assert result["rounds"] <= 10
    for row in result["accepted"]:
        assert row["after_objective"] < row["before_objective"]
        assert result["trials"][row["trial_index"]]["objective"] == row["after_objective"]
    assert len(result["trials"]) == 14 * result["rounds"]
    np.testing.assert_array_equal(start[[2, 4]], [2.4, -0.6])


def test_active_bound_kkt_does_not_move_an_outward_optimum():
    target = np.zeros(9)
    target[3] = 31  # Physical slope62Hz/s, outside hard60.
    objective = Quadratic(target)
    start = np.zeros(9)
    start[3] = 60
    result = polish(objective, start)
    assert result["converged"]
    assert result["evaluations"] == 1
    assert not result["trials"]
    assert result["vector"][3] == 60
    problem = _Problem(objective, start, fixed_position=True)
    assert projected_gradient(problem, start, objective.evaluate(start)[1])[1] == 0


def test_active_bound_can_take_only_feasible_inward_steps():
    target = np.zeros(9)
    target[3] = 29.995
    objective = Quadratic(target)
    start = np.zeros(9)
    start[3] = 60
    result = polish(objective, start)
    assert result["vector"][3] < 60
    assert any(not t["feasible"] for t in result["trials"])
    assert all(t["vector"][3] <= 60 + 1e-7 for t in result["trials"] if t["evaluated"])
    assert result["physical_constraints_minimum"] >= -1e-7


def test_no_improvement_is_explicit_and_never_overrides_gate():
    class Inconsistent(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            gradient = np.zeros(9)
            gradient[2] = 1
            return 1.0, gradient, None

    objective = Inconsistent()
    result = polish(objective, np.zeros(9))
    assert not result["converged"]
    assert result["stop_reason"] == "no-improving-feasible-step"
    assert result["objective"] == result["initial_objective"] == 1
    assert result["rounds"] == 0
    assert len(result["trials"]) == 14
    assert result["evaluations"] == objective.calls == 15


def test_fixed_position_and_zero_c_remain_locked():
    start = np.zeros(9)
    start[:2] = [4, -8]
    start[2] = 3
    objective = Quadratic()
    result = polish(objective, start, rf_arm="zero-c")
    np.testing.assert_array_equal(result["vector"][:2], start[:2])
    assert result["vector"][6] == 0
    assert all(t["coordinate"] not in [0, 1, 6] for t in result["trials"])
    for t in result["trials"]:
        np.testing.assert_array_equal(t["vector"][:2], start[:2])


def test_hard_operation_budget_stops_without_claiming_convergence():
    objective = Quadratic()
    start = np.zeros(9)
    start[2] = 100
    result = polish(objective, start, maximum_evaluations=2)
    assert result["evaluations"] == objective.calls == 2
    assert result["stop_reason"] == "evaluation-budget"
    assert not result["converged"]
    assert any(t.get("reason") == "evaluation budget" for t in result["trials"])


def test_start_is_not_silently_clipped_or_rescaled():
    start = np.zeros(9)
    start[3] = 61
    with pytest.raises(ValueError, match="physical constraints"):
        polish(Quadratic(), start)


def test_feasible_boundary_original_is_preserved_despite_helper_normalization():
    start = np.zeros(9)
    start[8] = 20 * np.sqrt(2)
    objective = Quadratic(start / Quadratic.scales)
    result = polish(objective, start)
    np.testing.assert_array_equal(result["vector"], start)
    assert np.max(abs(result["helper_start_delta"])) > 0
    assert result["converged"]


def test_bad_objective_fails_explicitly():
    class Bad(Quadratic):
        def evaluate(self, vector):
            return float("nan"), np.zeros(9), None

    with pytest.raises(ValueError, match="finite"):
        polish(Bad(), np.zeros(9))


def test_failed_trial_evaluations_are_retained_and_count_toward_budget():
    class FailingTrial(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            if np.any(vector):
                raise ValueError("synthetic rejected trial")
            gradient = np.zeros(9)
            gradient[2] = 1
            return 1.0, gradient, None

    objective = FailingTrial()
    result = polish(objective, np.zeros(9))
    assert result["evaluations"] == objective.calls == 15
    assert len(result["trials"]) == 14
    assert all(
        t["evaluated"] and "synthetic rejected trial" in t["error"] for t in result["trials"]
    )
    assert not result["converged"]
