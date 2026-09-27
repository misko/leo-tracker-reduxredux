import numpy as np
from scipy.optimize import minimize

from run_refit import Objective,BaseObjective,site,REFERENCE_RF_HZ,LIGHT_KM_S


def synthetic():
    center=[37.8,-122.4];rec,up=site(*center)
    east=np.array([-up[1],up[0],0.]);east/=np.linalg.norm(east)
    times=np.linspace(0.,300.,601)
    # Reproducible whole-block random mask rather than a time split.
    groups=np.minimum((times/30).astype(int),9)
    train_groups=np.random.default_rng(2026092731).permutation(10)[:6]
    mask=np.isin(groups,train_groups)
    tracks=[];banks={}
    for rx,rf in [(0,10.71e9),(1,11.95e9)]:
        pos=rec+600*up+(times-150.)[:,None]*east*2
        vel=np.broadcast_to(7.5*east,pos.shape).copy()
        unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[:,None]
        pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
        t=dict(track_id=str(rx),receiver_id=rx,rf_hz=rf,t=times,y=pred+12345.,mask=mask,centered_t=times-times[mask].mean())
        tracks.append(t)
        banks[str(rx)]=(np.broadcast_to(pos,(1,41,len(times),3)).copy(),np.broadcast_to(vel,(1,41,len(times),3)).copy(),np.array([0]))
    return tracks,banks,center


def test_zero_order_matches_existing_mixture_model():
    tracks,banks,center=synthetic()
    model=Objective(tracks,banks,center,1,[0,1],0)
    old=BaseObjective(tracks,banks,center,1,[0,1])
    for x in [np.array([0.,0.,0.]),np.array([1.,-2.,.3])]:
        result=model.evaluate(x);reference=old.evaluate(x,False)
        for k in ['train','held']:np.testing.assert_allclose(result[k],reference[k],atol=1e-9)
        assert result['penalized_train']==result['train']


def test_synthetic_curvature_recovery_and_no_held_leakage():
    tracks,banks,center=synthetic();truth=np.array([3.,-4.,6.,-8.])
    for t in tracks:
        rx=t['receiver_id'];u=(t['t']-150)/150
        t['y']=t['y']+100*(truth[2*rx]*u+truth[2*rx+1]*u*u)*11.2e9/t['rf_hz']
    model=Objective(tracks,banks,center,1,[0,1],2)
    fit=minimize(lambda z:-model.evaluate(np.r_[0.,0.,0.,z])['penalized_train'],np.zeros(4),method='BFGS',options=dict(gtol=1e-5))
    np.testing.assert_allclose(fit.x,truth,atol=.1)
    x=np.r_[0.,0.,0.,fit.x];original=model.evaluate(x)
    changed=[dict(t,y=t['y']+np.where(t['mask'],0.,1e6)) for t in tracks]
    other=Objective(changed,banks,center,1,[0,1],2)
    for candidate in [x,np.r_[1.,-1.,2.,np.zeros(4)]]:
        assert model.evaluate(candidate)['penalized_train']==other.evaluate(candidate)['penalized_train']
    assert other.evaluate(x)['held']<original['held']


def test_frozen_development_results_and_exact_propagation():
    import json
    from run_refit import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert protocol['source_sha256']==digest(HERE/'run_refit.py')
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    assert len(protocol['development_sessions'])==4
    for session in protocol['development_sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete']
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        assert result['input_sha256']==digest(REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json')
        assert set(result['arms'])=={'0','1','2'}
        initial_taus=[]
        for arm in result['arms'].values():
            assert len(arm['runs'])==3
            assert arm['best']==max(arm['runs'],key=lambda r:r['penalized_train'])
            assert arm['best']['success']
            assert not arm['best']['bound_hit']
            assert arm['maximum_interpolation_error_hz']<.05
            assert abs(arm['exact_train']-arm['best']['train'])<1.
            initial_taus.append([r['initial_tau'] for r in arm['runs']])
        assert initial_taus[0]==initial_taus[1]==initial_taus[2]
