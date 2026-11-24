import pytest

from reports.ALGO08.v3.sparse8_empty_exits import STAGES, price


def test_late_exit_preserves_positive_calls_and_charges_the_work_to_reach_the_cut():
    times = {s: 0 for s in STAGES}
    times.update(lag_timing=3, carrier_grid=5, other=2)
    clocks = {"positive": dict(times, carrier_grid=15), "empty": times}
    row = dict(installed_s=100, candidate_s=70, short_lanes=4, short_positives=1, short_s=25, solver_s=14)
    before = price([row], clocks, "input_mix")
    after = price([row], clocks, "carrier_grid")
    assert before["saved_short_wall_s"] == 15
    assert after["saved_short_wall_s"] == 7.5
    assert after["excess_above_half_s"] == pytest.approx(70 - 4 - 7.5 - 50)
    assert price([dict(row, short_positives=4)], clocks, "input_mix")["saved_short_wall_s"] == 0
    assert price([dict(row, short_lanes=0, short_positives=0, short_s=0)], clocks, "input_mix")["pairs"] == 1
    with pytest.raises(ValueError, match="Inconsistent"):
        price([dict(row, short_positives=5)], clocks, "input_mix")
