import pytest
from timing10_comparison_summary import summarize


def row(legacy, grouped):
    return {"dataset": "DS10", "size": 1, "legacy": legacy, "grouped": grouped}


def evaluated(error, resolved=True):
    return {"status": "evaluated", "error_km": error, "selection_resolved": resolved,
            "leader_converged": resolved}


def test_only_paired_units_enter_metrics_but_failures_remain_counted():
    rows = [row(evaluated(3), evaluated(.5, False)),
            row(evaluated(1), evaluated(2)),
            row({"status": "failed"}, evaluated(.1))]
    result = summarize(rows)[0]
    assert result["requested"] == 3 and result["paired_evaluated"] == 2
    assert result["legacy"]["median_error_km"] == 2
    assert result["grouped"]["median_error_km"] == pytest.approx(1.25)
    assert result["grouped"]["sub_km_count"] == 1
    assert result["grouped"]["resolved_count"] == 1
    assert result["legacy"]["pending_or_failed"] == 1
    assert result["grouped_lower_error_count"] == 1


def test_empty_strata_are_not_reported_as_zero_error():
    for result in summarize([]):
        assert result["legacy"]["median_error_km"] is None
        assert result["grouped"]["maximum_error_km"] is None
