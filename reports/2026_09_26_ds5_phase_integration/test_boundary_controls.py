import numpy as np
from scipy.special import logsumexp
from boundary_controls import scale_mixture,score,model_mixture
from segment_uncertainty import common_offset_evidence

def test_sufficient_statistics_match_explicit_scale_pair_integrals():
    rng=np.random.default_rng(71);a=rng.normal(size=(2,3,7))*30;b=rng.normal(size=(2,3,5))*12
    scales=[5,20]
    expected=logsumexp(np.stack([common_offset_evidence(a,b,x,y) for x in scales for y in scales]),axis=0)-np.log(4)
    np.testing.assert_allclose(scale_mixture(a,b,scales),expected,atol=1e-12)

def test_held_values_do_not_change_boundary_training_weights():
    rng=np.random.default_rng(72);bank=dict(train_residual=rng.normal(size=(2,3,8)),held_residual=rng.normal(size=(2,3,8)),logprior=np.full((2,3),-np.log(3)))
    times=np.arange(8.)
    first=score(bank,times,times,4);bank['held_residual']*=100
    second=score(bank,times,times,4)
    assert first['log_train']==second['log_train'] and first['counts']==second['counts']
    assert first['log_full']!=second['log_full']
    assert not score(bank,times,times,1)['eligible']

def test_model_mixture_uses_evidence_not_best_held_boundary():
    alt=[dict(log_train=np.log(2),log_full=np.log(6)),dict(log_train=np.log(4),log_full=np.log(20))]
    assert np.isclose(model_mixture(np.log(1),np.log(2),alt),np.log((2+13)/(1+3)))
    assert model_mixture(2,3,[])==1
