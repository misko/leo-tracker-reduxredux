import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from phase_route_challenge import score_choice


def test_one_small_regression_fails_strict_direction_but_passes_development_tolerance():
    errors = {
        "stock": {"c0": 1.0, "fitted_c": 1.0},
        "cumulative": {"c0": 0.5, "fitted_c": 1.02},
    }
    result = score_choice(True, errors, {"stock": "ok", "cumulative": "ok"})
    assert result["outcome"] == "selected regression"
    assert result["within_250_m_both_arms"]


def test_unavailable_qualification_uses_stock_without_claiming_a_prediction():
    result = score_choice(
        None,
        {"stock": {"c0": 1.0, "fitted_c": 1.0}},
        {"stock": "ok", "cumulative": "withheld"},
    )
    assert result["route"] == "stock"
    assert result["outcome"] == "qualification unavailable"
    assert result["error_delta_km"] is None
    assert not result["within_250_m_both_arms"]
