import pytest
from selection_frequency_counterexample import cost


def test_frequency_penalty_is_not_only_a_timing_tie_breaker():
    assert cost([0.,200.],0.,[0.])==pytest.approx(.5)
    assert cost([200.,200.],0.,[0.])>cost([0.,0.],1.,[0.])


def test_timing_score_uses_other_satellites_in_common_gauge():
    assert cost([0.],2.,[2.])==pytest.approx(.02)
