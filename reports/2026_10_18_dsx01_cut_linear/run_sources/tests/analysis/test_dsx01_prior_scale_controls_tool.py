"""Expanded covariance preserves physical predictions and normalized prior cost."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_prior_scale_controls")
    finally:
        sys.path.pop(0)


def test_scaled_mode_decoder_preserves_prediction_and_quadratic(tool):
    rng = np.random.default_rng(182)
    y, u = rng.normal(0, 200, 30), rng.normal(0, 80, (30, 5))
    groups, scale = np.repeat([0, 1, 2], 10), np.array([1, 3, 5, 3, 1])
    raw = tool.hierarchical_bound(y, u * scale, 100, groups)
    result = tool.scale_bound(y, u, 100, groups, scale)
    np.testing.assert_allclose(u @ result["coefficient"], (u * scale) @ raw["coefficient"])
    np.testing.assert_allclose(
        np.sum(result["coefficient"] ** 2 * result["coefficient_prior_precision"]),
        np.sum(raw["coefficient"] ** 2),
    )
    np.testing.assert_array_equal(result["residual"], raw["residual"])


def test_invalid_prior_scale_is_explicit(tool):
    with pytest.raises(ValueError, match="positive"):
        tool.scale_bound([1], [[1]], 100, np.array([0]), [-1])
