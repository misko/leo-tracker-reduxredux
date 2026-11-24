from statistics import median

import pytest

from reports.ALGO08.v3.receiver_solver_targets import targets


def test_even_panel_uses_the_two_middle_ratios_and_keeps_withheld_costs():
    # One pair is already fast. On the other, the solver is the only replaceable work.
    rows = [(10, 2, 0, 0), (40, 32, 0, 20)]
    gates = targets(rows, 1)
    assert gates["paired_median"] == 0
    assert gates["both"] == pytest.approx(9 / 20)


def test_fast_native_path_leaves_a_separate_paired_median_bottleneck():
    rows = [(200, 80, 40, 2), (10, 8, 2, 4), (10, 11, 1, 6)]
    gates = targets(rows, 2)
    assert gates["summed"] == 0
    assert gates["both"] == pytest.approx(.5)
    assert median((b - n / 2 - gates["both"] * s) / a for a, b, n, s in rows) == pytest.approx(.5)


def test_zero_solver_work_can_be_unreachable_at_a_fixed_receiver_rate():
    assert targets([(10, 9, 2, 0)], 2)["both"] is None
    assert targets([(10, 5, 0, 0)], 1)["both"] == 0
    assert targets([(10, 7, 0, 2)], 1)["both"] == pytest.approx(1.)
    with pytest.raises(ValueError, match="disjoint"):
        targets([(10, 7, 5, 3)], 1)
