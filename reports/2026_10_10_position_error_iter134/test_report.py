import copy

import pytest
from report import verify_successor


def fixture():
    plan, result = {"member": {"metadata_sha256": "x"}}, {"metadata_sha256": "x"}
    metadata = {"window_ids": ["a", "b"]}
    old = [
        {"window_id": "a", "status": "complete", "result": {"number": 1.0, "elapsed_s": 1.0}},
        {"window_id": "b", "status": "visit-read-failed"},
    ]
    new = copy.deepcopy(old)
    new[0]["result"]["elapsed_s"] = 2.0
    new[1] = {"window_id": "b", "status": "complete", "result": {"number": 2.0}}
    return plan, result, new, metadata, old


def test_previous_success_reproduced_without_ignoring_failure_lineage():
    out = verify_successor(*fixture())
    assert out["previous_successes_exactly_reproduced"] == 1
    assert out["complete_parity"] and out["rows"] == 2


@pytest.mark.parametrize("kind", ["missing", "duplicate", "changed", "regressed"])
def test_invalid_successor_rejected(kind):
    plan, result, new, metadata, old = fixture()
    if kind == "missing":
        new.pop()
    if kind == "duplicate":
        new.append(new[0])
    if kind == "changed":
        new[0]["result"]["number"] += 1
    if kind == "regressed":
        new[0]["status"] = "failed"
    with pytest.raises(ValueError):
        verify_successor(plan, result, new, metadata, old)
