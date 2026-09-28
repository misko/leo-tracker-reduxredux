import copy

import numpy as np
import pytest

from tools.rx_paired_state_model import (
    calibration_score,
    relative_emissions,
    score_lane,
    state_log_probabilities,
)


def lane(windows=5):
    return {
        "times": np.arange(windows, dtype=float),
        "roles": np.array(["reception"] * 2 + ["held_frequency"] * (windows - 2)),
        "y": np.arange(windows) % 4,
        "nuisance": np.column_stack((np.ones(windows), np.zeros(windows), np.arange(windows) / 60)),
        "geometry": np.arange(windows * 2 * 3).reshape(windows, 2, 3) / 10,
        "visible": np.ones((windows, 2), dtype=bool),
        "prior": np.log([0.2, 0.5, 0.3]),
        "background": np.array([0.1, 0.2, 0.3, 0.4]),
    }


def test_normalized_joint_emissions_nesting_and_swap():
    data = lane()
    beta = np.array([0.2, 0.1, -0.3, 0, 0, 0, 0.4])
    p = state_log_probabilities(data, beta)
    np.testing.assert_allclose(np.exp(p).sum(axis=-1), 1)
    np.testing.assert_array_equal(p, state_log_probabilities(data, np.r_[beta, 0, 0]))
    np.testing.assert_array_equal(p, state_log_probabilities(data, np.r_[beta, 0, 0, 0]))
    odd = np.r_[beta, 0.2, 0.1, 0.3]
    swapped = copy.deepcopy(data)
    swapped["geometry"][..., 2] *= -1
    a, b = state_log_probabilities(data, odd), state_log_probabilities(swapped, odd)
    np.testing.assert_allclose(a[..., [0, 2, 1, 3]], b)


@pytest.mark.parametrize("occupancy", [0, 0.4, 1])
def test_batched_objective_matches_scalar_log_domain_with_other_and_padding(occupancy):
    lanes = [lane(5), lane(3)]
    lanes[1]["prior"] = np.array([0, -np.inf, -np.inf])
    lanes[0]["visible"][2, 1] = False
    beta = np.arange(10) / 10
    selected = {"beta": beta, "occupancy": occupancy, "tau_s": 2.3}
    expected = sum(sum(score_lane(item, selected)["relative_log_scores"]) for item in lanes)
    assert calibration_score(lanes, beta, occupancy, 2.3) == pytest.approx(expected, abs=1e-12)
    emissions = relative_emissions(lanes[0], beta)
    np.testing.assert_array_equal(emissions[:, [0, -1]], 0)
    assert emissions[2, 2] == 0


def test_future_observation_does_not_change_prefix_and_null_equals_background():
    data, changed = lane(), lane()
    changed["y"][-1] = (changed["y"][-1] + 1) % 4
    model = {"beta": np.arange(10) / 10, "occupancy": 0.6, "tau_s": 1}
    a, b = score_lane(data, model), score_lane(changed, model)
    assert a["full_log_scores"][:-1] == b["full_log_scores"][:-1]
    null = score_lane(data, {**model, "occupancy": 0})
    np.testing.assert_allclose(null["relative_log_scores"], 0, atol=1e-14)
    np.testing.assert_allclose(null["full_log_scores"], np.log(data["background"][data["y"]]))


def test_other_mass_not_renormalized_away():
    data = lane()
    data["prior"] = np.array([-np.inf, -np.inf, 0])
    result = score_lane(data, {"beta": np.ones(10), "occupancy": 1, "tau_s": 1})
    np.testing.assert_allclose(result["relative_log_scores"], 0, atol=1e-14)
