"""The combined radio hypotheses retain native hardware and noise coordinates."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_combined_radio")
    finally:
        sys.path.pop(0)


def test_independent_columns_decode_the_same_four_physical_rates(tool):
    tracks = [dict(receiver=rx, channel=ch) for rx in (1, 2) for ch in (1, 5)]
    times = np.tile([50.0, 250.0], 4)
    problem = SimpleNamespace(
        scan=SimpleNamespace(tracks=tracks),
        members=list(range(4)),
        slices=[slice(2 * i, 2 * i + 2) for i in range(4)],
        flat_times=times,
        hardware=np.zeros((8, 8)),
    )
    coefficient = np.array([0.2, -0.4, 0.3, 0.8])
    for sigma in (2.0, 10.0):
        tool.replace_drift_columns(problem, sigma)
        # Parent covariance coordinates multiply RX-mean columns by ten.
        scaled = problem.hardware[:, 4:8] * [10, 1, 10, 1]
        expected = np.repeat(coefficient * sigma, 2) * (times - 150)
        np.testing.assert_allclose(scaled @ coefficient, expected)
        assert np.count_nonzero(problem.hardware[:, 4:8]) == 8


def test_combined_model_rejects_an_unspecified_hypothesis(tool):
    with pytest.raises(ValueError, match="unknown"):
        tool.CombinedRadio(None, None, False, variant="GPS_selected")
