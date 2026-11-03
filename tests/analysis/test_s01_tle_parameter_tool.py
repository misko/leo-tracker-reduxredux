"""Scientific invariants for the bounded S01 element perturbation prototype."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from sgp4.api import Satrec


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("fit_s01_69333_tle_parameter")
    finally:
        sys.path.remove(path)


@pytest.fixture
def satellite():
    return Satrec.twoline2rv(
        "1 69333U 26122E   26289.32649878  .00019639  00000-0  60857-3 0  9998",
        "2 69333  97.2840 317.5178 0001786  91.9071 268.2376 15.33470349 20754",
    )


def test_zero_element_change_reproduces_original_sgp4(tool, satellite):
    clone = tool.perturb(satellite, "phase_only", 0)
    assert (clone.jdsatepoch, clone.jdsatepochF) == (satellite.jdsatepoch, satellite.jdsatepochF)
    for time in (-300, 0, 500, 800):
        status, p, v = satellite.sgp4_tsince(time)
        other_status, other_p, other_v = clone.sgp4_tsince(time)
        assert status == other_status == 0
        np.testing.assert_allclose(other_p, p, atol=1e-9, rtol=0)
        np.testing.assert_allclose(other_v, v, atol=1e-12, rtol=0)


@pytest.mark.parametrize("component", ["e_cos_omega", "e_sin_omega"])
def test_e_vector_preserves_latitude_and_other_component(tool, satellite, component):
    # This traverses e*sin(omega)=0; the angular representation must not create
    # an artificial 180-degree orbital phase shift.
    delta = -0.0003
    changed = tool.perturb(satellite, component, delta)
    old_e = satellite.ecco * np.array([np.cos(satellite.argpo), np.sin(satellite.argpo)])
    new_e = changed.ecco * np.array([np.cos(changed.argpo), np.sin(changed.argpo)])
    expected = old_e.copy()
    expected[int(component == "e_sin_omega")] += delta
    np.testing.assert_allclose(new_e, expected, atol=1e-16, rtol=0)
    phase_error = changed.mo + changed.argpo - satellite.mo - satellite.argpo
    assert abs(np.arctan2(np.sin(phase_error), np.cos(phase_error))) < 1e-14
    status, position, _ = changed.sgp4_tsince(500)
    assert status == 0 and np.isfinite(position).all()


def test_mean_motion_uses_revolutions_per_day_units(tool, satellite):
    changed = tool.perturb(satellite, "mean_motion_rev_day", 0.001)
    np.testing.assert_allclose((changed.no_kozai - satellite.no_kozai) * 1440 / (2 * np.pi),
                               0.001, rtol=0, atol=1e-14)
