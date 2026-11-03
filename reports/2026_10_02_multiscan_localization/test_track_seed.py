from types import SimpleNamespace

import numpy as np
import pytest
from track_seed import ALIAS_HZ, TrackObjective


def data():
    times = np.arange(8, dtype=float)
    output = SimpleNamespace(
        times=times,
        measured=90000 + times**2,
        numbers=np.array([11, 12]),
        receiver=np.zeros(8, dtype=int),
        group=np.arange(8),
        tracks=[
            {"rows": np.arange(5), "candidate_indices": np.arange(2)},
            {"rows": np.arange(3, 8), "candidate_indices": np.arange(2)},
        ],
    )

    def predict(parameters, rows, satellites):
        return times[rows] ** 2 * (1 + satellites) + parameters[0] * times[rows], np.ones(
            len(rows), bool
        )

    output.predict = predict
    return output


def test_each_group_owned_once_and_correct_shape_selected():
    objective = TrackObjective(data())
    cost, assignments = objective.evaluate([0, 0])
    assert cost == pytest.approx(0, abs=1e-9)
    assert sum(row["source_groups"] for row in assignments) == 8
    assert all(row["catalog_number"] == 11 for row in assignments)


def test_per_observation_alias_lifts_do_not_change_shape_loss():
    original = data()
    lifted = data()
    lifted.measured += ALIAS_HZ * np.array([1, -4, 7, 1, 0, -1, 3, 3])
    before, _ = TrackObjective(original).evaluate([0.1, 0])
    after, _ = TrackObjective(lifted).evaluate([0.1, 0])
    assert before == pytest.approx(after, abs=1e-7)


def test_invalid_candidate_index_fails_closed():
    source = data()
    source.tracks[0]["candidate_indices"] = np.array([2])
    with pytest.raises(ValueError, match="candidate"):
        TrackObjective(source)
