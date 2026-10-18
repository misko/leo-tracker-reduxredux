"""Model comparisons restore the white-noise volume and keep controls matched."""

import copy
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
        yield importlib.import_module("report_dsx01_radio_orbit_followup")
    finally:
        sys.path.pop(0)


def test_noise_volume_and_each_prior_enter_once(tool):
    result = dict(
        noise_precision=np.array([0.5, 2.0]),
        conditional_residual_hz=np.array([80.0, -80.0, 40.0]),
        coefficient=np.array([2.0, 3.0, 4.0]),
        gamma_cost=7.0,
        logvolume=11.0,
        elevation=np.array([-2.0, 1.0, 2.0]),
    )
    p = SimpleNamespace(
        calculate=lambda x: result,
        sigma=80.0,
        slices=[slice(0, 2), slice(2, 3)],
        noise_groups=np.array([0, 0, 1]),
    )
    a = tool.cost_parts(p, np.zeros(2))
    np.testing.assert_allclose(a["normalized_total"], 1.5 + 4 + 25 + 7 + 11 + 1 + 6 * np.log(2))
    p.point_noise = np.array([40.0, 80.0, 160.0])
    b = tool.cost_parts(p, np.zeros(2))
    np.testing.assert_allclose(b["weighted_data"], 2 + 0.5 + 0.125)
    np.testing.assert_allclose(b["diagonal_noise_logvolume"], 6 * np.log(2))


def test_c_control_checks_the_noise_vector_and_orbit_reference(tool):
    fit = dict(
        rows=[],
        aliases=[],
        starts=[],
        grid=[],
        diagnostics=dict(
            phase_reference_s=[0.0],
            orbit_reference_standard=[[0.0, 0.0, 0.0]],
            point_noise_sigma_hz=[80.0],
        ),
    )
    fits = dict(c0=fit, fitted_c=copy.deepcopy(fit))
    tool.matched_controls(fits)
    fits["fitted_c"]["diagnostics"]["point_noise_sigma_hz"][0] = 81.0
    with pytest.raises(ValueError, match="point_noise"):
        tool.matched_controls(fits)
