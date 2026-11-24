from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from curved_overcap_repair import WorkBudget, groups


def test_single_budget_slot_preserves_standard_admission():
    ordinary = lambda counts: all(removed*20 <= total for total, removed in counts.values())
    budget = WorkBudget(ordinary)
    over = dict(tracks=(60, 2), curved=(200, 11), predictive=(20, 0))
    eligible = dict(over, curved=(200, 9))
    assert budget.admit(eligible)
    assert budget.over_cap_counts is None
    assert budget.admit(over)
    assert not budget.admit(over)
    assert budget.admit(eligible)
    assert budget.over_cap_counts == over


def test_over_budget_requires_a_concrete_deleted_track():
    budget = WorkBudget(lambda _: False)
    assert not budget.admit(dict(tracks=(60, 0), curved=(200, 11)))
    assert budget.over_cap_counts is None


def test_orbital_support_counts_radio_channel_owners_not_fragments():
    assignment = {"SCAN-RX1-CH4-T001-RF10.000": (1, 90, 0), "SCAN-RX1-CH4-T002-RF10.000": (1, 90, 0),
                  "SCAN-RX2-CH5-T001-RF14.000": (1, 90, 0), "SCAN-RX2-CH1-T001-RF10.000": (2, 100, 0)}
    nominal = groups(assignment, assignment)
    kept = groups(assignment, [key for key in assignment if "RX2" not in key])
    assert nominal == {1: {(1, 4), (2, 5)}, 2: {(2, 1)}}
    assert kept == {1: {(1, 4)}}
    with pytest.raises(ValueError, match="Graph component"):
        groups({"foreign": (1, 90, 0)}, ["foreign"])
