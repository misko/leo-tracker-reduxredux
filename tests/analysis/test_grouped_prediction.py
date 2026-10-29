import numpy as np
import pytest
from leo.analysis.research.grouped_prediction import grouped_split,predictive_score,polynomial_reference,replay_split,identity_consensus


def test_random_groups_keep_simultaneous_receivers_and_guard_together():
    times=np.repeat(np.arange(120.)+.1,2)
    train,held,r=grouped_split(times,times[(times>=24)&(times<72)],seed=20261029)
    assert np.array_equal(train[::2],train[1::2])
    assert np.array_equal(held[::2],held[1::2])
    assert not np.any(train&held)
    replay_train,replay_held=replay_split(times[::2],r)
    np.testing.assert_array_equal(replay_train,train[::2]);np.testing.assert_array_equal(replay_held,held[::2])
    assert np.array_equal(train,grouped_split(times,times[(times>=24)&(times<72)],seed=20261029)[0])
    assert any(np.diff(r['held_blocks'])>1)  # Random groups, not a final time interval.
    for group in r['held_blocks']:
        assert not train[(times>=group*12-2)&(times<=(group+1)*12+2)].any()
    with pytest.raises(ValueError):grouped_split(times,[1,2,3],seed=0)


def test_held_score_matches_dense_reference_and_charges_uncertainty():
    y=np.array([2.,-1.,4.]);u=np.array([[1.,0.],[1.,1.],[1.,2.]])
    g=np.array([[5.,1.],[1.,3.]]);sigma=np.array([2.,3.,2.])
    cov=np.diag(sigma**2)+u@np.linalg.inv(g)@u.T
    expected=y@np.linalg.solve(cov,y)+np.linalg.slogdet(cov)[1]+3*np.log(2*np.pi)
    assert predictive_score(y,u,g,sigma)['negative_twice_log_density']==pytest.approx(expected)
    small=predictive_score(np.zeros(3),u,g,sigma)['negative_twice_log_density']
    large=predictive_score(np.zeros(3),u,g,sigma*10)['negative_twice_log_density']
    assert large>small


def test_polynomial_preprocessing_cannot_read_held_values():
    t=np.linspace(0,80,81);train,held,_=grouped_split(t,t,seed=94721)
    y=1000-300*t+2*t*t+np.random.default_rng(1).normal(0,20,len(t))
    first=polynomial_reference(t,y,train,held);changed=y.copy();changed[held]+=10000
    second=polynomial_reference(t,changed,train,held)
    assert first['order']==second['order']==2
    np.testing.assert_array_equal(first['coefficient'],second['coefficient'])
    assert first['training_noise_hz']==second['training_noise_hz']
    assert second['held']['rms_hz']>first['held']['rms_hz']+9000


def test_consensus_requires_competitors_both_arms_and_predictive_adequacy():
    import copy
    def proposal(norad,cost):
        return dict(norad=norad,arms={a:dict(scores={'joint':{'negative_twice_log_density':cost},'target':{'rms_hz':70}},
            final_phase_change_s=.001,minimum_target_elevation_deg=20) for a in ('c0','fitted_c')})
    folds=[dict(seed=s,proposals=[proposal(1,100),proposal(2,130)]) for s in (1,2,3)]
    assert identity_consensus(folds)['status']=='conditionally_supported_identity'
    assert identity_consensus(folds)['position_inclusion_authorized'] is False
    changed=copy.deepcopy(folds);changed[0]['proposals'][1]['arms']['c0']['scores']['joint']['negative_twice_log_density']=50
    assert identity_consensus(changed)['status']=='unstable_identity'
    changed=copy.deepcopy(folds);changed[0]['proposals'][0]['arms']['c0']['scores']['target']['rms_hz']=500
    assert identity_consensus(changed)['status']=='prediction_mismatch'
    assert identity_consensus(folds[:1])['status']=='insufficient_partitions'
    conditional=copy.deepcopy(folds)
    for f in conditional:
        for p in f['proposals']:
            for v in p['arms'].values():v['scores']['conditional_target']=v['scores'].pop('joint')
    assert identity_consensus(conditional,score_name='conditional_target')['status']=='conditionally_supported_identity'
