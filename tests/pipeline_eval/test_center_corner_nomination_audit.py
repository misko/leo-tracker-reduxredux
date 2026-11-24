import json
from pathlib import Path

import pytest

from reports.ALGO08.v3 import center_corner_nomination_audit as census


def test_two_centres_and_one_matching_corner_need_two_duplicate_occurrences():
    one_repeat = census.signature_budget(8, 7)
    assert one_repeat["any_two_centre_agreement_possible"]
    assert not one_repeat["two_centre_and_first_corner_agreement_possible"]
    assert one_repeat["corner_exclusive_at_least"] == 3
    assert one_repeat["corner_exclusive_at_least_if_two_centres_agree"] == 4
    assert one_repeat["distinct_unseen_if_only_two_identical_centres_paid"] == 6
    two_repeats = census.signature_budget(8, 6)
    assert two_repeats["two_centre_and_first_corner_agreement_possible"]
    assert two_repeats["novel_skipped_at_least_if_two_centres_and_first_corner_agree"] == 3
    assert not census.signature_budget(8, 8)["any_two_centre_agreement_possible"]


def test_only_the_original_work_after_paid_centres_is_counted():
    assert census.subsequent_scope(5.0, 3.0, 1.8) == 2.0
    assert census.subsequent_scope(0.122) == 0.122
    with pytest.raises(ValueError, match="disjoint"):
        census.subsequent_scope(5.0, 3.0, 2.1)
    with pytest.raises(ValueError, match="Inconsistent"):
        census.signature_budget(8, 9)


def test_a_sorted_score_cannot_establish_which_anchor_first_proposed_the_winner():
    rows = [dict(node_index=i, cold_score=score) for i, score in enumerate((11., 9., 12., 13., 8., 14.))]
    assert census.corner_origin(rows, 4) == dict(node_index=4, cold_score=8., centre_score_lower_bound=9.,
                                                  improvement_at_least=1.)
    with pytest.raises(ValueError, match="insertion order"):
        census.corner_origin(sorted(rows, key=lambda row: row["cold_score"]), 4)
    rows[0]["cold_score"] = 7.
    assert census.corner_origin(rows, 4) is None


def test_generated_core_receipt_matches_pinned_archives():
    path = Path(census.__file__).parent/"measurements"/"center-corner-nomination-audit.json"
    sealed = json.loads(path.read_bytes())
    older = sealed.pop("older_direct_corner_winner")
    assert older["ranking"]["node_index"] == 4
    assert sealed == json.loads(json.dumps(census.audit(census.source_documents())))
    assert sealed["disposition"] == "stop_before_paid_validation"
