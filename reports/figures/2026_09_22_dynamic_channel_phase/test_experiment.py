import numpy as np
import pytest
from experiment import normalize_response
from types import SimpleNamespace
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking

def test_known_rotating_phase_recovers_smooth_channel():
    rng=np.random.default_rng(345);n=4096;b=180
    left=(rng.normal(size=(b,n))+1j*rng.normal(size=(b,n)))/np.sqrt(2)
    noise=(rng.normal(size=(b,n))+1j*rng.normal(size=(b,n)))/np.sqrt(2)
    f=np.linspace(-1,1,n);h=.7*np.exp(1j*(.4+.2*f))
    phi=2*np.sin(np.arange(b)*.08)+.03*np.arange(b)
    right=(left*h+noise)*np.exp(1j*phi[:,None])
    eligible=np.zeros(n,bool);eligible[64:-64]=True;idx=np.flatnonzero(eligible)
    indexes,fitted,history=normalize_response(left,right,f,idx,h[idx],eligible)
    error=np.angle(fitted*np.conj(h[indexes]))
    # A constant global phase gauge is irrelevant to relative time evolution.
    error=np.angle(np.exp(1j*(error-np.angle(np.mean(np.exp(1j*error))))))
    assert np.sqrt(np.mean(error**2))<.04
    assert np.median(abs(abs(fitted)-abs(h[indexes])))<.025
    assert len(indexes)>3500

def test_independent_noise_does_not_create_common_channel():
    rng=np.random.default_rng(346);n=4096;b=180
    left=rng.normal(size=(b,n))+1j*rng.normal(size=(b,n))
    right=rng.normal(size=(b,n))+1j*rng.normal(size=(b,n))
    eligible=np.zeros(n,bool);eligible[64:-64]=True;idx=np.flatnonzero(eligible)
    with pytest.raises(ValueError,match='No qualified'):
        normalize_response(left,right,np.arange(n),idx,np.ones(len(idx)),eligible)

@pytest.mark.parametrize('noise_scale,minimum_coherence,maximum_phase_rms_deg',[(.8,.6,5),(3.4,.15,10)])
def test_known_time_varying_phase_predicts_held_frequency_bands(noise_scale,minimum_coherence,maximum_phase_rms_deg):
    rng=np.random.default_rng(347);fs=2500000;n=4096;blocks=180;count=n*blocks
    time=np.arange(count)/fs
    left=(rng.normal(size=count)+1j*rng.normal(size=count))/np.sqrt(2)
    noise=(rng.normal(size=count)+1j*rng.normal(size=count))/np.sqrt(2)
    phase=2*np.pi*(25*time+60*time*time)+.25*np.sin(2*np.pi*7*time)
    right=.7*left*np.exp(1j*(.4+phase))+noise_scale*noise
    iq=np.column_stack((left,right));freq=np.fft.fftshift(np.fft.fftfreq(n,1/fs));win=np.hanning(n)
    a=np.fft.fftshift(np.fft.fft(left[:count//2].reshape(-1,n)*win,axis=1),axes=1)
    b=np.fft.fftshift(np.fft.fft(right[:count//2].reshape(-1,n)*win,axis=1),axes=1)
    eligible=np.zeros(n,bool);eligible[64:-64]=True;idx=np.flatnonzero(eligible)
    indexes,h,_=normalize_response(a,b,freq,idx,np.full(len(idx),.7*np.exp(.4j)),eligible)
    model=SimpleNamespace(frequency_hz=freq[indexes],channel_transfer=h,reference_sample=0,relative_cfo_hz=0,relative_cfo_rate_hz_s=0)
    result=frequency_held_out_tracking(iq,fs,model)
    centers=np.array([r['center_sample'] for r in result['rows']]);truth=np.interp(centers,np.arange(count),phase)
    estimated=np.array([r['training_band_phase_rad'] for r in result['rows']]);error=np.angle(np.exp(1j*(estimated-truth)))
    assert np.degrees(np.sqrt(np.mean(error**2)))<maximum_phase_rms_deg
    assert abs(result['tracked']['phase_rad'])<.08
    assert result['tracked']['coherence']>minimum_coherence
    assert result['wrong_time']['coherence']<.03
