import numpy as np
import pytest

from tools.pipeline_eval.variants import arc_validation as arc
from tools.pipeline_eval.variants import off_region_test

grid = arc.grid


@pytest.fixture
def orbit_tiles():
    duration = 180.0
    knots = grid._knots(duration, grid.FINE_ORBIT_STEP_S)
    origin = grid.geodetic_to_ecef_km(20, -45, 0.0)
    frame = grid.ecef_to_enu_matrix(20, -45)
    offsets = np.array([[50, -20, 510], [-55, 100, 470], [150, 15, 610], [185, 240, 450]])
    velocity = np.array([[6.1, 3, 0.2], [-5, 4, -0.1], [4, 6, 0.1], [-7, 2, -0.3]]) @ frame
    positions = origin + (offsets @ frame)[:, None] + knots[None, :, None] * velocity[:, None]
    velocities = np.broadcast_to(velocity[:, None], positions.shape)

    def tile(center):
        return grid.Tile(
            grid.geodetic_to_ecef_km(*center, 0.0),
            grid.ecef_to_enu_matrix(*center),
            duration,
            knots,
            positions,
            velocities,
            {},
        )

    tracks = []
    rf = 11.325e9
    for index in range(len(offsets)):
        times = np.linspace(12 + 5 * index, 57 + 5 * index, 12)
        delta = offsets[index] @ frame + times[:, None] * velocity[index]
        model = (
            -rf / grid.LIGHT_SPEED_KM_S * (delta @ velocity[index]) / np.linalg.norm(delta, axis=1)
        )
        tracks.append(
            dict(
                times=times.tolist(),
                values=(model + index * 95000).tolist(),
                rf_hz=rf,
                receiver=1,
                channel=3,
            )
        )
    return tile, dict(duration_s=duration, tracks=tracks)


def test_endpoint_frequency_cannot_change_training_nomination(orbit_tiles):
    tile, observation = orbit_tiles
    tracks = observation["tracks"]
    clean = arc._nomination(tile((20, -45)), tracks)
    damaged = [
        dict(track, values=track["values"][:8] + [10000 + f for f in track["values"][8:]])
        for track in tracks
    ]
    altered = arc._nomination(tile((20, -45)), damaged)
    assert clean["training_orbits"] == altered["training_orbits"] == 4
    assert clean["training_score"] == altered["training_score"]
    assert clean["latlon"] == altered["latlon"] == pytest.approx([20, -45])
    assert clean["held_score"] > 0.999
    assert clean["held_rms_hz"] < 1e-6
    assert altered["held_score"] == 0.0
    assert altered["held_orbits"] == 0


def test_training_offset_only_and_region_acceptance(monkeypatch, orbit_tiles):
    tile, observation = orbit_tiles
    monkeypatch.setattr(grid, "prepare_sky", lambda *args: None)
    monkeypatch.setattr(grid, "make_tile", lambda sky, center: tile(center))
    offers = [
        {"id": "correct", "center": [20.0, -45.0]},
        {"id": "north", "center": [20.75, -45.0]},
        {"id": "east", "center": [20.0, -44.25]},
        {"id": "other", "center": [20.75, -44.25]},
    ]
    result, reason, metrics = arc.solve(observation, offers, b"")
    assert reason == "accepted"
    assert metrics["region_accepted"]
    assert metrics["selected_region_id"] == "correct"
    assert result["latlon"] == pytest.approx([20, -45])
    shifted = dict(
        observation,
        tracks=[
            dict(track, values=[f + 4500.0 for f in track["values"]])
            for track in observation["tracks"]
        ],
    )
    shifted_result, shifted_reason, shifted_metrics = arc.solve(shifted, offers[::-1], b"")
    assert shifted_reason == reason
    assert shifted_metrics["selected_region_id"] == metrics["selected_region_id"]
    assert shifted_result["latlon"] == result["latlon"]
    assert shifted_result["held_score"] == pytest.approx(result["held_score"])
    _, missing_reason, missing_metrics = arc.solve(observation, offers[1:], b"")
    assert missing_reason != "accepted"
    assert missing_metrics.get("selected_region_id") != "correct"


def test_repeated_orbit_assignments_do_not_count_as_independent():
    assigned = np.array([[4, -1], [4, 6], [-1, 6], [7, 1]])
    assert arc._distinct_support(assigned).tolist() == [2, 2]


def test_sparse_input_withholds():
    result, reason, metrics = arc.solve(
        {"duration_s": 15, "tracks": []}, [{"id": "offer", "center": [0, 0]}], b""
    )
    assert result is None and reason == "insufficient_arc_tracks"
    assert metrics["usable_tracks"] == 0


def test_longitude_test_preserves_true_fix_after_independent_track_offsets(
    monkeypatch, orbit_tiles
):
    tile, observation = orbit_tiles
    monkeypatch.setattr(grid, "prepare_sky", lambda *args: None)
    monkeypatch.setattr(grid, "make_tile", lambda sky, center: tile(center))
    offers = [
        dict(id="correct", center=[20.0, -45.0]),
        dict(id="other", center=[20.75, -44.25]),
    ]
    shifted = dict(
        observation,
        tracks=[
            dict(track, values=[f + 4100.0 * index for f in track["values"]])
            for index, track in enumerate(observation["tracks"])
        ],
    )
    baseline, candidate = off_region_test.compare(observation, offers, b"")
    _, shifted_candidate = off_region_test.compare(shifted, offers[::-1], b"")
    assert baseline["reason"] == candidate["reason"] == shifted_candidate["reason"] == "accepted"
    assert candidate["metrics"]["longitude_control"]["null_tiles_tested"] == 38
    assert (
        shifted_candidate["metrics"]["longitude_control"]
        == candidate["metrics"]["longitude_control"]
    )
    assert shifted_candidate["arms"]["c0"]["latlon"] == candidate["arms"]["c0"]["latlon"]
    assert shifted_candidate["arms"]["c0"]["rf_rms_hz"] == pytest.approx(
        candidate["arms"]["c0"]["rf_rms_hz"], abs=1e-9
    )
