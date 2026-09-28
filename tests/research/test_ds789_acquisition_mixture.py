import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_acquisition_mixture import posterior, predictive_ratio  # noqa: E402


def test_predictive_average_equals_joint_to_training_evidence():
    evidence = np.array([-15.0, 8.0, 0.0])
    prediction = np.array([3.0, -7.0, 0.0])
    prior = np.array([0.25, 0.25, 0.5])
    weights = posterior(evidence, prior)
    expected = np.log(
        np.sum(prior * np.exp(evidence + prediction)) / np.sum(prior * np.exp(evidence))
    )
    assert predictive_ratio(weights, prediction) == pytest.approx(expected, abs=1e-12)
    np.testing.assert_allclose(posterior(evidence + 10000, prior), weights, atol=1e-12)
    assert np.exp(weights).sum() == pytest.approx(1)
    # Changing held predictions must not mutate training weights.
    before = weights.copy()
    predictive_ratio(weights, -prediction)
    np.testing.assert_array_equal(weights, before)


def test_invalid_mixture_contracts_rejected():
    with pytest.raises(ValueError, match="sum to one"):
        posterior([0, 0], [0.5, 0.6])
    with pytest.raises(ValueError, match="dimensions"):
        posterior([0, 0], [1])
    with pytest.raises(ValueError, match="positive"):
        posterior([0, 0], [0, 1])
    with pytest.raises(ValueError, match="normalized"):
        predictive_ratio([0, 0], [1, 2])
