from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from gamma_forward_sensitivity import Forward, instrument
from leo.analysis.localization_v3.hierarchical import hierarchical_bound


def fixture():
    rng = np.random.default_rng(170)
    u = rng.standard_normal((30, 7))
    y = rng.standard_normal(30) + u @ rng.standard_normal(7)
    sigma = rng.uniform(0.5, 2, 30)
    groups = np.repeat([0, 1, 2], 10)
    options = {"powers": [0.25, 0.7, 1.0], "prior_groups": [-1, -1, 0, 0, 1, 1, -1]}
    return rng, (y, u, sigma, groups), options


def test_derivative_follows_both_rate_recurrences_and_original_stop():
    rng, inputs, options = fixture()
    y, u, sigma, groups = inputs
    dy, du = rng.standard_normal((2, len(y))), rng.standard_normal((2, *u.shape))
    observer = Forward(dy, du)
    result = instrument(hierarchical_bound)(observer, *inputs, **options)
    original = hierarchical_bound(*inputs, **options)
    assert result.keys() == original.keys()
    for k, value in original.items():
        np.testing.assert_array_equal(result[k], value)
    assert result["precision_iterations"] == observer.counts["updates"] > 3
    assert np.linalg.norm(observer.drate) > 0.1
    assert np.linalg.norm(observer.dprior_rate) > 0.1
    for axis in range(2):
        delta = 1e-5
        a, b = [hierarchical_bound(y + h * dy[axis], u + h * du[axis], sigma, groups, **options)
                for h in (-delta, delta)]
        assert a["precision_iterations"] == b["precision_iterations"] == result["precision_iterations"]
        np.testing.assert_allclose(observer.jacobian[:, axis], (b["residual"] - a["residual"]) / (2 * delta),
                                   rtol=1e-6, atol=2e-9)


def test_denies_a_derivative_outside_original_symbolic_support():
    _, inputs, options = fixture()
    y, u, *_ = inputs
    u[0, 0] = 0
    tangent = Forward(np.zeros((2, len(y))), np.ones((2, *u.shape)))
    with pytest.raises(ValueError, match="symbolic support"):
        instrument(hierarchical_bound)(tangent, *inputs, **options)
