import numpy as np
import pytest

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets
from tests.pipeline_eval import geometry
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.variants import shared_doppler as receiver


def test_short_tracks_duplicates_order_and_sparse_input():
    def track(i):
        t = np.arange(i, i + 15.0)
        return dict(receiver=i % 2, channel=i % 8 + 1, rf_hz=11e9, times=t, values=t**2)

    tracks = [track(i) for i in range(6)]
    broken = dict(tracks[0], times=[1, 2], values=[1, 2])
    a = receiver.observations(dict(duration_s=60, tracks=tracks))
    observation = dict(duration_s=60, tracks=[broken, *reversed(tracks), tracks[1]])
    b = receiver.observations(observation)
    for field in receiver.Tracks.__dataclass_fields__:
        np.testing.assert_array_equal(getattr(a, field), getattr(b, field))
    out = receiver.infer(observation, [{"id": "a"}], "")
    assert out["status"] == "withheld" and all(v["latlon"] is None for v in out["arms"].values())


def test_common_assignments_recover_planted_receiver_and_rf_calibration():
    rng = np.random.default_rng(24933)
    n, s = 50, receiver.SAMPLES
    times = np.linspace(0, 220, n)[:, None] + np.arange(s)
    rf = 11.5e9 + 1e9 * rng.uniform(-0.7, 0.7, n)
    clock = times / 120 - 1
    lane = np.arange(n) % 2
    xy = [2.3, -3.1]
    jac = rng.normal(0, 170, (n, 1, s, 2))
    rate = rng.normal(0, 50, (n, 1, s))
    ambiguity = rng.integers(-3, 4, size=n)
    ids = (np.arange(n) % 6)[:, None]
    signal = jac[:, 0] @ xy + (rf[:, None] / 1e9 - 11.5) * 2500
    signal += (
        np.array([900, -600])[lane, None] + 200 * clock + ambiguity[:, None] * receiver.PERIOD_HZ
    )
    data = receiver.Tracks(times, signal, rf, lane, clock)
    model = receiver.Model(None, 10, data, ids, signal[:, None], jac, rate, 6)
    rows = np.arange(n)
    selection = (rows, np.zeros(n, dtype=int), ambiguity, np.zeros(n))
    zero, rms0, *_ = receiver.fit(model, *selection, "c0")
    fitted, rms, sats, used = receiver.fit(model, *selection, "fitted_c")
    assert sats == 6 and used == n
    assert zero.rf_slope == 0 and fitted.rf_slope == pytest.approx(2500, abs=5)
    np.testing.assert_allclose(fitted.xy, xy, atol=0.01)
    assert rms < rms0 * 0.03
    _, aliases, loss = receiver.assignments(model, fitted, rows)
    np.testing.assert_array_equal(aliases, ambiguity)
    assert loss.max() < 0.1
    assert receiver.fit(model, rows, selection[1], ambiguity, np.full(n, np.inf), "c0") is None


def test_box_solution_accounts_for_correlation_and_profiles_nuisance():
    h = np.array([[5.0, 2.0, 0.3], [2.0, 3.0, 0.1], [0.3, 0.1, 4.0]])
    rhs = h @ np.array([3.0, -1.0, 7.0])
    point, radius = receiver.bounded(h, rhs, 2.0)
    assert point[0] == 2 and -2 < point[1] < 2 and radius > 0
    np.testing.assert_allclose((h @ point - rhs)[1:], 0, atol=1e-10)


def test_independent_orbit_simulation_with_anonymous_regions():
    site = (-33.0, -71.0)
    rng = np.random.default_rng(7841)
    text = "".join(
        geometry.tle(i, 4.4, rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(50, 95))
        for i in range(5000, 6100)
    )
    catalog = parse_element_sets(text)
    tracks = []
    for start in (5.2, 91.3, 174.1):
        times = start + np.linspace(0, 60, 24)
        pos, vel = geometry.direct_states(catalog, times)
        delta = pos - geodetic_to_ecef_km(*site, 0.0)
        ray = delta / np.linalg.norm(delta, axis=-1, keepdims=True)
        visible = np.flatnonzero(np.min(ray @ ecef_to_enu_matrix(*site)[2], axis=1) > 0.4)
        for i in visible[:10]:
            rf = rng.uniform(10.8e9, 12e9)
            y = -rf * np.sum(vel[i] * ray[i], axis=-1) / 299792.458
            tracks.append(
                dict(
                    receiver=0,
                    channel=3,
                    rf_hz=rf,
                    times=times,
                    values=y + 1500 + 1300 * (rf / 1e9 - 11.5) + (i % 3) * receiver.PERIOD_HZ,
                )
            )
    assert len(tracks) > 10
    obs = dict(
        anchor_utc_ns=geometry.ANCHOR,
        cutoff_utc_ns=geometry.ANCHOR - 10**9,
        catalog_timestamp_ns=geometry.ANCHOR - geometry.DAY_NS // 4,
        duration_s=240,
        tracks=tracks,
    )
    near = {"id": "q", "center": [-33.009, -70.986]}
    far = {"id": "r", "center": [53.4, -2.4]}
    result = receiver.infer(obs, [far, near], text)
    assert result["reason"] == "weak_position_geometry" and result["metrics"]["radius_km"] > 5
    for arm in result["arms"].values():
        assert arm["latlon"] is None and arm["forced_region_id"] == "q"
        assert distance_km(arm["forced_latlon"], site) <= result["metrics"]["radius_km"]
    assert result["arms"]["fitted_c"]["c_hz_per_ghz"] == pytest.approx(1300, rel=0.05)
    reverse = receiver.infer(dict(obs, tracks=list(reversed(tracks))), [near, far], text)
    assert result["arms"] == reverse["arms"]
    tied = receiver.infer(obs, [near, dict(near, id="r")], text)
    assert tied["reason"] == "ambiguous_region" and tied["metrics"]["region_lead"] == 0
    assert all(not a["latlon"] and a["forced_latlon"] for a in tied["arms"].values())
