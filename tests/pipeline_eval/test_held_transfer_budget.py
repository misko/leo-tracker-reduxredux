import pytest

from reports.ALGO08.v3.held_transfer_budget import comparisons


def test_transfer_cost_and_accuracy_use_the_containing_cases():
    north, south = comparisons()
    for result, gap in zip((north, south), (3.8523, 4.4287), strict=True):
        assert result["gap"] == pytest.approx(gap, abs=.001)
        assert 0 < result["cfo_cpu"] < result["acquisition"]
        assert 0 < result["other"] < 1
        assert result["other"] + result["acquisition"] + result["finish"] == pytest.approx(result["candidate"])
    assert north["errors_m"][0] == pytest.approx((105.690, 113.236), abs=.001)
    assert south["errors_m"][1] == pytest.approx((1101.409, 810.906), abs=.002)
