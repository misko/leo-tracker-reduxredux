import pytest

from reports.ALGO08.v3.full_successor_stage_budget import elapsed_budget, two_gate_reduction


def test_nested_callbacks_are_subtracted_only_once():
    r = elapsed_budget(20, 15, 5, 8, 1)
    assert r["gap_s"] == 5
    assert r["remaining_s"] == 2
    assert r["minimum_savings_outside_detector_s"] == 4
    assert r["fraction_needed_from_acquisition_and_publication"] == 5/13
    assert r["speedup_if_acquisition_and_publication_each_halved"] == 20/8.5


@pytest.mark.parametrize("values", [(20, 15, 2, 13, 3), (20, 15, 4, 12, 2),
                                     (0, 12, 8, 2, 3), (float("nan"), 12, 8, 2, 3)])
def test_inconsistent_stage_clocks_rejected(values):
    with pytest.raises(ValueError):
        elapsed_budget(*values)


def test_full_cohort_uses_both_timing_gates_even_when_the_order_of_ratios_changes():
    records = [elapsed_budget(100, 80, 70, 9, 60), elapsed_budget(10, 9, 8, 1, 8),
               elapsed_budget(10, 7, 1, 2, 1), elapsed_budget(20, 9, 2, 1, 1)]
    result = two_gate_reduction(records, "native_detector")
    assert result["summed"] == pytest.approx(35/70)
    # At 0.5 the two inner ratios are 0.5 and 0.5, with their order changing at that point.
    assert result["median_paired"] == pytest.approx(.5)
    assert result["both"] == pytest.approx(.5)
    assert two_gate_reduction(records, "decision_and_publication")["both"] is None


def test_fixed_savings_and_no_double_counting():
    budget = [elapsed_budget(20, 16, 8, 6, 2)]
    assert two_gate_reduction(budget, "decision_and_publication", acquisition_fraction=.25)["both"] == pytest.approx(4/6)
    assert two_gate_reduction(budget, "other_acquisition")["both"] == pytest.approx(1)
    assert two_gate_reduction([elapsed_budget(32, 16, 8, 6, 2)], "native_detector")["both"] == 0
    with pytest.raises(ValueError, match="disjoint"):
        two_gate_reduction(budget, "native_detector", acquisition_fraction=.25)


def test_measured_zero_stage_is_retained_in_the_median_and_total():
    rows = [elapsed_budget(10, 7, 0, 0, 0), elapsed_budget(30, 17, 8, 6, 2)]
    assert rows[0]["fraction_needed_from_acquisition_and_publication"] is None
    result = two_gate_reduction(rows, "acquisition")
    assert result["summed"] == pytest.approx(.5)
    assert result["median_paired"] == pytest.approx(1)
    assert result["both"] == pytest.approx(1)
