import pytest

from reports.ALGO08.v3.intake_scale_check import (
    blind_rows, check_order, combined_intake_budget, cpu_budget, load, solve_intake_tradeoff,
)
from reports.ALGO08.v3.release_intake_rate import required_rate


def test_revised_solver_joint_target_is_for_its_two_blind_inputs_only():
    result = combined_intake_budget()
    first, second = result["rows"]
    assert [first["case"], second["case"]] == ["DS30-0163", "DS30-0173"]
    assert first["post_s"] == pytest.approx(13.6972304)
    assert second["post_s"] == pytest.approx(16.0159222)
    assert result["joint"]["required_MB_s"] == pytest.approx(229.47936)
    assert result["joint"]["sum_ratio"] < result["joint"]["median_ratio"] == pytest.approx(.5)


def test_transfer_charges_intercept_and_reports_whole_case_error():
    result = check_order((1_000_000, 1.5), (5_000_000, 3.5), (10_000_000, 8),
                         (20_000_000, 22_000_000), 10)
    assert result["marginal_MB_s"] == 2
    assert result["intercept_s"] == 1
    assert result["full_error_percent"] == -25
    assert result["projected_transfer_s"] == [11, 12]
    assert result["transfer_headroom_s"] == [-2, -1]


def test_cpu_budget_charges_every_case_and_detects_unattainable_time():
    rows = [dict(cpu_s=1, elapsed_s=4), dict(cpu_s=2, elapsed_s=2)]
    assert cpu_budget(rows, 1)["required_cpu_speedup"] == {"sum": None, "median": 5.}
    assert cpu_budget(rows, 0)["required_cpu_speedup"] == {"sum": 1., "median": 1.25}
    with pytest.raises(ValueError):
        cpu_budget([dict(cpu_s=4, elapsed_s=3)], 0)


def test_keep_negative_intercepts_and_disallow_nonpositive_time_slopes():
    assert check_order((2, 1), (4, 5), (8, 10), (80, 81), 20)["intercept_s"] == -3
    fit = check_order((2, 1), (4, 1), (8, 10), (80, 81), 20)
    assert not fit["usable"] and "marginal_MB_s" not in fit
    with pytest.raises(ValueError):
        check_order((2, 1), (4, 3), (4, 5), (80, 81), 20)


def test_both_matched_orders_underpredict_normal_full_clock():
    orders = load()
    assert [order["order"] for order in orders] == [[1, 4], [4, 1]]
    for order in orders:
        clock = order["scopes"]["through_detections"]
        assert clock["measured_full_s"] == pytest.approx(4.677983086)
        assert -28 < clock["full_error_percent"] < -27
        assert clock["projected_transfer_s"][1] < clock["transfer_allowance_s"]
        assert "projected_transfer_s" not in order["scopes"]["authenticated_acquisition"]


def test_blind_gates_include_both_withheld_baseline_and_recovered_fix():
    rows = blind_rows()
    assert [r["case"] for r in rows] == ["DS30-0419", "DS30-0289"]
    assert rows[1]["allowance_s"] == pytest.approx(18.55146)
    gate = required_rate(rows, "byte_high", 1, 0)
    assert gate["required_MB_s"] == pytest.approx(342.787)
    assert gate["median_ratio"] == pytest.approx(.5)
    assert gate["sum_ratio"] < .5


def test_only_numerical_time_can_be_saved_in_tradeoff():
    # Even a zero-cost solve still pays four seconds outside the solver.
    rows = [dict(elapsed_s=10., post_s=6., solve_s=2., byte_low=1_000_000, byte_high=2_000_000)]
    scenarios = solve_intake_tradeoff(rows)
    assert scenarios[0]["rates"]["byte_high"] is None
    assert scenarios[-1]["numeric_time_eliminated"]
    assert scenarios[-1]["rates"]["byte_high"]["required_MB_s"] == pytest.approx(2.)
    assert scenarios[-1]["rates"]["byte_low"]["required_MB_s"] == pytest.approx(1.)
