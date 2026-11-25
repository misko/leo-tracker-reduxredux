import pytest

from reports.ALGO08.v3.accuracy_stage_bounds import bound, percent_bracket, stages
from reports.ALGO08.v3.ds30_oracle_routing import coverage


def test_native_and_short_are_subsets_of_acquisition():
    cost = dict(acquisition_s=8, native_detector_s=5, solver=2, actual_wall_s=10)
    short = dict(short_wall=2, short_cpu=2)
    result = stages(cost, short, .5, 10)
    assert result["free_nonnative_acquisition"] == 30
    assert result["free_native_and_solver"] == 70
    assert result["free_short_and_solver"] == 40
    assert result["transferred_kernel"] == 10
    with pytest.raises(ValueError):
        stages(dict(cost, native_detector_s=9), short, .5, 10)


def test_accuracy_can_force_the_slower_build_even_with_free_receiving():
    def arm(case, error):
        return dict(case=case, fitted_c_fix=True, c0_fix=True, fitted_c_error_km=error, c0_error_km=error)

    pairs = [(arm("first", 1.), arm("first", 1.)), (arm("second", .8), arm("second", 2.))]
    result = bound(pairs, [(10, 2), (10, 1)], coverage(pairs, None), 1)
    assert result["feasible"]["candidate_cases"] == ["first"]
    assert result["lower_time_units"] == result["feasible"]["total_units"] == 12
    assert result["exact_sum"] and not result["both_gates_met_by_witness"]


def test_clock_bracket_keeps_sum_and_median_distinct():
    def evaluate(p):
        return dict(lower_time_units=77-p, feasible=dict(total_units=77-p, installed_total_units=100),
                    both_gates_met_by_witness=False)

    result = percent_bracket(evaluate)
    assert (result["previous_percent"], result["passing_percent"]) == (26, 27)
    assert not result["passing"]["both_gates_met_by_witness"]
