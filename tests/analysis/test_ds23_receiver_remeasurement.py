import pytest
import numpy as np
from probe_ds23_receiver_positions import merge_measurements


def data(ids):
    return dict(rows=[dict(point={'observation_id':i},archived_CFO_hz=10.) for i in ids],
        panel_metadata={'tracks':[dict(key=i,observation_ids=[i]) for i in ids]})


def test_remeasurement_replaces_existing_estimates_without_duplicating_physical_points():
    old=data(['a','b']);new=data(['b','c']);new['rows'][0]['refined']=True
    r=merge_measurements(old,new)
    assert {v['point']['observation_id'] for v in r['rows']}=={'a','b','c'}
    assert next(v for v in r['rows'] if v['point']['observation_id']=='b')['refined']
    assert len(r['panel_metadata']['tracks'])==3


def test_remeasurement_rejects_peak_substitution_or_incomplete_curves():
    old=data(['a']);new=data(['a']);new['rows'][0]['archived_CFO_hz']=20.
    with pytest.raises(ValueError,match='different archived peak'):merge_measurements(old,new)
    new=data(['b']);new['panel_metadata']['tracks'][0]['observation_ids'].append('missing')
    with pytest.raises(ValueError,match='complete curves'):merge_measurements(old,new)


def test_high_leverage_prediction_uncertainty_does_not_become_measurement_noise():
    from ds23_measurement_noise import measurement_scatter
    t=np.r_[np.linspace(0,10,20),36.];rng=np.random.default_rng(8);z=(t-t.mean())/np.ptp(t)
    a=np.vander(z,5,increasing=True);q,_=np.linalg.qr(a);h=np.sum(q*q,axis=1)
    estimates=[];press=[]
    for _ in range(100):
        y=a@np.array([1.,2.,3.,4.,5.])+rng.normal(0,10,len(t));r=y-q@(q.T@y)
        sigma,leverage=measurement_scatter(t,r,4);estimates.append(sigma)
        press.append(np.sqrt(np.mean((r/(1-h))**2)))
    assert leverage>.9999
    assert 8<np.mean(estimates)<12 and np.mean(press)>1000


def test_local_scatter_is_not_inflated_by_a_misjoined_two_point_tail():
    from ds23_measurement_noise import local_scatter
    rng=np.random.default_rng(12);t=np.r_[np.linspace(0,20,19),26.,36.]
    y=100+50*t+2*t*t+.03*t**3+rng.normal(0,10,len(t));y[-2:]+=[2000,8000]
    sigma,windows=local_scatter(t,y)
    assert windows==6 and 5<sigma<20


def test_bounded_carrier_scout_recovers_a_valid_pilot_outside_the_old_local_search():
    from local_pilot_refinement import PilotWorkspace,pilot_wave
    from probe_native_code_carrier import interpolate_periodic
    fs=2500000;n=np.arange(50000);epoch=125.3;truth=120123.4;archived=truth-450
    y=interpolate_periodic(pilot_wave(fs,'lower'),(n-epoch)*32)*np.exp(2j*np.pi*truth*n/fs)
    p=PilotWorkspace(y,fs,'lower',epoch);fixed=p.frequency_fit(archived);old=p.joint_fit(fixed['CFO_hz'])
    f=archived+np.arange(-600,601,20.);seed=f[np.argmax(p.evaluate(f))];new=p.joint_fit(seed)
    assert abs(old['CFO_hz']-truth)>100 and old['frequency_search_boundary']
    assert abs(new['CFO_hz']-truth)<2 and new['margin']>0
    assert new['score']>old['score']+1e-5 and abs(new['CFO_hz']-archived)<=800
