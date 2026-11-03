import numpy as np

from full_scan_residual_audit import nested_track_fit, REFERENCE_RF_HZ


def test_lane_offsets_do_not_create_a_false_satellite_slope():
    t = np.arange(40.)
    rx = (t >= 20).astype(int); channel = np.ones(40, int)
    residual = 200.*rx
    r = nested_track_fit(t, np.full(40, REFERENCE_RF_HZ), rx, channel, residual, np.ones(40))
    assert abs(r['shared_linear_hz_s']) < 1e-10
    assert r['rx_time_range_overlap_s'] == 0.


def test_shared_rf_scaled_slope_survives_lane_controls():
    t = np.tile(np.arange(30.), 2)
    rx = np.repeat([0, 1], 30); channel = 1+np.arange(60)%2
    rf = REFERENCE_RF_HZ*(1.+.02*channel)
    residual = 3.*(t-14.5)*rf/REFERENCE_RF_HZ+25*rx-10*channel
    r = nested_track_fit(t, rf, rx, channel, residual, np.ones(60))
    np.testing.assert_allclose(r['shared_linear_hz_s'], 3., atol=1e-10)
    assert r['plus_shared_linear_rms_hz'] < 1e-10
    assert r['rx_time_range_overlap_s'] == 29.


def test_insufficient_span_is_not_reported_as_no_curvature():
    x = np.arange(10.)
    assert nested_track_fit(x, x+1, np.zeros(10), np.ones(10), x, np.ones(10)) is None
