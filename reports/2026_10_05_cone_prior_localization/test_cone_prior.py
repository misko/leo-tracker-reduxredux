import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import experiment as study
from cone_geometry import cone_marginals, tilt, Support
from cone_model import probabilities, project, frame, BORESIGHTS_DEG
from cone_selection import ConeSearch
from penalty_replace_search import Search
from greedy_restart_scan import compile_mode


def test_cone_marginal_and_direction_gradient():
    rng=np.random.default_rng(3);u=rng.normal(size=(30,3));u/=np.linalg.norm(u,axis=1)[:,None]
    theta=np.array([.6,.4,np.log(.3),.2,.7]);frames=np.array([frame(*b) for b in BORESIGHTS_DEG])
    v,j=cone_marginals(u,theta,frames);p=probabilities(theta,project(u))
    np.testing.assert_allclose(v,np.column_stack([1-p[:,1],1-p[:,0]]),atol=1e-14)
    for axis in range(3):
        d=np.eye(3)[axis]*1e-6
        numeric=(cone_marginals(u+d,theta,frames)[0]-cone_marginals(u-d,theta,frames)[0])/2e-6
        np.testing.assert_allclose(j[...,axis],numeric,atol=1e-7)


def test_mass_conservation_zero_parity_and_gradient():
    rng=np.random.default_rng(5);b=rng.uniform(.001,.04,(5,7));la=rng.normal(0,.3,b.shape);g=rng.normal(size=b.shape)
    np.testing.assert_allclose(tilt(b,np.zeros_like(b)),b,atol=1e-16)
    q,db,dl=tilt(b,la,g)
    np.testing.assert_allclose(q.sum(axis=1),b.sum(axis=1),atol=1e-16)
    assert np.all(q<1)
    for i,j in [(0,0),(2,5),(4,6)]:
        step=np.zeros_like(b);step[i,j]=1e-6
        nb=np.sum(g*(tilt(b+step,la)-tilt(b-step,la)))/2e-6
        nl=np.sum(g*(tilt(b,la+step)-tilt(b,la-step)))/2e-6
        np.testing.assert_allclose(db[i,j],nb,atol=1e-8)
        np.testing.assert_allclose(dl[i,j],nl,atol=1e-8)


def test_support_gradient():
    axis=np.linspace(-1,1,31);x,y=np.meshgrid(axis,axis);inside=x*x+y*y<=1
    supported=(x[inside]>.1)&(y[inside]>-.2)
    support=Support(inside,supported)
    u=np.array([[.3,.1,.95],[-.1,.2,.97],[0.,0.,1.]])
    v,j=support.evaluate(u)
    for axis in range(3):
        delta=np.eye(3)[axis]*1e-6
        numeric=(support.evaluate(u+delta)[0]-support.evaluate(u-delta)[0])/2e-6
        np.testing.assert_allclose(j[:,axis],numeric,atol=1e-5)


def test_selection_zero_parity_and_sky_prefers_supported_identity():
    times=np.linspace(0,12,24);group=np.arange(24);rx=np.zeros(24,int);ch=np.ones(24,int)
    modes=[]
    for sat,evidence in [(100,-1.),(200,.5)]:
        mode=compile_mode(dict(catalog_number=sat,offset_s=0.,eligible_rows=list(range(24)),residual_hz=[0.]*24),rx,ch)
        mode['sky_log_odds']=np.full(24,evidence);modes.append(mode)
    original=Search(modes,group,times).run(3)
    zero=ConeSearch(modes,group,times,strength=0.).run(3)
    assert original['final']['assignments']==zero['final']['assignments']
    assert original['final']['objective']==zero['final']['objective']
    new=ConeSearch(modes,group,times,strength=1.).run(3)
    assert [m['catalog_number'] for m in new['final']['selected']]==[200]
    assert new['final']['assigned']==24


def test_polish_ties_use_stationarity_not_position_error():
    from polish import choose
    records=[dict(objective=40000.,kkt_residual=.1,point_km=[0.,0.]),
             dict(objective=40000.+1e-10,kkt_residual=1e-5,point_km=[3.,0.]),
             dict(objective=40000.+1e-5,kkt_residual=0.,point_km=[0.,0.])]
    assert choose(records) is records[1]
    records[0]['objective']-=1e-5
    assert choose(records) is records[0]


@pytest.mark.real_corpus
def test_real_n01_position_gradient_and_zero_strength_parity():
    from position_visibility_study import Objective as Reference
    from position_structure_study import seed_vector
    from full_data_timing_priors import load
    data,saved,_=load('N01')
    data=SimpleNamespace(**vars(data))
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows','owners','fixed_receiver_hz'):
        setattr(data,key,getattr(data,key)[:80])
    theta,frames,support,_=study.bundle();center=saved['input_metadata']['rf_center_hz']
    for arm in study.ARMS:
        ref=Reference(data,center,arm,'Q1','ordinary')
        seed=saved['arms'][arm]['best']
        for strength in (0.,.5):
            obj=study.Objective(data,center,arm,strength,theta,frames,support)
            v=seed_vector(obj,seed,arm);val,g=obj.evaluate(v)
            if strength==0:
                vr,gr=ref.evaluate(v)
                np.testing.assert_allclose(val,vr,atol=1e-8,rtol=0)
                np.testing.assert_allclose(g,gr,atol=1e-7,rtol=0)
            for i in (0,1,2,3,6,7,8,obj.size):
                step=1e-3 if i in (2,obj.size) else 1e-5
                dv=np.eye(len(v))[i]*step
                numeric=(obj.evaluate(v+dv)[0]-obj.evaluate(v-dv)[0])/(2*step)
                np.testing.assert_allclose(g[i],numeric,atol=3e-4,rtol=2e-4,
                                           err_msg=f'{arm} strength {strength} parameter {i}')
