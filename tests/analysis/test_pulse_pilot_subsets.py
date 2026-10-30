import numpy as np
import pytest
from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import pilot_wave
from probe_native_code_carrier import interpolate_periodic


def synthetic(fs,split=True,offset=.21):
    n=np.arange(fs//50);epoch=125.3;ppm=13.4
    frame=np.floor((n-epoch)/(fs/750)).astype(int)
    cfo=np.where(frame%2==1,120223.4,120023.4) if split else 120123.4
    rng=np.random.default_rng(471)
    gains=(.8+rng.uniform(0,.4,32))*np.exp(1j*rng.uniform(-np.pi,np.pi,32))
    dc=.05*(rng.normal(size=32)+1j*rng.normal(size=32))
    y=interpolate_periodic(pilot_wave(fs,'upper'),(n-epoch-offset)*(1+ppm*1e-6)*32)*gains[frame+1]*np.exp(2j*np.pi*cfo*n/fs)
    y+=dc[frame+1]+.03*(rng.normal(size=len(n))+1j*rng.normal(size=len(n)))
    return y,epoch


@pytest.mark.parametrize('fs',[2500000,10000000])
def test_joint_subsets_recover_distinct_carriers_with_independent_code_fit(fs):
    y,epoch=synthetic(fs);w=FastPilotWorkspace(y,fs,'upper',epoch)
    for subset,cfo in [('even',120023.4),('odd',120223.4)]:
        r=w.fast_joint_fit(120123.4,subset=subset)
        assert abs(r['CFO_hz']-cfo)<2
        assert abs(r['offset_samples']-.21)<.03
        assert abs(r['modulation_ppm']-13.4)<.5
        assert r['subset']==subset and r['margin']>.8
        assert abs(r['optimizer_score_difference'])<1e-12


def test_omitted_frames_cannot_change_subset_nomination_or_optimization():
    fs=2500000;y,epoch=synthetic(fs);w=FastPilotWorkspace(y,fs,'upper',epoch)
    a=w.fast_joint_fit(120123.4,subset='even')
    rng=np.random.default_rng(123)
    for k,ix in enumerate(w.frames):
        if k%2==1:y[ix]=1000*(rng.normal(size=len(ix))+1j*rng.normal(size=len(ix)))
    b=FastPilotWorkspace(y,fs,'upper',epoch).fast_joint_fit(120123.4,subset='even')
    for key in ('CFO_hz','offset_samples','modulation_ppm','score','control_score'):
        assert a[key]==pytest.approx(b[key],abs=1e-10)
    with pytest.raises(ValueError,match='subset'):w.fast_joint_fit(120123.4,subset='invalid')


def test_default_all_frames_retains_carrier_code_and_rate_recovery():
    y,epoch=synthetic(2500000,split=False);w=FastPilotWorkspace(y,2500000,'upper',epoch)
    default=w.fast_joint_fit(120100.);explicit=w.fast_joint_fit(120100.,subset='all')
    for key in ('CFO_hz','offset_samples','modulation_ppm','score'):
        assert default[key]==explicit[key]
    assert abs(default['CFO_hz']-120123.4)<2
    assert abs(default['offset_samples']-.21)<.03
    assert abs(default['modulation_ppm']-13.4)<.5


@pytest.mark.parametrize('subset',['odd','even'])
def test_subset_gradient_and_score_match_independent_reference(subset):
    y,epoch=synthetic(2500000);w=FastPilotWorkspace(y,2500000,'upper',epoch)
    x=np.array([120100.,.137,7.3]);actual=w.statistics(x,subset=subset);finite=[]
    assert actual['score']==pytest.approx(w.evaluate([x[0]],x[1],x[2],subset=subset)[0],abs=1e-12)
    for k in range(3):
        d=np.zeros(3);d[k]=w.parameter_scale[k]*1e-5
        finite.append((w.statistics(x+d,subset=subset,derivatives=False)['score']-w.statistics(x-d,subset=subset,derivatives=False)['score'])/2e-5)
    np.testing.assert_allclose(actual['gradient_score'],finite,rtol=3e-3,atol=2e-5)


def test_wider_epoch_range_recovers_shift_without_changing_default_bounds():
    y,epoch=synthetic(10000000,split=False,offset=-1.1);w=FastPilotWorkspace(y,10000000,'upper',epoch)
    narrow=w.fast_joint_fit(120100.);wide=w.fast_joint_fit(120100.,epoch_radius=3.)
    assert narrow['epoch_search_boundary']
    assert not wide['epoch_search_boundary'] and wide['score']>narrow['score']
    assert abs(wide['offset_samples']+1.1)<.03 and abs(wide['CFO_hz']-120123.4)<2


def test_reused_panel_checks_measurement_authority_not_just_identity():
    from refine_pulse_iq_panel import validate_panel
    p=dict(observation_id='p1',CFO_hz=100.,sample_start=200,iq_sha256='abc')
    plan=dict(points=[p],sample_rate_hz=10000000)
    meta=dict(points=[dict(p,array='point.npy')],sample_rate_hz=10000000)
    validate_panel(plan,meta)
    meta['points'][0]['CFO_hz']=101.
    with pytest.raises(ValueError,match='authority'):validate_panel(plan,meta)
    meta['points']=[p,p]
    with pytest.raises(ValueError,match='repeat'):validate_panel(plan,meta)
