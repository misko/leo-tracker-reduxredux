from __future__ import annotations

import numpy as np
import pytest
from batch_physics import linearize_candidates
from test_adapter import port


@pytest.mark.parametrize("indices", [(0,), (1, 0)])
@pytest.mark.parametrize("east,north", [(0., 0.), (120., -70.), (-200., 130.)])
def test_compact_batch_matches_frozen_full_oracle(indices, east, north):
    track_port = port()
    state = np.array([east, north, .1, .2, -.3, .01, -.05])
    actual = linearize_candidates(track_port, state, indices)
    assert set(actual) == {
        "indices", "means", "jacobians", "columns", "covariance", "eligible"
    }
    assert actual["means"].shape == (len(indices), track_port.observation.size)
    assert actual["jacobians"].shape == (len(indices), track_port.observation.size, 6)
    assert actual["columns"].shape == (len(indices), 6)
    np.testing.assert_array_equal(actual["indices"], indices)
    for row, index in enumerate(indices):
        expected = track_port.oracle_factor().candidates[index].predict(state)
        columns = actual["columns"][row]
        np.testing.assert_array_equal(columns, [0, 1, 2, 3, 4, 5 + index])
        np.testing.assert_allclose(actual["means"][row], expected.mean, rtol=1e-10, atol=1e-8)
        np.testing.assert_allclose(
            actual["jacobians"][row], expected.jacobian[:, columns], rtol=1e-5, atol=1e-5
        )
        assert bool(actual["eligible"][row]) == expected.eligible
        np.testing.assert_array_equal(actual["covariance"], expected.covariance)


def test_visibility_and_global_clock_support_match_frozen_port():
    track_port = port()
    # Put the second synthetic satellite on the far side of Earth so the batch
    # exercises both visibility outcomes.
    track_port.bank.positions_ecef_km[1] *= -1
    state = np.zeros(7)
    actual = linearize_candidates(track_port, state, [0, 1])
    expected = [
        track_port.oracle_factor().candidates[index].predict(state).eligible
        for index in (0, 1)
    ]
    assert expected == [True, False]
    np.testing.assert_array_equal(actual["eligible"], expected)

    state[6] = track_port.bank.times_s[-2] - track_port.likelihood.times.max()
    with pytest.raises(ValueError, match="global four-knot"):
        linearize_candidates(track_port, state, [0])


@pytest.mark.parametrize("indices", [[], [0, 0], [-1], [2]])
def test_indices_are_nonempty_unique_and_in_range(indices):
    with pytest.raises(ValueError, match="indices"):
        linearize_candidates(port(), np.zeros(7), indices)
