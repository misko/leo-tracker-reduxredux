import numpy as np
from ds23_cross_receiver_carrier import cross_carrier,circular_delta


def test_common_unknown_content_recovers_relative_carrier_without_template_or_position():
    rng=np.random.default_rng(8);fs=20000.;n=4000;t=np.arange(n)/fs
    content=rng.normal(size=n)+1j*rng.normal(size=n)
    first=content+.05*(rng.normal(size=n)+1j*rng.normal(size=n))
    second=2*content*np.exp(2j*np.pi*321.4*t+.3j)+.05*(rng.normal(size=n)+1j*rng.normal(size=n))
    result=cross_carrier(first,second,fs)
    assert abs(result['differential_CFO_hz']-321.4)<.05
    assert result['coherent_fraction']>.98
    assert result['lag_samples']==0


def test_independent_content_does_not_form_a_strong_shared_carrier():
    rng=np.random.default_rng(22);n=4000
    first=rng.normal(size=n)+1j*rng.normal(size=n)
    second=rng.normal(size=n)+1j*rng.normal(size=n)
    assert cross_carrier(first,second,20000.)['coherent_fraction']<.02
    assert circular_delta(1001.,1.,1000.)==0.
