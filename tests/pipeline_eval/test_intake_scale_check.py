import pytest

from reports.ALGO08.v3.intake_scale_check import blind_rows, check_order, load
from reports.ALGO08.v3.release_intake_rate import required_rate


def test_transfer_charges_intercept_and_reports_whole_case_error():
    result = check_order((1_000_000, 1.5), (5_000_000, 3.5), (10_000_000, 8),
                         (20_000_000, 22_000_000), 10)
    assert result["marginal_MB_s"] == 2
    assert result["intercept_s"] == 1
    assert result["full_error_percent"] == -25
    assert result["projected_transfer_s"] == [11, 12]
    assert result["transfer_headroom_s"] == [-2, -1]


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
