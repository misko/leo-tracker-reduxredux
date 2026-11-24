import pytest

from reports.ALGO08.v3.ds30_oracle_routing import coverage, frozen_order, meets, optimize


def row(case, elapsed, c0, fitted, *, fix=None):
    return dict(case=case, elapsed_s=elapsed, cpu_s=elapsed*.8,
                c0_error_km=c0, fitted_c_error_km=fitted,
                c0_fix=c0 is not None if fix is None else fix,
                fitted_c_fix=fitted is not None if fix is None else fix)


def test_execution_order_puts_frozen_smoke_first():
    cases = [dict(case=case) for case in ("a", "b", "c", "d")]
    assert [value["case"] for value in frozen_order(dict(cases=cases, smoke=["d", "b"]))] == ["d", "b", "a", "c"]
    with pytest.raises(ValueError, match="ambiguous"):
        frozen_order(dict(cases=cases, smoke=["a", "a"]))


def test_all_finite_thresholds_and_both_calibrations_are_binding():
    pair = (row("a", 10, 0, .13), row("a", 5, 0, .27))
    assert not meets(coverage([pair], None), 1)
    assert meets(coverage([pair], (1., 2.)), 1)
    result = optimize([pair])
    assert result["strict"]["minimum_sum"]["successor"] == []
    assert result["relaxed"]["minimum_sum"]["successor"] == ["a"]


def test_fix_count_stays_binding_at_both_relaxed_and_finite_gates():
    no_error_with_fix = row("a", 10, None, None, fix=True)
    no_fix = row("a", 5, None, None)
    one = [(no_error_with_fix, no_fix)]
    assert not meets(coverage(one, None), 1)
    assert not meets(coverage(one, (1., 2.)), 1)
    assert optimize(one)["unconstrained"]["minimum_sum"]["successor"] == ["a"]


def test_exact_sum_and_median_can_require_different_choices():
    pairs = [(row("a", 1000, .5, .5), row("a", 600, .8, .8)),
             (row("b", 10, .8, .8), row("b", 2, .5, .5)),
             (row("c", 10, .5, .5), row("c", 1, .8, .8))]
    strict = optimize(pairs)["strict"]
    assert strict["eligible"] == 4
    assert strict["minimum_sum"]["successor"] == ["a", "b"]
    assert strict["minimum_median"]["successor"] == ["b", "c"]
    assert not strict["common_optimum"]
    assert strict["minimum_sum"]["wall"]["total_s"] == 612
    assert strict["minimum_median"]["wall"]["median_paired_speedup"] == 5
    assert strict["joint"]["successor"] == ["a", "b"]


def test_scored_gains_can_cover_a_regression_without_increasing_total_failures():
    pairs = [(row("a", 10, None, None), row("a", 5, .01, .01)),
             (row("b", 10, .02, .03), row("b", 5, None, None))]
    strict = optimize(pairs)["strict"]["minimum_sum"]
    assert strict["successor"] == ["a", "b"]
    assert all(arm["largest_deficit"] == 0 and arm["routed_fixes"] == 1
               for arm in strict["calibrated_coverage"].values())
