from copy import deepcopy

import pytest

from tools.research.replay_shared_cfo_nested import select_training_candidate


def test_training_selection_includes_shared_and_ignores_held_outcomes():
    candidates = {
        "independent": {"train_sse": 5.0, "held_sse": 0.0},
        "shared": {"train_sse": 4.0, "held_sse": 100.0},
        "refined": {"train_sse": 3.0, "held_sse": 200.0},
    }
    assert select_training_candidate(candidates)[0] == "refined"
    changed = deepcopy(candidates)
    changed["refined"]["held_sse"] = 1e99
    assert select_training_candidate(changed)[0] == "refined"
    del candidates["refined"]
    assert select_training_candidate(candidates)[0] == "shared"


def test_invalid_training_score_rejected():
    with pytest.raises(ValueError):
        select_training_candidate({"bad": {"train_sse": float("nan")}})
