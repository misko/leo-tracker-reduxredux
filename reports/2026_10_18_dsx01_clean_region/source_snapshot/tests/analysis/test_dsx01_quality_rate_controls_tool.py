"""Frequency rates share their RF reference and cannot silently discard points."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_quality_rate_controls")
    finally:
        sys.path.pop(0)


def test_one_rate_scales_across_channels_but_not_an_unsupported_satellite(tool):
    labels = np.array([0, 0, 1, 2])
    q, times = np.array([0.9, 1.1, 1.0, 1.05]), np.array([100, 200, 250, 100])
    columns = tool.rate_columns(labels, q, times, [0, 1], 0.25)
    np.testing.assert_allclose(columns @ [2, -1], [-22.5, 27.5, -25, 0])


def test_quality_floor_preserves_nonzero_votes_and_does_not_boost_any_fragment(tool):
    np.testing.assert_array_equal(
        tool.reliability_weights([0, 0.001, 0.1, 1]), [0.01, 0.01, 0.1, 1]
    )
    with pytest.raises(ValueError):
        tool.reliability_weights([-0.1])
