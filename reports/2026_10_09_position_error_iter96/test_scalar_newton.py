"""Synthetic exact quadratics and bounded roundoff qualification."""

import sys
from pathlib import Path

import numpy as np
import pytest
from curvature_polish import polish

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter94"))
from test_coordinate_polish import Quadratic  # noqa: E402


def test_newton_qualifies_quadratic_and_keeps_exact_gate():
    objective = Quadratic()
    start = np.zeros(9)
    start[[2, 4]] = [5, -1.2]
    result = polish(objective, start)
    assert result["converged"] and result["stationarity"] <= 0.001
    assert result["objective"] < result["initial_objective"]
    assert result["evaluations"] == objective.calls <= 100
    assert result["rounds"] <= 10
    assert all(row["after_stationarity"] < row["before_stationarity"] for row in result["accepted"])
    assert all(row["after_objective"] <= result["objective_ceiling"] for row in result["accepted"])


def test_tiny_roundoff_cost_increase_can_qualify_without_lowering_gate():
    class Noisy(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            z = vector[8]
            gradient = np.zeros(9)
            gradient[8] = 100000 * z - 0.0015
            cost = 40000 + 0.5 * 100000 * z * z - 0.0015 * z
            if z != 0:
                cost += 1e-10  # Greater than predicted true benefit, within128ULP.
            return cost, gradient, None

    objective = Noisy()
    result = polish(objective, np.zeros(9))
    assert result["converged"] and result["stationarity"] < 1e-12
    assert result["objective"] > result["initial_objective"]
    assert result["objective"] <= result["initial_objective"] + result["objective_tolerance"]
    assert result["objective_tolerance"] == 128 * abs(np.spacing(40000.0))
    assert result["vector"][8] == pytest.approx(1.5e-8, abs=1e-16)


def test_material_cost_worsening_is_rejected_even_when_gradient_qualifies():
    class WrongCost(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            gradient = np.zeros(9)
            gradient[8] = 100000 * vector[8] - 0.0015
            return 40000 + (0.01 if vector[8] != 0 else 0), gradient, None

    result = polish(WrongCost(), np.zeros(9))
    assert not result["converged"]
    assert result["objective"] == result["initial_objective"]
    assert result["stop_reason"] == "no-kkt-improving-admissible-step"
    assert any(t["stationarity"] <= 0.001 for t in result["trials"] if t["kind"] == "newton")


def test_initial_score_tolerance_cannot_accumulate_across_rounds():
    tolerance = 128 * abs(np.spacing(40000.0))

    class TwoCoordinates(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            gradient = np.zeros(9)
            gradient[8] = 100000 * vector[8] - 0.002
            gradient[7] = 100000 * vector[7] - 0.0015
            cost = 40000 + 0.75 * tolerance * (int(vector[8] != 0) + int(vector[7] != 0))
            return cost, gradient, None

    result = polish(TwoCoordinates(), np.zeros(9))
    assert result["rounds"] == 1
    assert not result["converged"]
    assert result["objective"] <= result["initial_objective"] + tolerance
    assert any(
        t.get("within_initial_score_ceiling") is False and t["kind"] == "newton"
        for t in result["trials"]
    )


def test_full_kkt_cannot_be_replaced_by_selected_coordinate_only():
    class Coupled(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            x, y = vector[8], vector[7]
            gradient = np.zeros(9)
            gradient[8] = 100 * x + 99 * y - 0.002
            gradient[7] = 99 * x + 100 * y + 0.0015
            return (
                40000 + 50 * (x * x + y * y) + 99 * x * y - 0.002 * x + 0.0015 * y,
                gradient,
                None,
            )

    result = polish(Coupled(), np.zeros(9), maximum_rounds=1)
    assert not result["converged"]
    full_steps = [t for t in result["trials"] if t["kind"] == "newton" and t["damping"] == 1]
    assert abs(full_steps[0]["gradient"][8]) < 1e-12
    assert full_steps[0]["stationarity"] > 0.001


def test_active_bound_uses_feasible_one_sided_curvature():
    target = np.zeros(9)
    target[3] = 29.995
    start = np.zeros(9)
    start[3] = 60
    result = polish(Quadratic(target), start)
    assert result["converged"]
    assert result["accepted"][0]["curvature_method"] == "backward-gradient-difference"
    assert any(not t["feasible"] for t in result["trials"])
    assert result["physical_constraints_minimum"] >= -1e-7


def test_nonpositive_curvature_stops_explicitly():
    class Linear(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            gradient = np.zeros(9)
            gradient[8] = 1
            return 40000 + vector[8], gradient, None

    result = polish(Linear(), np.zeros(9))
    assert result["stop_reason"] == "nonpositive-or-nonfinite-curvature"
    assert not result["converged"]
    assert len(result["trials"]) == 2


def test_fixed_position_zero_c_and_original_boundary_are_preserved():
    start = np.zeros(9)
    start[:2] = [4, -8]
    start[8] = 20 * np.sqrt(2)
    target = start / Quadratic.scales
    objective = Quadratic(target)
    result = polish(objective, start, rf_arm="zero-c")
    np.testing.assert_array_equal(result["vector"], start)
    assert np.max(abs(result["helper_start_delta"])) > 0
    assert result["converged"]


def test_operation_budget_is_enforced_and_failed_probes_retained():
    objective = Quadratic()
    start = np.zeros(9)
    start[2] = 5
    result = polish(objective, start, maximum_evaluations=2)
    assert result["evaluations"] == objective.calls == 2
    assert result["stop_reason"] == "evaluation-budget"
    assert any(t.get("reason") == "evaluation budget" for t in result["trials"])

    class Failed(Quadratic):
        def evaluate(self, vector):
            self.calls += 1
            if np.any(vector):
                raise ValueError("synthetic failed probe")
            gradient = np.zeros(9)
            gradient[8] = 1
            return 40000, gradient, None

    result = polish(Failed(), np.zeros(9))
    assert result["evaluations"] == 3
    assert all("synthetic failed probe" in t["error"] for t in result["trials"])
    assert not result["converged"]
