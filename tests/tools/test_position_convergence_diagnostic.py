import importlib.util
from pathlib import Path


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_convergence_diagnostic.py"
    spec = importlib.util.spec_from_file_location("position_convergence_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optimizer_budget_preserves_incumbent_and_never_needs_truth():
    module = subject()
    rows = module.optimize_comparison(
        lambda point: (point[0] - 2.0) ** 2 + (point[1] + 3.0) ** 2,
        [[1.5, -2.5]],
        [4, 80],
    )
    assert rows[1]["objective_rmse_hz"] <= rows[0]["objective_rmse_hz"]
    assert "evaluation_only_error_km" not in rows[0]
    assert rows[1]["movement_from_seed_km"] > 0


def test_truth_is_appended_without_changing_inference_fields():
    module = subject()
    inference = {
        "position_truth_used": False,
        "rows": [{"latitude_deg": 37.0, "longitude_deg": -122.0, "objective_rmse_hz": 4.0}],
    }
    evaluated = module.append_truth_evaluation(inference, (37.1, -122.1), provenance="test fixture")
    assert "evaluation_only_error_km" not in inference["rows"][0]
    assert evaluated["rows"][0]["objective_rmse_hz"] == 4.0
    assert evaluated["rows"][0]["evaluation_only_error_km"] > 0
    assert evaluated["reference_used_for_inference"] is False
    assert evaluated["reference_coordinate"]["provenance"] == "test fixture"


def test_baseline_replay_requires_exact_coordinates_and_objective():
    module = subject()
    rows = [
        {
            "max_evaluations": 35,
            "latitude_deg": 1.0,
            "longitude_deg": 2.0,
            "objective_rmse_hz": 3.0,
        }
    ]
    module.assert_baseline_replay(
        rows, [{"latitude_deg": 1.0, "longitude_deg": 2.0, "rmse_hz": 3.0}]
    )
