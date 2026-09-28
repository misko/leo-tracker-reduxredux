import pytest

import dual_shared_geometry_reporting as subject
from test_shared_geometry_reporting import branch_fixture


def fixture():
    saved, branch = branch_fixture()
    names = {"old": "old", "mixture": "detection", "shared": "dual"}
    def point(row):
        return {**row, "variant_scores": subject.renamed(row["variant_scores"], names)}
    return saved, {**branch, "point_components": [point(row) for row in branch["point_components"]],
                   "selected": {names[k]: point(v) for k, v in branch["selected"].items()}}


def test_validation_and_labels_preserve_independent_minima():
    saved, branch = fixture()
    result = subject.validate_branch(saved, branch)
    assert set(result["selected"]) == {"old", "detection", "dual", "D"}
    assert result["selected"]["dual"]["east_km"] == 0.
    assert result["selected"]["detection"]["east_km"] == 1.


def test_changed_dual_D_rejected():
    saved, branch = fixture()
    branch["point_components"][0]["variant_scores"]["dual"]["D"] += 1.
    with pytest.raises(ValueError): subject.validate_branch(saved, branch)


def test_summary_is_complete_and_uses_only_dual_labels():
    sessions = list(map(str, range(4)))
    rows = [{"session_id": s, "prior": p,
             "errors_km": {"D": 4., "old": 3., "detection": 5., "dual": 3.}}
            for s in sessions for p in ("sacramento", "reno")]
    result = subject.summarize(rows, sessions)
    assert result["combined"]["dual_vs"]["D"]["improved"] == 8
    assert set(result["reno"]["mean_error_km"]) == {"D", "old", "detection", "dual"}
    with pytest.raises(ValueError): subject.summarize(rows[:-1], sessions)
