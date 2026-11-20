import numpy as np
import pytest

from tools.pipeline_eval.qualification.clock_geometry_results import chart_control
from tools.pipeline_eval.variants import clock_geometry as observable
from tools.pipeline_eval.variants import clock_geometry_pooled as fallback


def test_physical_frame_sign_survives_epoch_alias_and_affine_transmitter_term():
    t = np.linspace(0, 22, 90)
    rf, fs = 11.6e9, 10.0e6
    delay = -0.003 * t**3 + 0.07 * t**2
    cfo = (0.009 * t**2 - 0.14 * t) * rf / fs + 58_000
    phase = observable.pairs.fold(6665.0 + 1.2 * t + delay, fs / 750)
    a = observable.closure(t, phase, cfo, rf, fs)
    assert a["qualified"] and a["physical"] < 0.01
    assert a["clock_only"] > 3
    assert not observable.closure(t, np.roll(phase, 4), cfo, rf, fs)["qualified"]
    assert not observable.closure(t, phase, -cfo, rf, fs)["qualified"]


def test_pooled_band_eliminates_distinct_channel_offsets_and_checks_unseen_visits():
    t = np.arange(0.0, 300.0, 1.0)
    t = t[(t // 30) % 3 != 1]
    rate, mid = 2.5, 150
    histories = {
        lane: np.column_stack(
            (t, observable.pairs.fold(offset + rate * (t - mid) + 6.0 * np.cos(t / 3.0)))
        )
        for lane, offset in ((1, 113_500.0), (3, -45_000.0), (4, 77_444.0))
    }
    a = fallback.band_fit(histories, mid)
    assert a["eligible"]
    assert a["relative_hz_s"] == pytest.approx(rate, abs=0.1)
    assert a["sigma_hz_s"] == pytest.approx(1.5)
    for obs in histories.values():
        obs[obs[:, 0] % 30 >= 18, 1] += 1200
    assert not fallback.band_fit(histories, mid)["eligible"]


def test_relative_normal_anchors_only_inter_receiver_slope_difference():
    H, g = np.zeros((6, 6)), np.zeros(6)
    x = np.array([1.0, 2.0, 10.0, -1.0, 15.0, 4.0])
    r = {0: {"relative_hz_s": 2.0, "sigma_hz_s": 1.5}}
    loss = fallback.relative_normal(H, g, x, r, 4)
    assert loss == pytest.approx(1)
    np.testing.assert_array_equal(H @ np.array([0, 0, 1, 0, 1, 0]), np.zeros(6))
    np.testing.assert_array_equal(H[:2], np.zeros((2, 6)))
    assert g[2] > 0 and g[4] < 0


def test_chart_preserves_control_c0_and_has_no_replicated_fitted_endpoint():
    fit = dict(latlon=None, forced_latlon=[50.0, 1.0])
    old = dict(result=dict(status="withheld", arms=dict(c0=fit, fitted_c=fit), metrics={}))
    both = chart_control(old)["result"]
    assert both["arms"]["c0"] == fit == old["result"]["arms"]["fitted_c"]
    assert both["arms"]["fitted_c"] == dict(
        status="unavailable",
        reason="constant_rf_projects_out_with_free_arc_intercepts",
        latlon=None,
        forced_latlon=None,
    )
