import numpy as np
import pytest
from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import pilot_wave
from probe_native_code_carrier import interpolate_periodic


def data(edge='lower', cfo=120123.4, offset=.31, ppm=17.3, noise=.1, fs=2500000):
    n=np.arange(fs//50)
    epoch=125.3
    physical=(n-epoch-offset)*(1+ppm*1e-6)
    rng=np.random.default_rng(120)
    frame=np.floor((n-epoch)/(fs/750)).astype(int)+1
    gains=(.8+rng.uniform(0,.4,32))*np.exp(1j*rng.uniform(-np.pi,np.pi,32))
    dc=.1*(rng.normal(size=32)+1j*rng.normal(size=32))
    samples=interpolate_periodic(pilot_wave(fs,edge),physical*32)*gains[frame]*np.exp(2j*np.pi*cfo*n/fs)
    samples+=dc[frame]+noise*(rng.normal(size=len(n))+1j*rng.normal(size=len(n)))
    return samples,fs,epoch


def test_projected_likelihood_matches_reference_and_gradient_matches_finite_differences():
    y,fs,epoch=data()
    p=FastPilotWorkspace(y,fs,'lower',epoch)
    x=np.array([120100.,.137,7.3])
    actual=p.statistics(x)
    np.testing.assert_allclose(actual['score'],p.evaluate([x[0]],x[1],x[2])[0],rtol=1e-12,atol=1e-12)
    finite=[]
    for k in range(3):
        d=np.zeros(3);d[k]=p.parameter_scale[k]*1e-5
        finite.append((p.statistics(x+d,derivatives=False)['score']-p.statistics(x-d,derivatives=False)['score'])/2e-5)
    np.testing.assert_allclose(actual['gradient_score'],finite,rtol=3e-3,atol=2e-5)


def test_small_normal_system_matches_explicit_complex_QR_projection():
    y,fs,epoch=data()
    p=FastPilotWorkspace(y,fs,'lower',epoch)
    x=np.array([120100.,.137,7.3])
    def model(v):
        return p.replica(v[1],v[2])*np.exp(2j*np.pi*v[0]*(p.t-p.mid))
    signal=model(x);derivatives=[]
    for k in range(3):
        step=np.zeros(3);step[k]=p.parameter_scale[k]*1e-6
        derivatives.append((model(x+step)-model(x-step))/2e-6)
    derivative=np.column_stack(derivatives);normal=np.zeros((3,3))
    for ix in p.frames:
        design=np.column_stack((signal[ix],np.ones(len(ix))))
        coefficient=np.linalg.lstsq(design,p.y[ix],rcond=None)[0]
        q,_=np.linalg.qr(design)
        j=coefficient[0]*derivative[ix]
        j-=q@(q.conj().T@j)
        normal+=(j.conj().T@j).real
    np.testing.assert_allclose(p.statistics(x)['normal'],normal,rtol=2e-3,atol=2e-3)


@pytest.mark.parametrize('edge,offset,ppm',[('lower',.31,17.3),('upper',-.42,-23.4)])
def test_continuous_fit_recovers_independent_carrier_epoch_and_rate_with_frame_gains_and_DC(edge,offset,ppm):
    y,fs,epoch=data(edge=edge,offset=offset,ppm=ppm,noise=.05)
    p=FastPilotWorkspace(y,fs,edge,epoch)
    result=p.fast_joint_fit(120100.)
    assert abs(result['CFO_hz']-120123.4)<2
    assert abs(result['offset_samples']-offset)<.03
    assert abs(result['modulation_ppm']-ppm)<.5
    assert result['score']>.98 and result['margin']>.8
    assert abs(result['optimizer_score_difference'])<1e-12
    assert not any(result[k] for k in ['frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary'])
    assert all(b['score']>=a['score'] for a,b in zip(result['selected_history'],result['selected_history'][1:]))


@pytest.mark.parametrize('edge,cfo,offset,ppm',[
    ('lower',-350123.4,.61,31.3),('upper',650123.4,-.62,-33.4)])
def test_ten_megahertz_fit_recovers_high_carrier_and_near_edge_epoch_rate(edge,cfo,offset,ppm):
    y,fs,epoch=data(edge=edge,cfo=cfo,offset=offset,ppm=ppm,noise=.05,fs=10000000)
    p=FastPilotWorkspace(y,fs,edge,epoch)
    result=p.fast_joint_fit(cfo+85.)
    assert abs(result['CFO_hz']-cfo)<2
    assert abs(result['offset_samples']-offset)<.03
    assert abs(result['modulation_ppm']-ppm)<.5
    assert result['score']>.98 and result['margin']>.8
    assert not any(result[k] for k in ['frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary'])
