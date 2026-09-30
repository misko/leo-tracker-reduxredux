import numpy as np
from episode_controls import credit, shared_state


def test_ties_receive_fractional_credit_without_true_label_tiebreak():
    assert credit(np.array([.5, .5, .1]), [True, False, False]) == .5
    assert credit(np.array([.1, .2, .3]), [True, False, False]) == 0


def test_missing_state_is_not_different_state():
    assert shared_state({"known_tail_states": []}, {"known_tail_states": [1]}) == -1
    assert shared_state({"known_tail_states": [1]}, {"known_tail_states": [2]}) == 0
    assert shared_state({"known_tail_states": [1]}, {"known_tail_states": [1, 2]}) == 1
