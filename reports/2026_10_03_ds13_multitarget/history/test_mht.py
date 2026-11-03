import importlib.util, sys
from pathlib import Path
import numpy as np

P=Path(__file__).with_name('mht.py'); S=importlib.util.spec_from_file_location('mht',P); m=importlib.util.module_from_spec(S); sys.modules['mht']=m; S.loader.exec_module(m)

def run(res, em, groups, **kw):
    kw.setdefault('state',False)
    hs,_=m.track(np.arange(len(groups),dtype=float),np.asarray(groups),np.asarray(res,float),np.log(np.asarray(em,float)),beam=64,top_per_row=2,group_cap=64,sigma=1.,stationary_sigma=.5,timescale=3.,miss=.2,**kw)
    return m.marginals(hs,len(groups),np.asarray(res).shape[1])[0],hs

def test_simultaneous_exclusive_and_misses():
    p,hs=run([[0,9],[9,0],[.1,8],[8,.1]],[[.9,.1],[.1,.9],[.9,.1],[.1,.9]],[0,0,1,1])
    assert p[0,0]>.75 and p[1,1]>.75
    for h in hs:
        for g in h.assignments:
            used=[s for _,s in g if s>=0]; assert len(used)==len(set(used))
    p,_=run([[0,9],[9,9]],[[.9,.01],[1e-12,1e-12]],[0,1])
    assert p[1].sum()<.1

def test_crossing_ambiguity_retained_and_state_matters():
    # At the exact crossing both exclusive permutations survive the beam.
    p,hs=run([[-1,1],[1,-1],[0,0],[0,0]],[[.9,.9]]*4,[0,0,1,1])
    assert len(hs)>1 and np.all((p[2:]>0)&(p[2:]<1))
    residual=np.array([[3,8],[3,8],[3,8.]])
    base=np.exp(-.5*residual**2)
    on,_=run(residual,base,[0,1,2],state=True)
    off,_=run(residual,base,[0,1,2],state=False)
    assert on[:,0].sum()>off[:,0].sum()

def test_nonidentifiability_is_not_collapsed():
    p,_=run([[0,0],[0,0]],[[.8,.8],[.8,.8]],[0,1])
    assert np.allclose(p[:,0],p[:,1],atol=1e-10)

def test_tiny_state_off_matches_exact_joint_map():
    gain=np.array([[2., 1.], [1.5, -np.inf]])
    pairs,score=m.common.group_map(gain)
    hs,_=m.track(np.zeros(2),np.zeros(2,int),np.zeros_like(gain),gain,beam=64,state=False,top_per_row=2,group_cap=64)
    assert np.isclose(hs[0].score,score)
    assert {(r,s) for r,s in hs[0].assignments[0] if s>=0}==set(pairs)

def test_predictive_density_normalizer_and_elapsed_time():
    h=m.History(0.,np.array([[20.]]),np.array([[25.]]),np.array([0.]),())
    mean,var,last=m._predict(h,0,30.,10.,30.)
    assert np.allclose(mean,[[20/np.e]])
    assert np.allclose(var,[[25/np.e**2+100*(1-1/np.e**2)]]) and last[0]==30
    # At zero residual/mean, increased predictive variance must reduce density.
    sigma=2.; expected=-.5*np.log((sigma*sigma+var[0,0])/(sigma*sigma))
    gain=np.array([[0.]])
    out=m._choices(m.History(0.,np.zeros((1,1)),var,np.array([30.]),()),np.array([0]),np.zeros((1,1)),gain,lane=0,now=30.,state=True,sigma=sigma,stationary_sigma=10.,timescale=30.,miss=1.,top_per_row=1,group_cap=4)
    assigned=[x for x in out if x.assignments[0][0][1]==0][0]
    assert np.isclose(assigned.score,expected)

def test_receiver_channel_lane_isolation():
    times=np.array([0.,1.]); groups=np.array([0,1]); lanes=np.array([0,1])
    residual=np.array([[80.],[0.]]); gain=np.array([[5.],[5.]])
    hs,_=m.track(times,groups,residual,gain,lanes=lanes,beam=1,state=True,sigma=20.,stationary_sigma=100.,timescale=30.)
    assert hs[0].mean[0,0]>0 and abs(hs[0].mean[1,0])<1e-12
