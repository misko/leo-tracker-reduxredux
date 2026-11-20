"""Check the fixed-point receiver scores against the frozen solver."""

import json

import numpy as np

from tools.pipeline_eval.variants import shape_score

grid = shape_score.grid
receiver = shape_score.receiver


def test_all_changed_time_scores_match_with_horizon_filtering():
    rng = np.random.default_rng(72)
    duration = 180.0
    knots = grid._knots(duration, grid.FINE_ORBIT_STEP_S)
    site = grid.geodetic_to_ecef_km(0.0, 0.0, 0.0)
    up = grid.ecef_to_enu_matrix(0.0, 0.0)
    origin = site + np.column_stack(
        (np.linspace(-900.0, 850.0, 64), rng.uniform(-300, 300, (64, 2)))
    )
    velocity = rng.uniform([-0.6, -6.5, -6.5], [0.6, 6.5, 6.5], (64, 3))
    acceleration = rng.uniform(-0.008, 0.008, (64, 3))
    t = (knots - duration / 2)[None, :, None]
    position = origin[:, None] + t * velocity[:, None] + 0.5 * t**2 * acceleration[:, None]
    velocities = velocity[:, None] + t * acceleration[:, None]
    tile = shape_score._PreparedTile(site, up, duration, knots, position, velocities, {})

    tracks = []
    for i, count in enumerate((6, 12, 20, 44, 16)):
        satellite = 50 + i
        times = np.linspace(100 + i, 146 + i, count)
        elapsed = (times - duration / 2)[:, None]
        delta = (
            origin[satellite]
            - site
            + elapsed * velocity[satellite]
            + 0.5 * elapsed**2 * acceleration[satellite]
        )
        speed = velocity[satellite] + elapsed * acceleration[satellite]
        radial_velocity = np.sum(delta * speed, axis=1) / np.linalg.norm(delta, axis=1)
        rf_hz = 10.8e9 + i * 0.3e9
        values = -radial_velocity * rf_hz / grid.LIGHT_SPEED_KM_S
        tracks.append(dict(times=tuple(times), values=tuple(values), rf_hz=rf_hz))

    point = (0.1, -0.5)
    schedules = [tracks] + [
        receiver._shifted(tracks, duration / 2, duration, step)
        for step in range(1, receiver.NULL_COUNT + 1)
    ]
    reference = [grid.score_at(tile, changed, point) for changed in schedules]
    assert reference[0]["n_tracks"] == len(tracks)
    assert reference[0]["score"] > 0.99
    assert any(row["score"] < reference[0]["score"] for row in reference[1:])
    assert [shape_score._score_at(tile, changed, point) for changed in schedules] == reference


def test_all_satellites_below_the_horizon_contribute_zero():
    duration = 60.0
    knots = grid._knots(duration, grid.FINE_ORBIT_STEP_S)
    site = grid.geodetic_to_ecef_km(0.0, 0.0, 0.0)
    frame = grid.ecef_to_enu_matrix(0.0, 0.0)
    positions = np.broadcast_to(site - [500.0, 0.0, 0.0], (5, len(knots), 3))
    tile = shape_score._PreparedTile(
        site, frame, duration, knots, positions, np.zeros_like(positions), {}
    )
    track = dict(times=(31.0, 35.0, 40.0, 48.0), values=(1.0, 2.0, 3.0, 4.0), rf_hz=11e9)
    assert shape_score._score_at(tile, [track], (0, 0)) == {
        "score": 0.0,
        "n_tracks": 0,
        "rms_hz": None,
    }


def test_visible_interior_between_two_below_horizon_knots():
    duration = 60.0
    knots = grid._knots(duration, grid.FINE_ORBIT_STEP_S)
    site = grid.geodetic_to_ecef_km(0.0, 0.0, 0.0)
    frame = grid.ecef_to_enu_matrix(0.0, 0.0)
    positions = np.broadcast_to(site + [-20.0, 100.0, 0.0], (1, len(knots), 3))
    velocities = np.zeros_like(positions)
    knot = np.flatnonzero(knots == 32.0)[0]
    velocities[0, knot : knot + 2, 0] = [26.0, -26.0]
    tile = shape_score._PreparedTile(site, frame, duration, knots, positions, velocities, {})
    times = np.array([33.4, 33.8, 34.2, 34.6])
    u = (times - knots[knot]) / grid.FINE_ORBIT_STEP_S
    height = -20.0 + 130.0 * u * (1.0 - u)
    vertical_velocity = 26.0 * (1.0 - 2.0 * u)
    rf_hz = 11e9
    values = -height * vertical_velocity / np.hypot(height, 100.0) * rf_hz / grid.LIGHT_SPEED_KM_S
    track = dict(times=times, values=values, rf_hz=rf_hz)
    reference = grid.score_at(tile, [track], (0, 0))
    assert reference["score"] > 0.99
    assert reference["n_tracks"] == 1
    assert shape_score._score_at(tile, [track], (0, 0)) == reference


def test_missing_input_is_unavailable_and_sparse_tracks_are_withheld(tmp_path):
    case = {"id": "test", "regions": [{"id": "offer", "center": [1, 2]}]}
    unavailable = shape_score.run(case, tmp_path)
    assert unavailable["status"] == "unavailable"
    assert unavailable["reason"] == "missing_observation_or_catalog"

    observation = tmp_path / "observation.json"
    observation.write_text(json.dumps({"duration_s": 60.0, "tracks": []}))
    catalog = tmp_path / "catalog.tle"
    catalog.write_text("")
    result = shape_score.run(
        dict(case, observation_path=observation, catalog_path=catalog), tmp_path
    )
    assert result["status"] == "withheld"
    assert result["reason"] == "insufficient_tracks"
    assert (
        result["arms"]["c0"]
        == result["arms"]["fitted_c"]
        == {"latlon": None, "forced_latlon": None}
    )
    assert result["metrics"]["matched_decision"]
    assert result["metrics"]["matched_evidence"]
