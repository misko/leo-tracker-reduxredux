import numpy as np
from scipy.special import logsumexp
from cfo_scale_mixture import mixed_options
from catalogue_trial import constant_log_evidence
from timing_trial import options
from cfo_epoch_audit import causal_breaks

def bank():
    rng=np.random.default_rng(62)
    return dict(candidate_ids=np.array(['a','b']),taus=np.arange(5.),
                logprior=np.full((2,5),-np.log(5)),
                train_residual=rng.normal(size=(2,5,8))*10,
                held_residual=rng.normal(size=(2,5,4))*20,
                projection=rng.normal(size=(2,5,3)))

def test_scale_and_time_evidence_matches_explicit_sum():
    b=bank();scales=[5.,20.];out,diagnostic=mixed_options(b,scales)
    for i,row in enumerate(out):
        tr=[];full=[]
        for s in scales:
            for j in range(5):
                prior=-np.log(10)
                tr.append(constant_log_evidence(b['train_residual'][i,j],s)+prior)
                full.append(constant_log_evidence(np.r_[b['train_residual'][i,j],b['held_residual'][i,j]],s)+prior)
        assert np.isclose(row['train'],logsumexp(tr))
        assert np.isclose(row['held'],logsumexp(full)-logsumexp(tr))
    assert np.isclose(sum(diagnostic['training_scale_probabilities']),1)

def test_held_data_cannot_select_training_scale():
    b=bank();a,da=mixed_options(b,[5,20]);b['held_residual']*=100
    z,dz=mixed_options(b,[5,20]);assert da==dz
    for x,y in zip(a,z):
        assert x['train']==y['train']
        assert x['scale_probabilities']==y['scale_probabilities']
        np.testing.assert_array_equal(x['projection'],y['projection'])

def test_single_scale_matches_previous_integrator():
    b=bank();a,_=mixed_options(b,[20],33)
    previous={x['candidate_id']:x for x in options(b,20,33)}
    for x in a:
        y=previous[x['candidate_id']]
        for field in ('train','held','sample_held','projection','joint_projection'):
            np.testing.assert_allclose(x[field],y[field])

def test_epoch_break_is_causal_and_recovers_after_jump():
    t=np.arange(30,dtype=float);y=2*t+.01*t*t
    assert causal_breaks(t,y)[1]==[]
    y[12:]+=1000
    innovations,breaks=causal_breaks(t,y)
    assert breaks==[12]
    assert causal_breaks(t[:15],y[:15])==(innovations[:15],[12])
