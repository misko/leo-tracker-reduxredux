import numpy as np
from types import SimpleNamespace
from experiment import held_indices,gaussian_prediction,preserve,ranking_key


def test_whole_family_excluded_including_newly_recovered_points():
    p=SimpleNamespace(keep=np.array([True,True,True,True,True,True]),
        rows=[dict(candidate_index=1),dict(candidate_index=2),dict(candidate_index=1)],
        slices=[slice(0,2),slice(2,4),slice(4,6)])
    old=np.array([True,True,True,True,False,False])
    train,held=held_indices(p,old,1)
    assert train.tolist()==[False,False,True,True,False,False]
    assert held.tolist()==[True,True,False,False,False,False]


def test_prediction_carries_shared_phase_and_radio_uncertainty():
    raw=np.array([2.,3.]);u=np.ones((2,1));noise=np.ones(2)
    score,cov=gaussian_prediction(raw,u,np.array([.25]),np.zeros((0,1)),np.zeros(0),noise)
    expected=np.eye(2)+4*np.ones((2,2))
    np.testing.assert_allclose(cov,expected)
    np.testing.assert_allclose(score,raw@np.linalg.solve(expected,raw)+np.linalg.slogdet(expected)[1]+2*np.log(2*np.pi))


def test_parent_ids_required_in_both_arms():
    p={a:dict(accepted_observation_ids=['a','b']) for a in ['c0','fitted_c']}
    c={a:dict(accepted_observation_ids=['a','b','c']) for a in p}
    assert preserve(p,c)
    c['fitted_c']['accepted_observation_ids']=['a','c']
    assert not preserve(p,c)


def test_original_ranking_does_not_read_geography():
    def trial(points,loss):return dict(added_curved_points=points,additions=[dict(component='x')],arms={'c0':{'corrected_selection_loss':loss}})
    assert ranking_key(trial(20,100))<ranking_key(trial(10,1))
