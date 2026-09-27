import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from score import shared_time_score

def test_time_is_shared_not_independently_reselected_per_track():
    evidence=np.array([[0.,-100.],[-100.,0.]])
    assert np.isclose(shared_time_score(evidence),-100.)
    independently_reselected=np.sum(logsumexp(evidence,axis=1)-np.log(2))
    assert independently_reselected-shared_time_score(evidence)>98

def test_shared_time_matches_explicit_mixture():
    evidence=np.log(np.array([[.2,.8],[.4,.6],[.9,.1]]))
    assert np.isclose(shared_time_score(evidence),np.log((.2*.4*.9+.8*.6*.1)/2))

def test_whole_visit_assignment_and_exact_phase_join():
    data=json.loads((Path(__file__).with_name('inputs.json')).read_text());parts={};ids={t['track_id'] for t in data['tracks']}
    for track in data['tracks']:
        assert len(track['visits'])==len(track['candidate_ids'])==len(track['times_s'])
        for visit,mask in zip(track['visits'],track['training_mask']):
            assert visit not in parts or parts[visit]==mask
            parts[visit]=mask
    for row in data['phase_joins']:
        for mode in row['modes']:
            for rx in mode:
                for tid in rx['alltrack_ids']:
                    assert tid in ids
                    track=next(t for t in data['tracks'] if t['track_id']==tid)
                    assert rx['candidate_id'] in track['candidate_ids']
                    idx=track['candidate_ids'].index(rx['candidate_id'])
                    assert track['visits'][idx]==row['visit']
    assert len(data['recurring_rx0_pairs'])==1
