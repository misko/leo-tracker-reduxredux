import sys
from pathlib import Path
import numpy as np
from model import phase_covariance,weights,evaluate
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'2026_09_27_ds6_dwell_phase'))
from test_experiment import synthetic
from experiment import evaluate as unweighted_evaluate

def fixture():
    n=800;p=4;X=np.zeros((n,p),complex)
    X[np.arange(n),np.arange(n)//200]=1
    return [X,X],np.ones(n,bool),np.arange(n)//5

def test_cluster_covariance_against_correlated_noise_monte_carlo():
    X,mask,groups=fixture();rng=np.random.default_rng(11);estimates=[];errors=[]
    beta=np.array([1.,.7,1.4,.5]);signal=np.column_stack([X[0]@beta,X[1]@(beta*np.exp(.4j))])
    for _ in range(300):
        noise=.07*(rng.normal(size=(160,2))+1j*rng.normal(size=(160,2)))
        iq=signal+noise[groups];cov,_=phase_covariance(X,iq,mask,groups)
        co=[np.linalg.lstsq(x,iq[:,rx],rcond=None)[0] for rx,x in enumerate(X)]
        errors.append(np.angle(co[1]*np.conj(co[0]))-.4);estimates.append(np.diag(cov))
    ratio=np.mean(estimates,axis=0)/np.var(errors,axis=0,ddof=1)
    assert np.all((ratio>.75)&(ratio<1.25)),ratio

def test_common_receiver_noise_cancels_and_held_data_cannot_change_covariance():
    X,mask,groups=fixture();mask[::2]=False;rng=np.random.default_rng(7)
    y=X[0]@np.ones(4)+.1*(rng.normal(size=800)+1j*rng.normal(size=800))
    iq=np.column_stack([y,y*np.exp(.4j)])
    a,_=phase_covariance(X,iq,mask,groups)
    assert np.max(abs(a))<1e-20
    iq[~mask]+=100
    b,_=phase_covariance(X,iq,mask,groups)
    np.testing.assert_array_equal(a,b)

def test_uniform_weights_reproduce_previous_fit_and_preserve_phase():
    windows=synthetic()
    for w in windows:w['weight']=np.ones(len(w['data']['fit']['t']))
    a=evaluate(windows,[0,2,5],[1,3,4],.2,True)
    b=unweighted_evaluate(windows,[0,2,5],[1,3,4],.2)
    assert abs(a['held_rms_deg']-b['held_rms_deg'])<1e-6
    assert abs(a['model']['rate']-.13)<1e-5
    assert a['held_rms_deg']<1e-4

def test_weak_pilot_gets_lower_weight():
    w=weights(np.diag([.01,.01,1.,.01]))
    assert w[2]<w[0]/50
    assert np.all(np.isfinite(weights(np.zeros((4,4)))))
