"""Independent semantic checks for the staged joint-cone runner.

These tests exercise only synthetic arrays.  They do not load radio inputs or
produce an experiment result.
"""

import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).with_name("staged_run.py")
SPEC = importlib.util.spec_from_file_location("joint_cone_staged_review", PATH)
RUN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN)


class _TwoOrientationCone:
    """Small deterministic grid: orientation 0 points along x, 1 along z."""

    @staticmethod
    def orientation_grid(_maximum_tilt):
        return np.array([[0, 0, 0], [1, 0, 0]])

    @staticmethod
    def axes_batched(_orientations):
        return np.array(
            [
                [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]],
            ]
        )


def _track(held_scale=1.0):
    errors = np.array(
        [
            [10.0, 10.0, 20.0 * held_scale, 20.0 * held_scale],
            [11.0, 11.0, 30.0 * held_scale, 30.0 * held_scale],
        ]
    )
    return {
        "session_id": "synthetic-session",
        "track_id": "synthetic-track",
        "receiver_id": 0,
        "weight_s": 2.0,
        "observation_count": 4,
        "span_s": 3.0,
        "train_mask": np.array([True, True, False, False]),
        # The normal-Doppler winner is z-facing candidate A.  Candidate B is
        # cheaper only after the cone refit, and is x-facing.
        "baseline": 0,
        "baseline_candidate_id": "A",
        "baseline_cost": 0.4,
        "baseline_directions": np.array([[0.0, 0.0, 1.0]]),
        "retained_indices": np.array([0, 1]),
        "retained_candidate_ids": np.array(["A", "B"]),
        "retained_costs": np.array([0.4, 0.1]),
        "retained_directions": np.array(
            [
                [[0.0, 0.0, 1.0]],
                [[1.0, 0.0, 0.0]],
            ]
        ),
        "retained_errors": errors,
    }


def test_orientation_uses_frozen_normal_winner_before_refit():
    cone = _TwoOrientationCone()
    orientations, axes, (_gain, orientation_index) = RUN.select_shared_orientation(
        cone, [_track()], (0, 1)
    )
    assert orientations[orientation_index].tolist() == [1, 0, 0]

    scenario = RUN.evaluate_scenario([_track()], axes, orientation_index, (0, 1))
    # The z-facing frozen winner drives the orientation; B cannot replace it
    # until the subsequent visible-candidate refit, where it is not visible.
    assert scenario["assignments"][0]["baseline_candidate_id"] == "A"
    assert scenario["assignments"][0]["refit_candidate_id"] == "A"


def test_held_mutation_cannot_change_training_selection_or_cost():
    axes = _TwoOrientationCone.axes_batched(None)
    original = RUN.evaluate_scenario([_track(1.0)], axes, 1, (0, 1))
    perturbed = RUN.evaluate_scenario([_track(1_000.0)], axes, 1, (0, 1))

    assert perturbed["assignments"] == original["assignments"]
    assert perturbed["training_capped_loss"] == original["training_capped_loss"]
    assert perturbed["held_capped_loss"] != original["held_capped_loss"]


def test_restricted_all_track_cost_is_not_better_than_normal_baseline():
    axes = _TwoOrientationCone.axes_batched(None)
    scenario = RUN.evaluate_scenario([_track()], axes, 1, (0, 1))
    normal_baseline = _track()["baseline_cost"]
    assert scenario["training_capped_loss"] >= normal_baseline
