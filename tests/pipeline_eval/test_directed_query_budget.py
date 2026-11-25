import pytest

from reports.ALGO08.v3.directed_query_budget import budget, load_cases


def test_charges_queries_after_existing_native_and_solver_costs():
    result = budget([(20, 15, 6, 6, 10)], 2, 2)
    assert result["aggregate_slack_s"] == 1
    assert result["max_additional_us"] == pytest.approx(100_000)
    assert result["speedups_at_840_us"] == pytest.approx((20 / 9.0084,) * 2)


def test_median_can_bind_before_sum_and_cases_without_queries_still_count():
    result = budget([(100, 10, 0, 0, 0), (2, .9, 0, 0, 5), (2, .9, 0, 0, 10)], 1, 1)
    assert result["max_additional_us"] == pytest.approx(20_000)
    assert budget([(10, 6, 0, 0, 1)], 1, 1)["max_additional_us"] is None
    assert budget([(10, 5, 0, 0, 1)], 1, 1)["max_additional_us"] == 0


def test_field_query_counts_match_the_timing_panel():
    cases = load_cases()
    assert len(cases) == 30
    assert sum(row[-1] for row in cases) == 64_639
