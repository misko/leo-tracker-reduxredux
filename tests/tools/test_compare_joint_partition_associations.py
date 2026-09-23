import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "association_comparison",
    Path(__file__).parents[2] / "reports/compare_joint_partition_associations.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(episode, norad, weight):
    return {
        "session_id": "s",
        "episode_id": episode,
        "candidates": [{"norad": norad, "weight": weight}],
        "null_weight": 1 - weight,
    }


def test_matches_by_episode_and_distinguishes_weak_candidate_from_null():
    a = {"tracks": [row("x", 1, 0.99), row("y", 2, 0.1)]}
    b = {"tracks": [row("y", 3, 0.1), row("x", 1, 0.95), row("z", 4, 0.99)]}
    result = MODULE.compare(a, b)
    assert result["common_episodes"] == 2
    assert result["right_only"] == 1
    assert result["candidate_leader_agreement"] == 1
    assert result["both_weight_at_least_0_9"] == 1
    assert result["changed_candidate_leaders"][0]["left_null"] == 0.9


def test_duplicate_or_disjoint_episodes_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        MODULE.indexed_tracks({"tracks": [row("x", 1, 1), row("x", 1, 1)]})
    with pytest.raises(ValueError, match="no common"):
        MODULE.compare({"tracks": [row("x", 1, 1)]}, {"tracks": [row("y", 1, 1)]})


def test_load_rejects_changed_or_nonblind_result(tmp_path):
    path = tmp_path / "result.json"
    document = {"complete": True, "position_truth_used": False, "selected": {"converged": True}}
    path.write_text(json.dumps(document))
    checksum = tmp_path / "result.sha256"
    checksum.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    assert MODULE.load_result(path)[0] == document
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum"):
        MODULE.load_result(path)
    document["position_truth_used"] = True
    path.write_text(json.dumps(document))
    checksum.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="blind"):
        MODULE.load_result(path)
