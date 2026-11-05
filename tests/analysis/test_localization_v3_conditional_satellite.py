from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.conditional_satellite import (
    conditional_update,
    family_coordinates,
)


def test_only_requested_family_coordinates_and_its_curved_bias_are_free():
    problem = SimpleNamespace(
        hardware=np.zeros((1, 9)),
        smooth=np.zeros((1, 4)),
        labels=[7, 2, 9],
        supported=[2, 7],
        rows=[dict(candidate_index=j) for j in [7, 2, 7, 9]],
    )
    assert family_coordinates(problem, [7]) == [13, 19, 20, 21, 22, 24]
    assert family_coordinates(problem, [7], include_bias=False) == [13, 19, 20, 21]
    assert family_coordinates(problem, [9]) == [15, 25]
    for invalid in [[], [123]]:
        with pytest.raises(ValueError, match="satellite families"):
            family_coordinates(problem, invalid)


def test_conditional_update_matches_dense_gaussian_and_fixes_other_coordinates():
    rng = np.random.default_rng(4081)
    design = rng.normal(size=(12, 5))
    factor = rng.normal(size=(5, 5))
    precision = factor.T @ factor + np.eye(5)
    mean = rng.normal(size=5)
    raw = rng.normal(size=12) * 50
    sigma = rng.uniform(1, 5, size=12)
    groups = np.repeat([0, 1, 2], 4)
    indices = [2, 4]
    delta, prediction, distance = conditional_update(
        mean, precision, design, raw, sigma, groups, indices
    )

    # Independent observation-space marginalization. Excluded coefficients are
    # fixed, so use the selected precision block, not a covariance sub-block.
    selected = precision[np.ix_(indices, indices)]
    covariance = np.linalg.inv(selected)
    u = design[:, indices]
    noise = np.diag(2 * sigma**2)
    biases = 300.0**2 * (groups[:, None] == groups[None, :])
    marginal = noise + biases + u @ covariance @ u.T
    weighted = np.linalg.solve(marginal, raw)
    expected_delta = covariance @ u.T @ weighted
    expected_objective = raw @ weighted + np.linalg.slogdet(marginal)[1] + 12 * np.log(2 * np.pi)
    np.testing.assert_allclose(delta[indices], expected_delta, atol=1e-9)
    np.testing.assert_array_equal(delta[[0, 1, 3]], 0)
    assert prediction["objective"] == pytest.approx(expected_objective, abs=1e-7)
    assert distance**2 == pytest.approx(expected_delta @ selected @ expected_delta, abs=1e-9)
    assert not np.allclose(covariance, np.linalg.inv(precision)[np.ix_(indices, indices)])
