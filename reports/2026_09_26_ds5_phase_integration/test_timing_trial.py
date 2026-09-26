import numpy as np
from pathlib import Path
import json
from scipy.special import logsumexp
from timing_trial import evaluate,quantile_indices
from phase_factor import phase_evidence

def option(cid,projection,held):
    return dict(candidate_id=cid,train=0.,held=held,sample_held=np.full(len(projection),held),projection=np.array(projection,float),joint_projection=np.array(projection,float))

def test_quantiles_include_equal_mass_posterior():
    assert np.array_equal(quantile_indices(np.log([.25,.5,.25]),4),[0,1,1,2])
    assert np.array_equal(quantile_indices(np.array([-np.inf,0.,-np.inf]),4),[1,1,1,1])

def test_zero_phase_concentration_is_neutral():
    y=np.array([.1,.2,.4,.5]);train=np.array([1,0,1,0],bool)
    left=[option('a',[[0,.1,.2,.3]],-.5),option('b',[[0,.3,.1,.7]],-1)]
    right=[option('c',[[0,.2,.4,.6]],-.2)]
    result=evaluate(left,right,y,train,np.full(4,11.2e9),np.full(4,11.2e9),0,n_baseline=5)
    assert result['maximum_probability_change']<1e-12
    assert abs(result['cfo_gain'])<1e-12
    assert abs(result['quantile_error_nats'])<1e-12
    assert abs(result['phase_held_vs_uniform'])<1e-12

def test_identical_geometry_does_not_change_identity_weights():
    y=np.array([.1,.2,.4,.5]);train=np.array([1,0,1,0],bool)
    left=[option('a',[[0,.1,.2,.3]],-.5),option('b',[[0,.1,.2,.3]],-1)]
    right=[option('c',[[0,.2,.4,.6]],-.2)]
    result=evaluate(left,right,y,train,np.full(4,11.2e9),np.full(4,11.2e9),1,n_baseline=5)
    assert result['maximum_probability_change']<1e-12
    shifted=evaluate(left,right,y+1.2,train,np.full(4,11.2e9),np.full(4,11.2e9),1,n_baseline=5)
    assert np.isclose(result['phase_held_vs_uniform'],shifted['phase_held_vs_uniform'])

def test_joint_timing_quadrature_matches_exact_discrete_integral():
    y=np.array([.1,.2,.4,.5]);train=np.array([1,0,1,0],bool)
    p0=[0,.001,.002,.003];p1=[0,.002,.005,.009]
    left=option('a',[p0,p0,p1,p1],np.log(2))
    left['sample_held']=np.log([1,1,3,3])
    left['joint_projection']=np.array([p0,p1,p1,p1])
    right=option('b',[[0,0,0,0]],0)
    f=np.full(4,11.2e9);B=np.linspace(-2,2,5)
    result=evaluate([left],[right],y,train,f,f,1,n_baseline=5)
    prediction=-2*np.pi*B[:,None,None]*np.array([p0,p1])[None,:,:]*f/299792458.
    tr=phase_evidence(y[train],prediction[...,train],np.ones(train.sum()))
    exact=logsumexp(tr+np.log([1,3])[None,:])-logsumexp(tr)-np.log(2)
    assert np.isclose(result['cfo_gain'],exact,atol=1e-12)

def test_real_results_keep_all_dwell_pairs_and_normalized_posteriors():
    root=Path(__file__).resolve().parent/'timing-trial'
    files=sorted(root.glob('*-q33.json'));assert len(files)==4
    for f in files:
        d=json.loads(f.read_text());assert len(d['observations'])==18
        assert len({r['visit'] for r in d['observations']})==18
        assert 0<sum(d['phase_training_mask'])<18
        for e in d['experiments']:
            assert np.isfinite(e['cfo_gain'])
            assert np.isclose(sum(e['cfo_probabilities']),1)
            assert np.isclose(sum(e['phase_updated_probabilities']),1)
    for f in root.glob('*-f1-q65-b161-membership.json'):
        d=json.loads(f.read_text())
        assert d['shared_probe_source_groups']>0
        assert all(len(t['equivalent_in_production_input'])==1 for t in d['tracks'])
