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
        yield importlib.import_module("prototype_s01_causal_shape")
    finally:
        sys.path.remove(path)


def test_zero_shared_correction_preserves_original_curve_and_loss(tool):
    scan, seed = problem_inputs()
    old = {k: v.copy() for k, v in scan.sky.items()}
    old["position_km"][..., 0] += 1
    p = tool.CausalShapeFamilies(scan, seed, "shared_phase", False, (0, 0), aligned_previous=old)
    baseline = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    np.testing.assert_allclose(p.predicted(p.initial)[0], baseline.predicted(baseline.initial)[0])
    np.testing.assert_allclose(p.residual(p.initial)[:-1], baseline.residual(baseline.initial))


def test_one_family_correction_is_shared_across_receivers_and_actual_RF_channels(tool):
    scan, seed = problem_inputs()
    old = {k: v.copy() for k, v in scan.sky.items()}
    old["velocity_km_s"][..., 1] += 0.01
    p = tool.CausalShapeFamilies(scan, seed, "shared_phase", True, (0, 0), aligned_previous=old)
    x = p.initial.copy()
    x[-1] = 1
    delta = p.predicted(x)[0] - p.predicted(p.initial)[0]
    first = delta[p.slices[0]]
    for block in p.slices[1:]:
        np.testing.assert_allclose(delta[block], first)
    assert np.max(abs(first)) > 1
    assert len(p.decode(x)["causal_shape_coefficients"]) == 1
