import copy

import numpy as np
import pytest

from tools.rx_geometry_temporal_transfer import score_lanes, within_center_from_reception


def _lane():
    return {
        "x": np.arange(4 * 2 * 2 * 8, dtype=float).reshape(4, 2, 2, 8),
        "roles": np.array(["reception", "reception", "held_frequency", "held_frequency"]),
    }


def test_within_mean_uses_reception_only_and_applies_to_held() -> None:
    lane = _lane()
    original = lane["x"].copy()
    changed = within_center_from_reception([lane])[0]
    expected_mean = original[:2, ..., 3:8].mean(axis=0, keepdims=True)
    np.testing.assert_array_equal(changed["x"][..., :3], original[..., :3])
    np.testing.assert_allclose(changed["x"][:2, ..., 3:8].mean(axis=0), 0.0)
    np.testing.assert_array_equal(
        changed["x"][2:, ..., 3:8], original[2:, ..., 3:8] - expected_mean
    )


def test_held_geometry_cannot_change_center_applied_to_reception() -> None:
    lane = _lane()
    changed_input = copy.deepcopy(lane)
    changed_input["x"][2:, ..., 3:8] += 1_000_000.0
    first = within_center_from_reception([lane])[0]
    second = within_center_from_reception([changed_input])[0]
    np.testing.assert_array_equal(first["x"][:2], second["x"][:2])


def test_controlled_swap_and_reverse_use_their_reception_means() -> None:
    original = _lane()
    swapped = copy.deepcopy(original)
    swapped["x"][..., 6:8] *= -1
    reversed_lane = copy.deepcopy(original)
    reversed_lane["x"][:2, ..., 3:8] = reversed_lane["x"][1::-1, ..., 3:8]
    for controlled in (swapped, reversed_lane):
        centered = within_center_from_reception([controlled])[0]
        np.testing.assert_allclose(centered["x"][:2, ..., 3:8].mean(axis=0), 0.0)
        np.testing.assert_array_equal(centered["x"][..., :3], controlled["x"][..., :3])


def test_inputs_are_not_mutated() -> None:
    lane = _lane()
    before = copy.deepcopy(lane)
    within_center_from_reception([lane])
    np.testing.assert_array_equal(lane["x"], before["x"])
    np.testing.assert_array_equal(lane["roles"], before["roles"])


def test_score_lanes_carries_reception_posterior_into_held(monkeypatch) -> None:
    import tools.rx_geometry_temporal_transfer as transfer

    emissions = np.log([[1.0, 1.0], [0.2, 0.8], [0.9, 0.1]])
    monkeypatch.setattr(transfer, "relative_emissions", lambda lane, beta: emissions)
    lane = {
        "prior": np.array([0.0]),
        "times": np.array([0.0, 1.0, 5.0]),
        "roles": np.array(["reception", "reception", "held_frequency"]),
        "indices": [0, 1, 2],
        "reference": np.zeros(3),
        "source": {
            "lane": {"session_id": "s"},
            "windows": [
                {
                    "source_window_id": str(index),
                    "prediction_utc_ns": int(time * 1e9),
                }
                for index, time in enumerate((0.0, 1.0, 5.0))
            ],
        },
    }
    result = score_lanes([lane], {"beta": [0.0], "occupancy": 0.5, "tau_s": 2.0})
    # Re-scoring the held row from the stationary prior would give log(.5); the
    # reception prefix favors presence and changes the held predictive score.
    held = result["roles"]["held_frequency"]["relative_log_score"]
    assert held != pytest.approx(np.log(0.5))
    assert result["lanes"][0]["windows"][2]["elapsed_s"] == 5.0


def test_held_emission_change_cannot_change_reception_scores(monkeypatch) -> None:
    import tools.rx_geometry_temporal_transfer as transfer

    base = np.log([[1.0, 1.0], [0.4, 0.6], [0.7, 0.3]])
    current = base.copy()
    monkeypatch.setattr(transfer, "relative_emissions", lambda lane, beta: current)
    lane = {
        "prior": np.array([0.0]),
        "times": np.array([0.0, 1.0, 4.0]),
        "roles": np.array(["reception", "reception", "held_frequency"]),
        "indices": [0, 1, 2],
        "reference": np.zeros(3),
        "source": {
            "lane": {"session_id": "s"},
            "windows": [
                {"source_window_id": str(index), "prediction_utc_ns": index * 1_000_000_000}
                for index in range(3)
            ],
        },
    }
    fitted = {"beta": [0.0], "occupancy": 0.5, "tau_s": 1.0}
    first = score_lanes([lane], fitted)
    current = base.copy()
    current[2] = np.log([0.0001, 100.0])
    second = score_lanes([lane], fitted)
    assert second["roles"]["reception"] == first["roles"]["reception"]
