import numpy as np
import pytest

from ds23_frame_registration import PERIOD, circular_line, epoch_pairs, wrap


def peak(epoch, cfo, margin=.5, rank=0):
    return dict(integer_epoch_sample=int(epoch), fractional_epoch_offset_samples=epoch-int(epoch),
                fractional_tracking_cfo_hz=cfo, fractional_margin=margin, candidate_rank=rank,
                passed_fractional_margin_gate=True)


def test_epoch_pairs_remove_alias_duplicates_but_keep_distinct_emissions():
    a = [peak(51.1,1000), peak(51.12,1000+PERIOD,.4), peak(500.4,20000)]
    b = [peak(51.15,10250), peak(900,11200)]
    pairs = epoch_pairs(a,b,2_500_000)
    assert len(pairs) == 1
    assert pairs[0]['differential_cfo_hz'] == pytest.approx(9250)
    assert pairs[0]['epoch_difference_samples'] == pytest.approx(.05)


def test_circular_line_rejects_false_pairs_and_unwraps_boundary():
    rng = np.random.default_rng(8124)
    times = np.linspace(0,300,120)
    values = wrap(113500+7*(times-150)+rng.normal(0,15,len(times)))
    values[::3] = rng.uniform(-PERIOD/2,PERIOD/2,len(times[::3]))
    result = circular_line(times,values)
    assert abs(result['offset_hz']-113500) < 6
    assert abs(result['rate_hz_s']-7) < .05
    assert result['inliers'].sum() >= 80
    assert not result['inliers'][::3].any()


def test_epoch_tolerance_and_native_alias_dedup_are_invariant_in_seconds():
    for fs in (2_500_000,10_000_000):
        first=[peak(.0001*fs,1000),peak((.0001+50e-9)*fs,1000+PERIOD,.4)]
        inside=[peak((.0001+70e-9)*fs,9000)]
        outside=[peak((.0001+100e-9)*fs,9000)]
        matches=epoch_pairs(first,inside,fs)
        assert len(matches)==1
        assert matches[0]['epoch_difference_s']==pytest.approx(70e-9)
        assert not epoch_pairs(first,outside,fs)
