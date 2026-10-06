from dataclasses import replace

import numpy as np
import pytest
from test_regional_position_score import synthetic_inputs

from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_score import PositionObjective
from leo.contracts.regional_position import POSITION_SCORES


def bootstrap_fixture():
    observations, bank, prior = synthetic_inputs()
    rows = np.arange(len(observations.window_ids))
    tracks = tuple(tuple(rows[rows % 12 == lane]) for lane in range(12))
    observations = replace(
        observations,
        measured_hz=observations.measured_hz
        + 600 * (1 - 2 * observations.receiver)
        + 0.5 * (observations.times_s - observations.time_center_s),
    )
    return observations, bank, prior, tracks


def test_shape_bootstrap_initializes_shared_receiver_lines():
    observations, bank, prior, tracks = bootstrap_fixture()
    result = bootstrap_position(observations, bank, prior, [3, -5], tracks, maximum_seconds=10)
    assert len(result.satellite_indices) >= 2
    assert {observations.receiver[m.rows[0]] for m in result.matches} == {0, 1}
    objective = PositionObjective(
        observations, bank.select(list(result.satellite_indices)), prior, POSITION_SCORES["T1AT"]
    )
    empty = result.vector.copy()
    empty[2:7] = 0
    assert objective.evaluate(result.vector)[0] < objective.evaluate(empty)[0]
    assert np.max(abs(result.vector[7] + objective.basis @ result.vector[8:])) <= 20 + 1e-9


def test_bootstrap_is_bounded_and_validates_physical_tracks():
    observations, bank, prior, tracks = bootstrap_fixture()
    with pytest.raises(TimeoutError):
        bootstrap_position(observations, bank, prior, [0, 0], tracks, maximum_seconds=1e-12)
    with pytest.raises(ValueError, match="track indices"):
        bootstrap_position(observations, bank, prior, [0, 0], ((0, 0, 0),))
    with pytest.raises(ValueError, match="receiver/RF"):
        bootstrap_position(observations, bank, prior, [0, 0], ((0, 1, 2),))


def test_overlapping_shape_proposals_do_not_duplicate_likelihood_windows():
    observations, bank, prior, tracks = bootstrap_fixture()
    result = bootstrap_position(
        observations, bank, prior, [3, -5], tracks + (tracks[0],), maximum_seconds=10
    )
    assert result.matches
    assert len(observations.window_ids) == len(set(observations.window_ids))
