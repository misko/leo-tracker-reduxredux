import numpy as np
import json
from pathlib import Path
from timing_trial import episode_evidence,evaluate
from phase_factor import phase_evidence
from episode_trial import labels
from test_timing_trial import option
from episode_support_audit import supported_breaks

def test_episode_intercepts_are_independently_invariant():
    y=np.array([.2,.3,2.,2.1]);g=np.array([0,0,1,1]);k=np.ones(4)
    prediction=np.array([[.1,.2,.4,.6],[.3,.1,.8,.2]])
    expected=phase_evidence(y[:2],prediction[:,:2],k[:2])+phase_evidence(y[2:],prediction[:,2:],k[2:])
    np.testing.assert_allclose(episode_evidence(y,prediction,k,g),expected)
    np.testing.assert_allclose(episode_evidence(y+np.array([.7,.7,-2,-2]),prediction,k,g),expected)

def test_single_episode_and_neutral_updates():
    y=np.array([.1,.2,.4,.5]);train=np.array([1,0,1,0],bool);f=np.full(4,11.2e9)
    a=[option('a',[[0,.1,.2,.3]],-.5),option('b',[[0,.3,.1,.7]],-1)]
    b=[option('c',[[0,.2,.4,.6]],-.2)]
    default=evaluate(a,b,y,train,f,f,1,n_baseline=5)
    explicit=evaluate(a,b,y,train,f,f,1,n_baseline=5,phase_groups=np.zeros(4,int))
    assert default==explicit
    neutral=evaluate(a,b,y,train,f,f,0,n_baseline=5,phase_groups=np.array([0,0,1,1]))
    assert abs(neutral['cfo_gain'])<1e-12
    assert neutral['maximum_probability_change']<1e-12

def test_independent_singletons_cannot_update_identity():
    y=np.array([.1,.2,.4,.5]);train=np.array([1,0,1,0],bool);f=np.full(4,11.2e9)
    a=[option('a',[[0,.1,.2,.3]],-.5),option('b',[[0,.3,.1,.7]],-1)]
    b=[option('c',[[0,.2,.4,.6]],-.2)]
    result=evaluate(a,b,y,train,f,f,1,n_baseline=5,phase_groups=np.arange(4))
    assert abs(result['cfo_gain'])<1e-12
    assert abs(result['phase_held_vs_uniform'])<1e-12

def test_break_assignment_has_no_future_effect():
    t=np.array([1.,2.,3.,4.]);np.testing.assert_array_equal(labels(t,[2,4]),[0,1,1,2])
    np.testing.assert_array_equal(labels(t,[2,4]),labels(t,[2,4,10]))

def test_supported_predictor_needs_history_and_rejects_long_extrapolation():
    t=np.r_[np.arange(10.),100.,101.,102.,103.,104.,105.]
    y=.01*t*t+2*t
    rows,breaks=supported_breaks(t,y)
    assert not breaks and not rows[10]['supported']
    assert all(not r['supported'] for r in rows[:5])
    y[7:]+=1000
    rows,breaks=supported_breaks(t,y)
    assert breaks==[7]
    assert supported_breaks(t[:10],y[:10])==(rows[:10],[7])

def test_neutral_episodes_cannot_change_orbital_evidence():
    y=np.array([1.,2.,3.,4.]);k=np.array([0.,0.,1.,1.]);g=np.array([0,0,1,1]);model=np.arange(12.).reshape(3,4)
    np.testing.assert_allclose(episode_evidence(y,model,k,g),phase_evidence(y,model,k),atol=1e-12)

def test_real_episode_trial_keeps_cfo_coverage_and_baseline():
    root=Path(__file__).resolve().parent
    data=json.loads((root/'phase-episodes/results.json').read_text())['experiments']
    assert len(data)==8
    for r in data:
        if r['arm']!='continuous':continue
        other=next(x for x in data if x['session_id']==r['session_id'] and x['fold']==r['fold'] and x['arm']=='timing_episodes')
        for key in ('exact_cfo_held','pairs','cfo_probabilities','kappa','training_mask','phase_times_s'):
            assert r[key]==other[key]
        assert np.isclose(sum(other['phase_updated_probabilities']),1)
