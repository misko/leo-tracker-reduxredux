import pytest
from audit_bundle_native_measurements import pilot_time_support


def test_pilot_support_centroid_is_inside_physical_probe_and_tracks_epoch():
    a=pilot_time_support(100.,10_000_000,200000);b=pilot_time_support(101.,10_000_000,200000)
    assert 0<=a['support_start_s']<a['uniform_centroid_s']<a['support_end_s']<.02
    assert a['frames']==b['frames'] and b['uniform_centroid_s']-a['uniform_centroid_s']==pytest.approx(1e-7)
    assert a['probe_midpoint_s']==.01 and a['unknown_IQ_weights']
    with pytest.raises(ValueError,match='no complete'):pilot_time_support(199999.,10_000_000,200000)
    with pytest.raises(ValueError,match='geometry'):pilot_time_support(1.,0.,200000)
