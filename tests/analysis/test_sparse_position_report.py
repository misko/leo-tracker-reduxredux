import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "tools" / "report_sparse_position_exploration.py"
SPEC = importlib.util.spec_from_file_location("report_sparse_position_exploration", SCRIPT)
REPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPORT)


def test_summary_requires_convergence_and_exact_pass_but_keeps_failure_denominator():
    evaluation = {
        "runs": [
            {
                "job_id": "pass",
                "model": "shape3-formal",
                "actual_fitting_count": 399,
                "status": "converged",
                "horizontal_error_m": 700.0,
            },
            {
                "job_id": "exact-fail",
                "model": "shape3-formal",
                "actual_fitting_count": 399,
                "status": "converged",
                "horizontal_error_m": 100.0,
            },
            {
                "job_id": "optimizer-fail",
                "model": "shape3-formal",
                "actual_fitting_count": 399,
                "status": "nonconverged",
                "horizontal_error_m": 50.0,
            },
        ]
    }
    exact = {
        "runs": [
            {"job_id": "pass", "passed": True},
            {"job_id": "exact-fail", "passed": False},
        ]
    }

    summary = REPORT.summarize(evaluation, exact)

    assert len(summary) == 1
    assert summary[0]["total"] == 3
    assert summary[0]["converged"] == 2
    assert summary[0]["exact_checked"] == 2
    assert summary[0]["qualified"] == 1
    assert summary[0]["sub_km_qualified"] == 1
    assert summary[0]["qualified_error_min_m"] == 700.0
    assert summary[0]["qualified_error_max_m"] == 700.0


def test_incomplete_primary_evaluation_is_rejected():
    with pytest.raises(
        ValueError, match=r"refusing to score incomplete noise evaluation: 2/3 runs"
    ):
        REPORT.require_complete_primary({"runs": [{}, {}]}, 3, "noise evaluation")


def test_laplace_exact_pass_at_rate_boundary_is_not_qualified():
    evaluation = {
        "runs": [
            {
                "seed": 2,
                "fraction": 0.125,
                "fitting_observations": 1597,
                "status": "converged",
                "horizontal_error_m": 405.0,
            }
        ]
    }
    exact = {
        "rows": [
            {
                "seed": 2,
                "fraction": 0.125,
                "minimum_rate_bound_margin_s_h": 0.0,
                "exact": {"passed": True},
            }
        ]
    }

    summary = REPORT.summarize_laplace(evaluation, exact)
    row = next(row for row in summary if row["budget"] == 1597)

    assert row["exact_passed"] == 1
    assert row["qualified"] == 0
    assert row["sub_km_qualified"] == 0
