from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.pipeline import AnalysisContext, StageOutcome, StageResult


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


def test_analysis_context_dependency_inventory_is_exact_bounded_and_ordered() -> None:
    context = AnalysisContext(
        session_id="T1",
        run_id="run-1",
        pipeline_release="1" * 40,
        job_node_id="radio-reduce",
        dependency_node_ids=("path-00", "path-01"),
    )
    assert context.dependency_node_ids == ("path-00", "path-01")

    for invalid in (("path-01", "path-00"), ("path-00", "path-00")):
        with pytest.raises(ValidationError, match="unique, bounded and ordered"):
            AnalysisContext.model_validate(
                {**context.model_dump(mode="json"), "dependency_node_ids": invalid}
            )
