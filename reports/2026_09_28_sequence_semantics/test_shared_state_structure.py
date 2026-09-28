import numpy as np
from shared_state_structure import loo, runs


def test_runs_do_not_merge_separated_occurrences():
    result = runs([0, 0, 1, 0])
    assert [r["length"] for r in result] == [2, 1, 1]
    assert result[-1]["first_frame"] == 3


def test_prediction_uses_other_members_and_excludes_singletons():
    result = loo(np.array([0, 10, 100]), np.array([0, 0, 1]))
    assert result["count"] == 2
    assert result["state_median_mae"] == 10
