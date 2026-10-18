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
        yield importlib.import_module("prototype_s01_joint_radio_orbit")
    finally:
        sys.path.remove(path)


def test_wider_drift_changes_only_receiver_prior_even_with_shared_shape_tail(tool):
    scan, seed = problem_inputs()
    old = {k: v.copy() for k, v in scan.sky.items()}
    p = tool.CausalShapeFamilies(scan, seed, "shared_phase", False, (0, 0), aligned_previous=old)
    wrapped = tool.WideDriftProblem(p)
    x = p.initial.copy()
    x[6] = 1
    x[-1] = 0.5
    a, b = p.residual(x), wrapped.residual(x)
    changed = np.flatnonzero(abs(a - b) > 1e-10)
    assert len(changed) == 1
    assert b[changed[0]] == pytest.approx(a[changed[0]] / 4)
    np.testing.assert_allclose(a[-1:], b[-1:])
    assert wrapped.upper[6] == 10 and wrapped.lower[6] == -10
