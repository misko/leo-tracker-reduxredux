"""Verify the protected-region replay's assignment and no-location checks."""

from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
import local_future_omissions as audit  # noqa: E402


def test_accepted_repair_can_only_add_pinned_future_owner():
    original = [["before", 100, "conditional"]]
    expanded = original + [["future", 200, "predictive"]]
    repaired = dict(decision="accepted", added=[dict(observation_id="future", norad=200, role="predictive")])
    assert audit.owner_delta(original, expanded, {"future"}, repaired) == dict(before=1, after=2, added=1)
    with pytest.raises(ValueError, match="Changed incumbent"):
        audit.owner_delta(original, expanded, {"other"}, repaired)
    with pytest.raises(ValueError, match="Changed incumbent"):
        audit.owner_delta(original, [["before", 101, "conditional"], expanded[1]], {"future"}, repaired)
    with pytest.raises(ValueError, match="Changed incumbent"):
        audit.owner_delta(original, expanded, {"future"}, dict(repaired, decision="rejected"))


@pytest.mark.parametrize("repair", [{}, {"decision": "rejected"}])
def test_zero_owner_early_exit_and_unchanged_rejected_repair(repair):
    assert audit.owner_delta([], [], {"candidate"}, repair) == dict(before=0, after=0, added=0)
    kept = [["original", 100, "conditional"]]
    assert audit.owner_delta(kept, kept, {"candidate"}, repair) == dict(before=1, after=1, added=0)


def test_a_duplicate_row_is_never_interpreted_as_preserved_ownership():
    before = [["same", 100, "predictive"]]
    with pytest.raises(ValueError, match="Duplicate"):
        audit.owner_delta(before, before * 2, set(), {})
