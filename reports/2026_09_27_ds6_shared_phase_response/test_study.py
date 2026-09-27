import itertools,json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp,i0
from study import integrate_groups
from information import projected_information

def toy():
    rng=np.random.default_rng(10);groups=[]
    for _ in range(2):
        groups.append(dict(y=rng.normal(size=4),mask=np.array([True,False,True,False]),df=np.linspace(30000,50000,4),geometry=rng.normal(size=(2,2,4)),cfo_train=rng.normal(size=(2,2)),cfo_joint=rng.normal(size=(2,2))))
    return groups

def test_shared_parameters_match_explicit_enumeration():
    groups=toy();delay=np.array([-1e-6,0,1e-6]);weights=np.array([.25,.5,.25]);result=integrate_groups(groups,delay,weights)
    values=[]
    for sign,di,ti,a,b in itertools.product([-1,1],range(3),range(2),range(2),range(2)):
        score=np.log(weights[di]/4)
        for group,ci in zip(groups,[a,b]):
            mask=group['mask'];pred=sign*group['geometry'][ti,ci]+2*np.pi*delay[di]*group['df']
            score+=group['cfo_train'][ti,ci]+np.sum(np.cos(group['y'][mask]-pred[mask])-np.log(i0(1.)))
        values.append(score)
    assert np.isclose(logsumexp(values),result['shared_delay']['training_log_evidence'],atol=1e-12)

def test_held_phase_does_not_tune_training_or_cfo_prediction():
    groups=toy();delay=np.linspace(-1e-6,1e-6,11);weight=np.ones(11)/11;a=integrate_groups(groups,delay,weight)
    for g in groups:g['y'][~g['mask']]+=1.5
    b=integrate_groups(groups,delay,weight)
    for arm in ['independent_offsets','shared_delay']:
        assert a[arm]['training_log_evidence']==b[arm]['training_log_evidence']
        assert a[arm]['held_cfo_log_predictive']==b[arm]['held_cfo_log_predictive']

def test_free_offsets_remove_constant_geometric_information():
    x=np.array([[1,0],[1,0],[0,1],[0,1]],float);j=x@np.array([[1.,2.],[3.,4.]])
    np.testing.assert_allclose(projected_information(j,x),np.zeros((2,2)),atol=1e-25)
    assert np.trace(projected_information(j,np.empty((4,0))))>0

def test_real_delay_quadrature_converges():
    d=json.loads(Path(__file__).with_name('results.json').read_text())
    for key in ['training_log_evidence','held_phase_log_predictive','held_cfo_log_predictive']:
        assert abs(d['401']['scores']['shared_delay'][key]-d['801']['scores']['shared_delay'][key])<1e-5
