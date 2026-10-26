"""Mask geometry, full covariance, and actual-data held-response isolation."""
import copy
from pathlib import Path
import numpy as np
from common import module,ROOT,context,h,fit,metadata

residual=module('residual_experiment',ROOT/'residual/run.py')
matched=module('matched_experiment',ROOT/'matched/run.py')


def test_matching_preserves_equal_family_receiver_time_counts_and_ownership():
    rng=np.random.default_rng(72);n=350
    m=dict(channel=rng.integers(1,9,n),family=rng.integers(0,4,n),
        receiver=rng.integers(1,3,n),time=rng.uniform(0,120,n))
    keep=rng.random(n)>.1;original=keep.copy();choices,_=matched.masks(keep,m,310)
    repeated,_=matched.masks(keep,m,310)
    for name,mask in choices.items():
        assert np.array_equal(mask,repeated[name]) and not (mask&~keep).any()
    for rep in range(3):
        low=choices[f'matched_low_{rep}'];high=choices[f'matched_high_{rep}']
        assert not (low&high).any() and low.sum()==high.sum()
        def counts(mask):
            cells={}
            for i in np.flatnonzero(mask):
                k=(m['family'][i],m['receiver'][i],int(m['time'][i]//20));cells[k]=cells.get(k,0)+1
            return cells
        assert counts(low)==counts(high)
    assert np.array_equal(keep,original)


def test_joint_predictive_density_preserves_shared_covariance():
    rng=np.random.default_rng(10);raw=rng.normal(size=17);u=rng.normal(size=(17,6));sigma=rng.uniform(.4,2,17)
    c=np.diag(sigma**2)+u@u.T
    expected=raw@np.linalg.solve(c,raw)+np.linalg.slogdet(c)[1]+17*np.log(2*np.pi)
    assert abs(h.gaussian_score(raw,u,sigma)['negative_twice_log_density']-expected)<1e-10


def test_actual_held_receiver_and_family_responses_cannot_change_training():
    d=context('DS24-0010');nominee=residual.nominate(d)[0]
    for receiver in (None,1,2):
        train,held,entries=residual.split(d,nominee['family'],receiver)
        unseen=[nominee['family']] if receiver is None else []
        ref=h.causal_reference(train,unseen)
        p=h.build(train,'fitted_c',ref,'sharedRF50');before=p.calculate([.2,-.3])
        altered=dict(train);altered['scan']=copy.copy(train['scan']);altered['scan'].tracks=copy.deepcopy(train['scan'].tracks)
        targets={i for i,sl in zip(p.members,p.slices,strict=True) if held[sl].any()}
        targets.update(e['track_index'] for e in entries)
        for i in targets:altered['scan'].tracks[i]['values']=np.asarray(altered['scan'].tracks[i]['values'])+12345
        q=h.build(altered,'fitted_c',ref,'sharedRF50');after=q.calculate([.2,-.3])
        assert before['negative_twice_elbo']==after['negative_twice_elbo']
        np.testing.assert_array_equal(before['coefficient'],after['coefficient'])
        np.testing.assert_array_equal(before['noise_precision'],after['noise_precision'])
        if receiver is None:
            np.testing.assert_array_equal(fit(p,np.zeros(2),iterations=8)['parameters'],
                                          fit(q,np.zeros(2),iterations=8)['parameters'])


def test_empty_cross_band_overlap_remains_empty_not_replaced():
    n=20;m=dict(channel=np.r_[np.ones(10),np.full(10,8)],family=np.r_[np.zeros(10),np.ones(10)],
        receiver=np.ones(n),time=np.arange(n))
    choices,_=matched.masks(np.ones(n,bool),m,3)
    assert not choices['matched_low_0'].any() and not choices['matched_high_0'].any()
