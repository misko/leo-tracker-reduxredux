from __future__ import annotations

from leo.pipeline import StageOutcome, StageResult


def test_no_result_is_distinct_from_insufficient_data_and_failure() -> None:
    absent = StageResult(
        outcome=StageOutcome.NO_RESULT,
        summary={"candidate_count": 0},
        message="sufficient search coverage found no candidate",
    )
    insufficient = StageResult(
        outcome=StageOutcome.INSUFFICIENT_DATA,
        summary={"coverage_fraction": 0.0},
        message="no samples were available",
    )

    assert absent.outcome is StageOutcome.NO_RESULT
    assert insufficient.outcome is StageOutcome.INSUFFICIENT_DATA
    assert absent.outcome != insufficient.outcome
    assert "failed" not in {outcome.value for outcome in StageOutcome}
