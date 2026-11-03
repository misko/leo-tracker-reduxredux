import pytest
from evaluate_grouped_cohort import evaluate_fit
from joint_inputs import _coordinates


def test_reference_accuracy_never_selects_model_and_all_trials_remain():
    wrong = {
        "parameters": [10., 10.], "satellite_count": 4, "selection_score": 1.,
        "success": False, "status": "nonconverged", "convergence_reason": "budget_exhausted",
    }
    accurate = {
        **wrong, "parameters": [0., 0.], "satellite_count": 8, "selection_score": 2.,
        "success": True, "status": "converged", "convergence_reason": "projected_gradient",
    }
    latitude, longitude = _coordinates([0., 0.])
    result = evaluate_fit({
        "trials": [wrong, accurate],
        "selection": {"score_leader": wrong, "selection_resolved": False},
    }, {"capture": {"latitude_deg": latitude, "longitude_deg": longitude}})
    assert result["selected"]["satellite_count"] == 4
    assert result["selected"]["maximum_reference_error_km"] > 10
    assert result["trials"][1]["maximum_reference_error_km"] == pytest.approx(0.)
    assert not result["selection_resolved"]
