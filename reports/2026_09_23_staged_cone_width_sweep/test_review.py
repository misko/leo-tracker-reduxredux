"""Independent synthetic checks for the staged full-FOV width sweep."""

import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("staged_width_review", PATH)
RUN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN)


def _direction(angle_deg):
    angle = np.radians(angle_deg)
    return np.array([[np.sin(angle), 0.0, np.cos(angle)]])


def _track(held_scale=1.0):
    return {
        "session_id": "synthetic-session",
        "track_id": "synthetic-track",
        "receiver_id": 0,
        "weight_s": 1.0,
        "observation_count": 4,
        "span_s": 3.0,
        "train_mask": np.array([True, True, False, False]),
        "baseline_candidate_id": "visible",
        "retained_indices": np.array([0, 1]),
        "retained_candidate_ids": np.array(["visible", "outside"]),
        "retained_costs": np.array([0.2, 0.1]),
        "retained_directions": np.array([_direction(4.9), _direction(5.1)]),
        "retained_errors": np.array(
            [[10.0, 10.0, 20.0 * held_scale, 20.0 * held_scale],
             [11.0, 11.0, 30.0 * held_scale, 30.0 * held_scale]]
        ),
    }


def test_full_fov_ten_uses_exactly_five_degree_half_angle_boundary():
    axis = np.array([0.0, 0.0, 1.0])
    assert RUN.all_samples_inside(_direction(4.999), axis, 10.0)
    assert not RUN.all_samples_inside(_direction(5.001), axis, 10.0)


def test_fixed_orientation_compatibility_is_nested_across_widths():
    axis = np.array([0.0, 0.0, 1.0])
    directions = np.concatenate([_direction(4.9), _direction(10.0)])
    compatible_10 = RUN.all_samples_inside(directions, axis, 10.0)
    compatible_25 = RUN.all_samples_inside(directions, axis, 25.0)
    compatible_30 = RUN.all_samples_inside(directions, axis, 30.0)
    assert np.all(~compatible_10 | compatible_25)
    assert np.all(~compatible_25 | compatible_30)


def test_same_los_cannot_be_in_both_five_degree_caps():
    base = RUN.load(RUN.BASE, "width_review_base")
    cone = RUN.load(base.CONE, "width_review_cone")
    axes = cone.axes_batched(cone.orientation_grid(15))
    same_los = axes[:, 0, :]
    first = np.sum(same_los * axes[:, 0, :], axis=1) >= np.cos(np.radians(5.0))
    second = np.sum(same_los * axes[:, 1, :], axis=1) >= np.cos(np.radians(5.0))
    assert np.all(first)
    assert not np.any(first & second)


def test_held_mutation_cannot_change_refit_training_cost():
    axes = np.array([[[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]]])
    base = type("Base", (), {"CAP_HZ": 800.0})
    original = RUN.evaluate(base, [_track()], axes, 0, (0, 1), 10.0)
    perturbed = RUN.evaluate(base, [_track(1_000.0)], axes, 0, (0, 1), 10.0)
    assert perturbed["training_capped_loss"] == original["training_capped_loss"]
    assert perturbed["held_capped_loss"] != original["held_capped_loss"]


def test_ten_degree_refit_rejects_candidate_outside_five_degree_cap():
    chosen = RUN.refit_track(_track(), np.array([0.0, 0.0, 1.0]), 10.0)
    assert chosen == 0
