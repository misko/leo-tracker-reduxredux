from statistics import median

import pytest

from reports.ALGO08.v3.receiver_solver_targets import aperture_seconds, aperture_targets, design_point, targets


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


def test_design_point_charges_each_measured_scope_once():
    # 15 seconds in native become 10, and 14 seconds of solver become 10.
    # The withheld case still pays its entire four seconds outside those stages.
    result = design_point([(80, 39, 15, 14), (10, 4, 0, 0)])
    assert result["excess_over_half_s"] == pytest.approx(-11)
    assert result["summed_speedup"] == pytest.approx(90 / 34)
    assert result["median_paired_speedup"] == pytest.approx(1 / median([30 / 80, 4 / 10]))


def test_aperture_budget_prices_only_short_calls_after_known_savings():
    result = aperture_targets([(60, 42, 14, 10, 8)])
    # The solver saves 4 s. Without an anchor change, 8 of the 10 short seconds must go.
    assert result["required_short_fraction_removed"][1.]["both"] == pytest.approx(.8)
    assert result["required_short_fraction_removed"][1.25]["both"] == pytest.approx(.64)
    assert aperture_seconds({"full": 1_000_000_000}, 1.) == {"short_s": 0, "full_s": 1.}
    for modes in ({"other": 1}, {"full": 9}, {"short_primary": -2}):
        with pytest.raises(ValueError, match="partition"):
            aperture_seconds(modes, 1.)
