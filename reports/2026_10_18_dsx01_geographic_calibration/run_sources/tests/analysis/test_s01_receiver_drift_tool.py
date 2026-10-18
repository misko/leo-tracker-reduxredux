import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_s01_receiver_drift")
    finally:
        sys.path.remove(path)


def test_common_mode_and_band_contrast_decode_to_native_hz_per_second(tool):
    scan, seed = problem_inputs()
    p = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    wrapped = tool.ReceiverDriftProblem(p, mean_sigma=5, contrast_sigma=0.5)
    x = wrapped.initial.copy()
    low, high, *_ = wrapped.pairs[0]
    x[low] = 1
    x[high] = 0.6
    beta = wrapped.decode(x)["beta"]
    np.testing.assert_allclose(beta[4:6] / 150, [4.7, 5.3])
    np.testing.assert_allclose(beta[6:8], 0)
    r = wrapped.residual(x)
    start = len(r) - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [1, 0.6, 0, 0])


def test_zero_drift_preserves_original_frequency_and_data_coordinates(tool):
    scan, seed = problem_inputs()
    p = tool.AnchoredFamilies(scan, seed, "shared_phase", True, (0, 0))
    wrapped = tool.ReceiverDriftProblem(p)
    np.testing.assert_allclose(p.predicted(p.initial)[0], wrapped.predicted(wrapped.initial)[0])
    np.testing.assert_allclose(p.residual(p.initial), wrapped.residual(wrapped.initial))
