"""Ensure the artifact audit rejects changed decisions and unequal search banks."""

import pytest
from verify import check_common_bank, check_detection_counts


def test_frozen_threshold_strict_inequality_and_count():
    assert check_detection_counts([0.1, 0.2, 0.3], 0.2, 3, 1).tolist() == [False, False, True]
    with pytest.raises(ValueError, match="detection count"):
        check_detection_counts([0.1, 0.2, 0.3], 0.2, 3, 2)


@pytest.mark.parametrize("scores", [[0.1], [0.1, float("nan")]])
def test_incomplete_or_nonfinite_saved_scores_fail(scores):
    with pytest.raises(ValueError, match="geometry or nonfinite"):
        check_detection_counts(scores, 0.2, 2, 0)


def test_different_candidate_order_is_allowed_but_missing_candidate_fails():
    bank = [{"candidate_id": i} for i in range(8)]
    row = {"candidate_bank": bank, "methods": {"current": bank, "other": bank[::-1]}}
    check_common_bank(row)
    row["methods"]["other"] = bank[:-1]
    with pytest.raises(ValueError, match="identical candidate bank"):
        check_common_bank(row)


def test_duplicate_common_candidate_fails_even_if_each_method_copies_it():
    bank = [{"candidate_id": i} for i in range(7)] + [{"candidate_id": 0}]
    with pytest.raises(ValueError, match="common candidate inventory"):
        check_common_bank({"candidate_bank": bank, "methods": {"current": bank}})
