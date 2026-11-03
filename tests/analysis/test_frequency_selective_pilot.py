from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from frequency_selective_pilot import ChannelPilotWorkspace
from local_pilot_refinement import PilotWorkspace


def workspace():
    return ChannelPilotWorkspace(np.zeros(20000,complex),2500000.,'lower',23.2)


def test_tone_sum_matches_original_flat_template():
    p=workspace()
    # The canonical sum is rounded to complex64 before Fourier interpolation;
    # separate tone columns retain complex128 until the final sum.
    tolerance=2*np.finfo(np.float32).eps
    np.testing.assert_allclose(p.columns(.125,7.).sum(axis=1),p.replica(.125,7.),atol=tolerance,rtol=tolerance)


def test_flat_channel_profile_matches_existing_scorer():
    y=np.random.default_rng(71).normal(size=20000)+1j*np.random.default_rng(72).normal(size=20000)
    p=ChannelPilotWorkspace(y,2500000.,'lower',23.2)
    old=PilotWorkspace(y,2500000.,'lower',23.2)
    frequencies=np.array([10000.,10030.,10060.])
    np.testing.assert_allclose(p.evaluate(frequencies,.125,7.,flat=True),old.evaluate(frequencies,.125,7.),atol=1e-10,rtol=1e-6)


def test_variable_projection_recovers_frequency_with_nonflat_complex_channels():
    p=workspace();columns=p.columns();rng=np.random.default_rng(143)
    frequency=12345.25
    y=np.zeros(len(p.y),complex)
    for k,ix in enumerate(p.frames):
        gains=rng.normal(size=8)+1j*rng.normal(size=8)
        y[ix]=(columns[ix]@gains)*np.exp(2j*np.pi*frequency*(p.t[ix]-p.mid))+(k+1j)
    q=ChannelPilotWorkspace(y,p.fs,'lower',p.epoch)
    fitted=q.frequency_fit(frequency-17)
    assert abs(fitted['CFO_hz']-frequency)<.1
    assert fitted['score']>1-1e-8
    assert q.evaluate([frequency],control=True)[0]<.5
    for subset in ('symbol_even','symbol_odd'):
        fit=q.frequency_fit(frequency-17,subset=subset)
        assert abs(fit['CFO_hz']-frequency)<.15
        assert q.prediction_error(fit,subset)['heldout_normalized_error']<1e-7


def test_symbol_folds_are_disjoint_and_cover_the_same_frame():
    p=workspace()
    for k,full in enumerate(p.frames):
        first=p.indices(k,0.,0.,'symbol_even');second=p.indices(k,0.,0.,'symbol_odd')
        assert not set(first)&set(second)
        np.testing.assert_array_equal(np.sort(np.r_[first,second]),full)
    assert len(p._channel_cache)<=2
