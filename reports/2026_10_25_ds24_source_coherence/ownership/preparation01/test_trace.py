import numpy as np
from trace import winner, lane_owner


def test_winner_keeps_original_gate_and_rank_tie():
    candidates = [dict(candidate_rank=2, fractional_margin=8., passed_fractional_margin_gate=False),
                  dict(candidate_rank=1, fractional_margin=3., passed_fractional_margin_gate=True),
                  dict(candidate_rank=0, fractional_margin=3., passed_fractional_margin_gate=True)]
    assert winner(candidates) is candidates[2]
    assert winner([candidates[0]]) is None


def test_native_lane_index_ownership_and_gauge():
    lane = [dict(observation_id=str(i), time_s=float(i), measured_cfo_hz=100.+i) for i in range(4)]
    track = dict(key='test', indices=[1, 3], observation_ids=['1', '3'],
                 times=[1., 3.], values=[101.-20., 103.-20.])
    mapping, shift = lane_owner(track, lane)
    assert mapping == {'1': 'test', '3': 'test'}
    assert np.allclose(shift, -20.)
    bad = dict(track, observation_ids=['0', '3'])
    try:
        lane_owner(bad, lane)
    except AssertionError:
        pass
    else:
        raise AssertionError('native-index mismatch was silently accepted')
