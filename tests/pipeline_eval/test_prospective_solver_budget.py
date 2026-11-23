from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def budget(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("prospective_solver_budget")


def test_budget_reserves_separate_render_and_solve_times(budget):
    case = budget.allowance(20, 40, 3, 2, 10)
    assert case["available_for_acquisition_and_all_other_work_s"] == 5
    assert case["minimum_acquisition_MB_s"] == 8
    assert case["maximum_solve_at_diagnostic_rate_s"] == 4
    assert budget.allowance(10, 40, 3, 2, 10)["minimum_acquisition_MB_s"] is None


def test_preexisting_predictions_referenced_by_two_clock_boundaries(budget):
    result = budget.assess()
    assert result["transfer"]["historical_detections_to_terminal"]["predictions"]["three_sizes_s"] == pytest.approx(8.901, abs=.001)
    assert result["transfer"]["fresh_stock_solve_cpu"]["predictions"]["three_sizes_s"] == pytest.approx(8.749, abs=.001)
    assert result["fresh_solve_cpu_s"] == pytest.approx(8.659, abs=.001)
