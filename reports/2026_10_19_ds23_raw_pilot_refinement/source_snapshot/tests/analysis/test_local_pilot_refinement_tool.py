import numpy as np
from local_pilot_refinement import PilotWorkspace,pilot_wave
from probe_native_code_carrier import interpolate_periodic


def synthetic(cfo=120123.4,ppm=0.,noise=0.):
    fs=2500000;n=np.arange(fs//50);epoch=125.3;rng=np.random.default_rng(91)
    wave=pilot_wave(fs,'lower');position=(n-epoch)*(1+ppm*1e-6)
    frame=np.floor(position/(fs/750)).astype(int);phase=np.exp(1j*rng.uniform(-np.pi,np.pi,32))
    samples=interpolate_periodic(wave,position*32)*phase[frame+1]*np.exp(2j*np.pi*cfo*n/fs)
    samples+=noise*(rng.normal(size=len(n))+1j*rng.normal(size=len(n)))
    return samples,fs,epoch


def test_direct_frequency_fit_handles_independent_frame_phases_and_recovers_off_grid_CFO():
    samples,fs,epoch=synthetic(noise=.2);p=PilotWorkspace(samples,fs,'lower',epoch)
    result=p.frequency_fit(120100.)
    assert abs(result['CFO_hz']-120123.4)<2
    assert not result['frequency_search_boundary']
    assert result['score']>.8


def test_joint_fit_recovers_distinct_modulation_rate_without_changing_carrier_truth():
    samples,fs,epoch=synthetic(ppm=20);p=PilotWorkspace(samples,fs,'lower',epoch)
    result=p.joint_fit(120100.)
    assert abs(result['CFO_hz']-120123.4)<2
    assert abs(result['modulation_ppm']-20)<=2.5
    assert result['score']>.999
    assert result['margin']>.8


def test_disjoint_frame_subsets_have_independent_phase_fits_at_same_frequency():
    samples,fs,epoch=synthetic(noise=.4);p=PilotWorkspace(samples,fs,'lower',epoch)
    a=p.frequency_fit(120100.,subset='odd');b=p.frequency_fit(120100.,subset='even')
    assert abs(a['CFO_hz']-120123.4)<3 and abs(b['CFO_hz']-120123.4)<3
    assert 0<p.effective_time(a)<.02
    assert .0008<p.effective_time(a)-p.effective_time(b)<.0019
