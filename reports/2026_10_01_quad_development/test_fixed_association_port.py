import numpy as np
import pytest
from fixed_association_port import FixedAssociationPort


class Port:
    candidate_count = 2
    observation_ids = ('a', 'b')
    observation = np.array([3.])
    def score_selected(self, state, index): return float(state[0]+index-10)
    def predict_selected(self, state, index): return (state[0], index)


@pytest.mark.parametrize('index', [0, 1, 2])
def test_selected_score_is_preserved_without_renormalization(index):
    base = Port(); port = FixedAssociationPort(base, index); x = np.array([2.])
    scores = port.score_all(x)
    assert np.argmax(scores) == index
    assert scores[index] == base.score_selected(x, index) == port.score_selected(x, index)
    assert np.isneginf(np.delete(scores, index)).all()
    assert port.observation_ids == base.observation_ids
    assert port.predict_selected(x, index) == base.predict_selected(x, index)
    with pytest.raises(ValueError): port.score_selected(x, (index+1)%3)
