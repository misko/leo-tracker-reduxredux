import numpy as np

from ds23_shared_waveform import remove_pilot,coherence,derangements,frame_positions,carrier_spectrum


def test_pilot_only_similarity_does_not_create_a_shared_random_waveform():
    rng=np.random.default_rng(37)
    pilot=rng.normal(size=512)+1j*rng.normal(size=512)
    payload=lambda:rng.normal(size=(14,512))+1j*rng.normal(size=(14,512))
    a=8*pilot[None,:]+payload()
    b=8*pilot[None,:]+payload()
    raw,_=coherence(a,b,derangements(14))
    first,_=remove_pilot(a,pilot)
    second,_=remove_pilot(b,pilot)
    residual,null=coherence(first,second,derangements(14))
    assert raw>.95 and residual<.005
    assert max(null)<.01


def test_shared_payload_survives_different_frame_gains_and_pilot_projection():
    rng=np.random.default_rng(41)
    pilot=rng.normal(size=512)+1j*rng.normal(size=512)
    payload=rng.normal(size=(14,512))+1j*rng.normal(size=(14,512))
    frames=5*pilot[None,:]+payload
    a=frames+.1*(rng.normal(size=frames.shape)+1j*rng.normal(size=frames.shape))
    gain=(.5+rng.random(14))*np.exp(1j*rng.uniform(-np.pi,np.pi,14))
    b=gain[:,None]*frames+.1*(rng.normal(size=frames.shape)+1j*rng.normal(size=frames.shape))
    first,_=remove_pilot(a,pilot)
    second,_=remove_pilot(b,pilot)
    actual,null=coherence(first,second,derangements(14))
    assert actual>.9 and actual>max(null)*20


def test_frame_sampling_preserves_fractional_epoch_without_extrapolation():
    x=frame_positions(50000,2500000.,123.375,delay_samples=.25)
    assert len(x)==14
    np.testing.assert_allclose(x[:,0]-(123.375+16+.25),np.arange(14)*2500000/750)
    assert x.min()>=0 and x.max()<50000


def test_common_pilot_clock_distortion_is_not_a_payload_fingerprint():
    rng=np.random.default_rng(51)
    pilot=rng.normal(size=512)+1j*rng.normal(size=512)
    distortion=rng.normal(size=512)+1j*rng.normal(size=512)
    k=np.arange(14)
    common=(k[:,None]/3+np.cos(2*np.pi*k[:,None]/3))*distortion[None,:]
    a=10*pilot[None,:]+common+rng.normal(size=(14,512))+1j*rng.normal(size=(14,512))
    b=10*pilot[None,:]+common+rng.normal(size=(14,512))+1j*rng.normal(size=(14,512))
    first,_=remove_pilot(a,pilot);second,_=remove_pilot(b,pilot)
    actual,_=coherence(first,second,derangements(14))
    assert actual<.01


def test_shared_waveform_carrier_recovers_an_injected_physical_frequency_difference():
    rng=np.random.default_rng(83)
    t=np.arange(14)[:,None]/750+np.arange(256)[None,:]/2500000
    a=rng.normal(size=t.shape)+1j*rng.normal(size=t.shape)
    b=a*np.exp(2j*np.pi*145*t)+.05*(rng.normal(size=t.shape)+1j*rng.normal(size=t.shape))
    result=carrier_spectrum(a,b,t)
    assert result['additional_frequency_hz']==145.
    assert result['leave_frame_out_range_hz']==0.
    assert result['coherence']>.99


def test_independent_waveforms_do_not_produce_a_strong_carrier_peak():
    rng=np.random.default_rng(89)
    t=np.arange(14)[:,None]/750+np.arange(256)[None,:]/2500000
    a=rng.normal(size=t.shape)+1j*rng.normal(size=t.shape)
    b=rng.normal(size=t.shape)+1j*rng.normal(size=t.shape)
    assert carrier_spectrum(a,b,t)['coherence']<.01
