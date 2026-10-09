"""Generic trigger, fixed budget, numerical verification and physical controls."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
import qualification as driver

PRIOR = Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter100"
sys.path.insert(0, str(PRIOR))
SPEC = importlib.util.spec_from_file_location(
    "synthetic100_for102", PRIOR / "test_reduced_newton.py"
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


@pytest.fixture(autouse=True)
def problem(monkeypatch):
    monkeypatch.setattr(driver.newton, "_Problem", helper.helper.Problem)


@pytest.mark.parametrize("stage", ["calibration-prefit", "calibration-postfit"])
def test_direct_qualification_on_coupled_face(stage):
    objective = helper.Anisotropic()
    objective.optimizer_success = True  # Solver success must not suppress a failed full-KKT gate.
    seed = np.zeros(3)
    result = driver.qualify(
        objective,
        seed,
        objective.evaluate(seed)[0],
        retained=True,
        stage=stage,
        independently_qualified=False,
    )
    assert result["status"] == "qualified"
    assert result["fit"]["stationarity"] <= 0.001
    assert result["objective_evaluations"] == result["fit"]["evaluations"] == 8
    assert result["polish_elapsed_s"] > 0
    assert result["objective_verified"] is True
    np.testing.assert_array_equal(result["original_vector"], seed)
    assert result["fit"]["objective"] <= result["fit"]["objective_ceiling"]
    assert all(row["feasible"] for row in result["fit"]["trials"])


@pytest.mark.parametrize(
    "retained,stage,accepted",
    [
        (False, "calibration-prefit", False),
        (True, "association", False),
        (True, "calibration-prefit", True),
    ],
)
def test_normal_fits_and_unretained_points_do_not_trigger(retained, stage, accepted):
    result = driver.qualify(
        object(), np.zeros(3), 0, retained=retained, stage=stage, independently_qualified=accepted
    )
    assert result["status"] == "not-triggered" and result["objective_evaluations"] == 0


def test_dimension_cap_without_objective_evaluation(monkeypatch):
    monkeypatch.setattr(
        driver.newton, "tangent_basis", lambda *args: (None, {"tangent_dimension": 50})
    )
    result = driver.qualify(
        helper.Anisotropic(),
        np.zeros(3),
        0,
        retained=True,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert result["status"] == "dimension-exceeds-budget"
    assert result["minimum_first_round_evaluations"] == 102
    assert result["objective_verified"] is False
    assert result["objective_evaluations"] == 0


def test_bad_saved_score_stops_after_one_counted_evaluation():
    result = driver.qualify(
        helper.Anisotropic(),
        np.zeros(3),
        -99,
        retained=True,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert result["status"] == "failed" and result["objective_evaluations"] == 1


def test_infeasible_lock_and_unchanged_physical_start():
    objective = helper.Anisotropic()
    objective.lower[0] = objective.upper[0] = 1
    result = driver.qualify(
        objective,
        np.zeros(3),
        0,
        retained=True,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert result["status"] == "infeasible-saved-state"
    assert result["objective_evaluations"] == 0


def test_locked_coordinate_does_not_move():
    objective = helper.Anisotropic()
    objective.lower[0] = objective.upper[0] = 0
    seed = np.zeros(3)
    result = driver.qualify(
        objective,
        seed,
        objective.evaluate(seed)[0],
        retained=True,
        stage="calibration-postfit",
        independently_qualified=False,
    )
    assert result["fit"]["vector"][0] == 0
    assert all(row["vector"][0] == 0 for row in result["fit"]["trials"])


@pytest.mark.parametrize("vector", [np.zeros((2, 2)), np.array([np.nan, 0, 0]), np.zeros(5)])
def test_invalid_state_classified_before_any_fit(vector):
    result = driver.qualify(
        helper.Anisotropic(),
        vector,
        0,
        retained=True,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert result["status"] == "qualification-invalid-state"
    assert result["objective_evaluations"] == 0 and result["polish_elapsed_s"] == 0


def test_problem_constructor_failure_classified(monkeypatch):
    def bad_problem(*args, **kwargs):
        raise ValueError("outside prior")

    monkeypatch.setattr(driver.newton, "_Problem", bad_problem)
    result = driver.qualify(
        helper.Anisotropic(),
        np.zeros(3),
        0,
        retained=True,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert result["status"] == "qualification-invalid-state"
    assert "outside prior" in result["error"]
    assert result["objective_evaluations"] == 0
