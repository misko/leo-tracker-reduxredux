from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_channel_rate_transfer import designs,fit,baseline_prediction,transfer
from ds23_channel_clock_screen import predictive_score


def evidence():
    t=np.arange(0.,150.,.8);ch=np.where(np.arange(len(t))%2,1,2);fr=ch
    base,clock=designs(t,ch,fr,[1,2],[1,2],center_s=75.,scale_s=75.)
    y=10000+3*t+.07*t*t+clock[:,0]*3+np.random.default_rng(53).normal(0,15,len(t))
    train=(np.floor(t/15).astype(int)%3)!=1
    return t,base,clock,y,train


def test_channel_clock_contrast_cannot_contain_a_common_rate():
    b,c=designs([0.,0.],[1,2],[1,2],[1,2],[1,2],center_s=0,scale_s=1.)
    np.testing.assert_allclose(c.sum(axis=0),0,atol=1e-14)


def test_source_clock_improves_other_receiver_prediction():
    t,b,c,y,train=evidence();noise=np.full(len(t),40.)
    source=fit(b[train],c[train],y[train],noise[train])
    target=y+1000+np.random.default_rng(2).normal(0,15,len(y))
    null=fit(b[train],np.zeros((train.sum(),0)),target[train],noise[train])
    p,cov=transfer(source,null,b[train],c[train],noise[train],b[~train],c[~train],noise[~train])
    q,old=baseline_prediction(null,b[~train],noise[~train])
    assert predictive_score(p,cov,target[~train])<predictive_score(q,old,target[~train])-50


def test_receiver_specific_clock_hurts_transfer_to_a_clean_receiver():
    t,b,c,y,train=evidence();noise=np.full(len(t),40.)
    source=fit(b[train],c[train],y[train],noise[train]);target=10000+3*t+.07*t*t
    null=fit(b[train],np.zeros((train.sum(),0)),target[train],noise[train])
    p,cov=transfer(source,null,b[train],c[train],noise[train],b[~train],c[~train],noise[~train])
    q,old=baseline_prediction(null,b[~train],noise[~train])
    assert predictive_score(p,cov,target[~train])>predictive_score(q,old,target[~train])+50


def test_target_clock_uncertainty_is_from_source_not_retrained():
    t,b,c,y,train=evidence();noise=np.full(len(t),40.)
    source=fit(b[train],c[train],y[train],noise[train]);null=fit(b[train],np.zeros((train.sum(),0)),y[train],noise[train])
    _,cov=transfer(source,null,b[train],c[train],noise[train],b[~train],c[~train],noise[~train])
    _,old=baseline_prediction(null,b[~train],noise[~train])
    assert np.linalg.eigvalsh(cov-old).min()>-1e-7


def test_unseen_fragment_keeps_its_prior_in_predictive_variance():
    t=np.arange(30.);b,c=designs(t,np.where(t%2,1,2),np.zeros(30,int),[1,2],[0,1],center_s=15,scale_s=15)
    model=fit(b,np.zeros((30,0)),t*t,np.full(30,40.))
    b1,_=designs([10.],[1],[1],[1,2],[0,1],center_s=15,scale_s=15)
    b0,_=designs([10.],[1],[0],[1,2],[0,1],center_s=15,scale_s=15)
    assert baseline_prediction(model,b1,[40.])[1][0,0]>baseline_prediction(model,b0,[40.])[1][0,0]+300.**2


def test_invalid_channel_and_noise_inputs_fail_explicitly():
    with pytest.raises(ValueError):designs([0.],[3],[0],[1,2],[0],center_s=0,scale_s=1)
    _,b,c,y,_=evidence()
    with pytest.raises(ValueError):fit(b,c,y,np.zeros(len(y)))
