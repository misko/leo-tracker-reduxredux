import importlib.util
import sys
from pathlib import Path

import numpy as np


def subject():
    path = (
        Path(__file__).parents[2]
        / "reports/2026_09_23_long_training_search/search.py"
    )
    spec = importlib.util.spec_from_file_location("long_training_search", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_regular_grid_interpolation_is_linear_and_rejects_out_of_range():
    module = subject()
    grid = np.asarray([0, 1_000_000_000, 2_000_000_000], dtype=np.int64)
    values = np.arange(3.0)[None, :, None] * np.ones((1, 1, 3))
    position, velocity = module.interpolate_track(values, 2 * values, grid, [0.5, 1.5])
    np.testing.assert_allclose(position[0, :, 0], [0.5, 1.5])
    np.testing.assert_allclose(velocity[0, :, 0], [1.0, 3.0])
    with np.testing.assert_raises_regex(ValueError, "outside"):
        module.interpolate_track(values, values, grid, [-0.1, 0.5])
    with np.testing.assert_raises_regex(ValueError, "outside"):
        module.interpolate_track(values, values, grid, [2.000000001])


def test_diverse_beam_keeps_low_scores_with_required_spacing():
    module = subject()
    rows = [
        {"objective_rmse_hz": score, "east_km": east, "north_km": 0.0}
        for score, east in ((1.0, 0.0), (2.0, 1.0), (3.0, 10.0), (4.0, 20.0))
    ]
    selected = module.diverse_best(rows, spacing=9.0, count=3)
    assert [row["east_km"] for row in selected] == [0.0, 10.0, 20.0]


def test_every_declared_prior_trial_stays_inside_conservative_normal_cap():
    module = subject()
    for _name, (latitude, longitude, radius) in module.PRIORS.items():
        centre = (latitude, longitude)
        centre_normal = module.receiver_ecef(latitude, longitude)[1]
        for angle in np.linspace(0, 2 * np.pi, 97):
            point = module.offset_coordinate(
                centre, radius * np.sin(angle), radius * np.cos(angle)
            )
            normal = module.receiver_ecef(*point)[1]
            separation = np.arccos(np.clip(np.dot(centre_normal, normal), -1.0, 1.0))
            assert separation <= radius / 6335.0 + 1e-12
            assert module.haversine_km(centre, point) <= radius + 1e-9


def test_candidate_and_offset_ignore_reserved_frequency_values():
    module = subject()
    receiver, _ = module.receiver_ecef(0.0, 0.0)
    position = np.tile(receiver + [600.0, 0.0, 0.0], (2, 4, 1))
    velocity = np.zeros_like(position)
    velocity[0, :, 0] = [0.0, 1.0, 2.0, 3.0]
    velocity[1, :, 0] = [0.0, 3.0, 1.0, 2.0]
    measured = -module.REFERENCE_RF_HZ / module.LIGHT_KM_S * velocity[0, :, 0] + 123.0
    track = {
        "track_id": "synthetic", "position": position, "velocity": velocity,
        "measured_hz": measured.copy(), "training_mask": np.array([True, True, False, False]),
        "weight_s": 4,
    }
    initial, rows = module.score_point([track], ["correct", "wrong"], 0.0, 0.0, True)
    assert rows[0]["candidate_id"] == "correct"
    np.testing.assert_allclose(rows[0]["frequency_offset_hz"], 123.0)
    np.testing.assert_allclose(rows[0]["evaluation_rms_hz"], 0.0, atol=1e-8)
    track["measured_hz"][2:] += 10000.0
    changed, selected = module.score_point([track], ["correct", "wrong"], 0.0, 0.0, True)
    assert changed == initial
    assert selected[0]["candidate_id"] == rows[0]["candidate_id"]
    assert selected[0]["frequency_offset_hz"] == rows[0]["frequency_offset_hz"]
    np.testing.assert_allclose(selected[0]["evaluation_rms_hz"], 10000.0)


def test_invisible_candidates_receive_capped_unmatched_penalty():
    module = subject()
    receiver, _ = module.receiver_ecef(0.0, 0.0)
    position = np.tile(-receiver, (1, 4, 1))
    track = {
        "track_id": "invisible", "position": position, "velocity": np.zeros_like(position),
        "measured_hz": np.zeros(4), "training_mask": np.array([True, True, False, False]),
        "weight_s": 4,
    }
    objective, rows = module.score_point([track], ["below-horizon"], 0.0, 0.0, True)
    assert objective == 800.0
    assert rows[0]["candidate_id"] is None
