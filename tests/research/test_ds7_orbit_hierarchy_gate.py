import copy

import pytest

from tools.ds7_orbit_hierarchy_gate import audit, candidate_supported, project


def _fixture():
    sessions = [f"s{i:02d}" for i in range(88)]
    groups = [
        {
            "kind": "group8",
            "unit_id": f"group8-{i + 1:02d}",
            "session_ids": sessions[i * 8 : i * 8 + 8],
        }
        for i in range(11)
    ]
    plan = {
        "dataset_sha256": "sha256:dataset",
        "content_sha256": "sha256:plan",
        "captures": [{"session_id": session} for session in sessions],
        "units": groups,
    }
    projections = []
    for session in sessions:
        projections.append({"session_id": session, "tle_candidates": []})
    row = {
        "physical_group_id": "p",
        "leading_catalog_number": 123,
        "heldout": {"leader_rank": 1, "leader_persisted": True, "runner_margin": 2.0},
        "abstention_recommended": False,
        "abstention_reasons": [],
        "candidate_only": True,
        "identity_claimed": False,
    }
    projections[0]["tle_candidates"] = [copy.deepcopy(row)]
    projections[40]["tle_candidates"] = [copy.deepcopy(row)]
    return plan, projections, row


def test_candidate_repeat_is_not_identity_or_calibration_admission():
    plan, projections, _ = _fixture()
    result = audit(plan, projections)
    assert result["candidate_repeat_count"] == 1
    assert result["candidate_repeats"][0]["status"] == "candidate_repeat_only"
    assert result["independently_asserted_identity_row_count"] == 0
    assert result["gate"]["variant_fit_admitted"] is False


def test_whole_group_split_rejects_membership_reordering_leakage():
    plan, projections, _ = _fixture()
    plan["units"][-1]["session_ids"][-1], plan["units"][-1]["session_ids"][-2] = (
        plan["units"][-1]["session_ids"][-2],
        plan["units"][-1]["session_ids"][-1],
    )
    with pytest.raises(ValueError, match="chronological capture membership"):
        audit(plan, projections)


def test_abstention_or_unpersisted_leader_is_not_supported():
    _, _, row = _fixture()
    row["abstention_recommended"] = True
    assert candidate_supported(row) is False
    row["abstention_recommended"] = False
    row["heldout"]["leader_persisted"] = False
    assert candidate_supported(row) is False


def test_pending_product_preserves_membership_without_inventing_support():
    result = project("s00", {"session_id": "s00", "state": "pending", "product": None})
    assert result["source_digest"] is None
    assert result["tle_candidates"] == []
