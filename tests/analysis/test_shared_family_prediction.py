import numpy as np
import pytest
from types import SimpleNamespace
from validate_shared_family_prediction import prediction_masks,bias_only_projection,family_inputs


def test_bidirectional_prediction_keeps_held_and_target_roles_separate():
    train=np.array([1,0,1,0,0],bool);held=np.array([0,1,0,1,0],bool);target=np.array([0,0,1,1,1],bool)
    masks=prediction_masks(train,held,target)
    assert np.flatnonzero(masks['family_to_target'][0]).tolist()==[0]
    assert np.flatnonzero(masks['family_to_target'][1]).tolist()==[3]
    assert np.flatnonzero(masks['combined_to_family'][0]).tolist()==[0,2]
    assert np.flatnonzero(masks['combined_to_family'][1]).tolist()==[1]
    assert all(not np.any(a&b) for a,b in masks.values())
    with pytest.raises(ValueError,match='disjoint'):prediction_masks(train,train,target)


def test_bias_projection_uses_training_values_only():
    y=np.array([0.,10.,100.]);mean=np.zeros((1,3));cov=np.eye(3);cov[1:,1:]+=100
    kwargs=dict(family_train=np.array([1,0,0],bool),target_train=np.array([0,1,0],bool),target_held=np.array([0,0,1],bool),bias_sigma=10.)
    a=bias_only_projection(y,mean,cov[None],np.zeros(1),**kwargs)
    assert a['bias_hz']==pytest.approx(1000/101)
    changed=y.copy();changed[-1]=-1000
    b=bias_only_projection(changed,mean,cov[None],np.zeros(1),**kwargs)
    np.testing.assert_allclose(a['held_mean_hz'],b['held_mean_hz'])


def test_family_exclusion_preserves_only_original_retained_points():
    tracks=[dict(key=str(i),times=np.array([0.,1.]),values=np.array([i,i+1.]),observation_ids=[f'{i}a',f'{i}b']) for i in range(3)]
    scan=SimpleNamespace(tracks=tracks,rx_basis=[np.ones((2,1)) for _ in tracks],norads=[100,200])
    p=SimpleNamespace(rows=[{'candidate_index':0},{'candidate_index':1}],members=[0,1],slices=[slice(0,2),slice(2,4)],alias=[0,0])
    d={'scan':scan,'keep':np.array([1,0,1,1],bool),'entries':[]}
    targets=[dict(track_index=2,candidate_index=0,alias=1,observation_ids=['2a','2b'])]
    changed,entries,keep=family_inputs(d,p,targets)
    np.testing.assert_array_equal(keep,[False,False,True,True])
    assert entries[0]['observation_ids']==['0a']
    assert changed.tracks[0]['observation_ids']==['0a']
    assert scan.tracks[0]['observation_ids']==['0a','0b']
    np.testing.assert_array_equal(d['keep'],[True,False,True,True])
