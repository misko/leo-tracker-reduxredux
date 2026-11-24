import pytest

from reports.ALGO08.v3.prefix_owner_reach import changes_by_visit, index_opportunities, summarize


def test_frozen_suffix_counts_shared_changed_added_and_removed_in_each_arm():
    visits = {"a": 0, "b": 64, "c": 129, "d": 141, "e": 149}
    before = [("a", 1, "curved"), ("b", 1, "curved"), ("c", 2, "predictive"), ("d", 3, "curved")]
    after = [("a", 7, "curved"), ("b", 1, "curved"), ("c", 4, "predictive"), ("e", 8, "curved")]
    result = summarize(changes_by_visit(before, after, visits), 64, 150)
    assert result["inside_prefix"] == 1 and result["outside_prefix"] == 3
    assert result["tails"][1]["kinds"] == {"reassigned": 1, "removed": 1, "added": 1}
    assert result["tails"][2]["unreachable_changes"] == 0
    assert result["satellite_transitions"] == [dict(old=2, new=4, count=1)]


def test_reject_unbound_and_duplicate_keys():
    with pytest.raises(ValueError, match="unbound"):
        changes_by_visit([("a", 2, "curved")], [], {})
    row = {"receiver_id": 0, "valid_start_counter": 42, "visit_index": 1}
    with pytest.raises(ValueError, match="Duplicate"):
        index_opportunities({"session_id": "case", "probes": [row, row]})
