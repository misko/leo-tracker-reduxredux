import numpy as np
import pytest
from scipy.special import logsumexp
from core import exact_soft


def test_one_track_matches_direct_mixture():
    prior=np.log(np.array([.25,.75]));opts={'t':{
        'a':{'train':np.array([[0.,-2.]]),'predict':np.array([[-1.,-3.]]),'n_test':2},
        'b':{'train':np.array([[-1.,0.]]),'predict':np.array([[-2.,-1.]]),'n_test':2}}}
    out=exact_soft(opts,{'a':prior,'b':prior},np.array([0.]))
    tr=np.array([logsumexp(prior+opts['t'][c]['train'][0])-np.log(2) for c in ('a','b')])
    jo=np.array([logsumexp(prior+opts['t'][c]['train'][0]+opts['t'][c]['predict'][0])-np.log(2) for c in ('a','b')])
    assert out['composite_nll_per_test_block']==pytest.approx(-(logsumexp(jo)-logsumexp(tr))/2)
    assert sum(out['tracks'][0]['probabilities'].values())==pytest.approx(1)


def test_null_and_clock_are_normalized():
    row=lambda x:{'train':np.array([[x],[x+1.]]),'predict':np.array([[-.5],[-.25]]),'n_test':1}
    opts={'t':{'a':row(0),'__null__':row(-1)}}
    out=exact_soft(opts,{'a':np.array([0.])},np.log(np.array([.4,.6])))
    assert sum(out['clock_probabilities'])==pytest.approx(1)
    assert sum(out['tracks'][0]['probabilities'].values())==pytest.approx(1)
    assert 0<out['mean_null_probability']<1


def test_rejects_mismatched_denominators():
    opts={'t':{'a':{'train':np.zeros((1,1)),'predict':np.zeros((1,1)),'n_test':1},
        'b':{'train':np.zeros((1,1)),'predict':np.zeros((1,1)),'n_test':2}}}
    with pytest.raises(ValueError,match='denominator'):exact_soft(opts,{'a':np.array([0.]),'b':np.array([0.])},np.array([0.]))


def test_evaluation_data_cannot_change_assignment_posterior():
    prior=np.log(np.array([.5,.5]));base={'t':{
        'a':{'train':np.array([[0.,-1.]]),'predict':np.array([[0.,0.]]),'n_test':1},
        'b':{'train':np.array([[-2.,0.]]),'predict':np.array([[0.,0.]]),'n_test':1}}}
    changed={'t':{c:dict(r,predict=np.array([[1000.,-1000.]])) for c,r in base['t'].items()}}
    a=exact_soft(base,{'a':prior,'b':prior},np.array([0.]))
    b=exact_soft(changed,{'a':prior,'b':prior},np.array([0.]))
    assert a['tracks'][0]['probabilities']==pytest.approx(b['tracks'][0]['probabilities'])
