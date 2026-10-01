"""Independent synthetic checks for B1's uncapped compact-gradient path."""

from __future__ import annotations

import numpy as np
from test_adapter import port

from leo.analysis import localization_soft as soft


def test_uncapped_compact_proposal_matches_full_soft_objective_gradient() -> None:
    track_port = port()
    state = np.array([12.0, -8.0, 0.1, 0.2, -0.3, 0.01, -0.05])
    prediction = track_port.predict_selected(state, 0)
    track_port.observation = prediction.mean + np.linspace(-1.0, 1.0, prediction.mean.size)
    track_port.likelihood.observation = track_port.observation
    track_port.likelihood.background_log_likelihood = -100.0
    track_port._score_key = None

    precision = np.array([0.02, 0.03, 1.0, 4.0, 4.0, 4.0, 4.0])
    center = np.zeros_like(state)
    scores = soft._scores(track_port, state)
    probabilities = soft._responsibilities(scores)
    indices, omitted, truncated = soft._working_indices(
        probabilities, track_port.candidate_count, None, 1e-6
    )
    np.testing.assert_array_equal(indices, np.flatnonzero(probabilities[:-1] > 0.0))
    assert omitted == 0.0
    assert not truncated

    branches = soft._compact_linearizations(track_port, state, indices, probabilities)
    lookup = np.arange(state.size)
    system = np.diag(precision)
    proposal_gradient = -precision * (state - center)
    for branch in branches:
        soft._scatter_student_t_contribution(system, proposal_gradient, lookup, branch, 4.0)

    def objective(value: np.ndarray) -> float:
        return soft._objective(value, (track_port,), center, precision, lambda _state: True, None)

    step = 1e-4
    basis = np.eye(state.size)
    finite_difference = np.array(
        [
            (objective(state + step * row) - objective(state - step * row)) / (2.0 * step)
            for row in basis
        ]
    )
    # The normal-equation right side is the negative objective gradient.
    np.testing.assert_allclose(proposal_gradient, -finite_difference, rtol=2e-7, atol=2e-8)
    assert len(branches) == track_port.candidate_count
