import pytest

from tools.report_glrt_relative_phase import surface_summary


def test_incomplete_surface_cannot_pass_the_accuracy_gate():
    result = dict(completed=False, candidate_scope="conditional pool")
    rows = [
        dict(
            east_m=0.0,
            north_m=0.0,
            distance_m=0.0,
            kind="reference",
            arms={"fitted-c": {"score": 10.0}},
        )
    ]
    summary = surface_summary(result, rows, "fitted-c")
    assert summary["reference_score_gap"] == 0.0
    assert not summary["conditional_gate_met"]
    assert summary["full_catalogue_audit_required"]
    rows[0]["east_m"] = 1.0
    with pytest.raises(ValueError, match="reference"):
        surface_summary(result, rows, "fitted-c")
