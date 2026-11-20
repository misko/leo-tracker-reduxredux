import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.reference.grid import Tile
from tools.pipeline_eval.variants import robust_em as lean
from tools.pipeline_eval.variants import robust_orbit_fit as upgraded
from tools.pipeline_eval.variants.projected_fit import Region


def _tile():
    center = (17.0, -117.0)
    origin = geodetic_to_ecef_km(*center, 0.0)
    frame = ecef_to_enu_matrix(*center)
    region = Region("plant", center, origin, frame)
    knots = -8.0 + 5 * np.arange(65)
    t = (knots - 145.0)[None, :]
    angle = np.linspace(-2.0, 2.0, 8)[:, None]
    speed = 7.0
    height = 560 + 0.0015 * t**2 + 25 * np.sin(angle)
    east = np.cos(angle) * speed * t + 150 * np.sin(2 * angle)
    north = np.sin(angle) * speed * t + 190 * np.cos(2 * angle)
    h = np.stack((east, north, height), axis=-1)
    east_rate = np.broadcast_to(speed * np.cos(angle), east.shape)
    north_rate = np.broadcast_to(speed * np.sin(angle), north.shape)
    height_rate = np.broadcast_to(0.003 * t, height.shape)
    v = np.stack((east_rate, north_rate, height_rate), axis=-1)
    return Tile(origin, frame, 300.0, knots, origin + h @ frame, v @ frame, {}), region


def test_range_rate_jacobian_matches_central_differences_at_shifted_site():
    tile, region = _tile()
    times = np.array([77.11, 99.2, 116.1, 146.21, 201.44])
    site = region.site(np.array([4.0, -2.0]))[0]
    phase, rf = 2.44, 11.7e9
    _, site_jac, phase_jac = upgraded.project(tile, 2, times, site, phase, rf)
    for i, step in enumerate(np.eye(3) * 1e-3):
        plus = upgraded.project(tile, 2, times, site + step, phase, rf)[0]
        minus = upgraded.project(tile, 2, times, site - step, phase, rf)[0]
        np.testing.assert_allclose(site_jac[:, i], (plus - minus) / 0.002, atol=1e-5)
    plus = upgraded.project(tile, 2, times, site, phase + 1e-4, rf)[0]
    minus = upgraded.project(tile, 2, times, site, phase - 1e-4, rf)[0]
    np.testing.assert_allclose(phase_jac, (plus - minus) / 0.0002, atol=0.001)


def test_relinearization_reduces_exact_loss_for_the_same_planted_assignments():
    tile, region = _tile()
    truth = np.array([4.25, -3.0])
    site = region.site(truth)[0]
    rows = []
    for orbit, angle in enumerate(np.linspace(-1, 1, 8)):
        for lane in range(2):
            times = np.linspace(60 + 3 * orbit + 10 * lane, 234 + 4 * orbit, 71)
            hz, _, _ = upgraded.project(tile, orbit, times, site, 3 * angle, 11.2e9)
            track = lean.Track(
                times, hz, 11.2e9, lane, True, (times - 150) / 100, np.eye(len(times)) / 150
            )
            arc = lean.shortlist(tile, track)
            winner = int(np.flatnonzero(arc.orbit == orbit)[0])
            rows.append(lean.Assignment(arc, winner, 0, 0.25, 8.0))
    start = lean.fit(rows, len(tile.positions_km), 12.5, "c0")
    fitted, receipt = upgraded.refine(rows, start, tile, region, 12.5, "c0")
    assert 0 < receipt["accepted_steps"] <= upgraded.RELINEARIZATIONS
    assert fitted.score < receipt["exact_score_at_linear_fit"]
    assert np.linalg.norm(fitted.state.xy - truth) < np.linalg.norm(start.state.xy - truth)
    np.testing.assert_allclose(fitted.state.xy, truth, atol=0.1)


def test_null_track_inventory_is_withheld():
    result = upgraded.infer({"duration_s": 300, "tracks": []}, {"center": [0, 0], "id": "null"}, "")
    assert result["reason"] == "insufficient_track_inventory"
    assert all(value["latlon"] is None for value in result["arms"].values())
