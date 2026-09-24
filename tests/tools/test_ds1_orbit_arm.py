"""Unit checks for the standalone DS1 causal-rate arm."""

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _module():
    path = Path(__file__).parents[2] / "reports/2026_09_24_ds1_orbit_arm/run.py"
    spec = importlib.util.spec_from_file_location("ds1_orbit_arm_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_quartic_reproduces_all_five_nodes_and_historical_extrapolation():
    module = _module()
    nodes = np.stack(
        [np.full((5, 3), float(knot)) for knot in module.NODES],
        axis=1,
    )
    # A linear state is reproduced at all interpolation nodes and outside the
    # node interval. Historical formal_orbit deliberately permits that local
    # extrapolation, subject to the exact SGP4 replay gate.
    phase = np.asarray([-3.5, -2.0, -0.25, 0.0, 1.5])
    output = module.quartic(nodes, phase)
    np.testing.assert_allclose(output, np.repeat(phase[:, None], 3, axis=1))
