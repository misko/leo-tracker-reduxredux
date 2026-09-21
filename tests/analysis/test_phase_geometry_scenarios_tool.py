from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

TOOL_PATH = Path(__file__).parents[2] / "tools" / "report_phase_geometry_scenarios.py"
SPEC = importlib.util.spec_from_file_location("phase_geometry_scenarios", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_zero_baseline_and_linear_baseline_frequency_scaling() -> None:
    los = np.array([[0.4, -0.2, 0.89442719]])
    zero = MODULE.phase_deg(MODULE.RF_HZ, np.zeros(3), los)
    base = MODULE.phase_deg(MODULE.RF_HZ, np.array([0.0, 0.08, 0.0]), los)
    scaled = MODULE.phase_deg(2 * MODULE.RF_HZ, np.array([0.0, 0.16, 0.0]), los)
    assert zero[0] == 0.0
    assert scaled[0] == pytest.approx(4 * base[0])


def test_common_source_equal_frequency_double_difference_is_zero() -> None:
    los = MODULE.los_from_el_az(np.radians(np.array([45.0])), np.array([0.3]))
    heading = np.radians(np.array([45.0]))
    delta = MODULE.propagate_los(los, 550_000.0, heading, 9.0) - los
    baseline = np.array([0.0, 0.08, 0.0])
    dd = MODULE.phase_deg(MODULE.RF_HZ, baseline, delta) - MODULE.phase_deg(
        MODULE.RF_HZ, baseline, delta
    )
    assert dd[0] == 0.0


def test_ideal_geo_has_zero_phase_change_in_rotating_holder_frame() -> None:
    los = MODULE.los_from_el_az(np.radians(np.array([37.0])), np.array([1.2]))
    baseline = np.array([0.0, 0.08, 0.0])
    dt = 123.0
    change = MODULE.phase_deg(
        MODULE.RF_HZ,
        MODULE.rotate_z(baseline, MODULE.EARTH_RATE_RAD_S * dt),
        MODULE.ideal_geo_los(los, dt),
    ) - MODULE.phase_deg(MODULE.RF_HZ, baseline, los)
    assert change[0] == pytest.approx(0.0, abs=1e-11)


def test_known_los_analytic_derivative_matches_small_step() -> None:
    los = MODULE.los_from_el_az(np.radians(np.array([60.0])), np.array([0.7]))
    heading = np.radians(np.array([45.0]))
    position = MODULE.satellite_from_los(los, 550_000.0)
    tangent = MODULE.orbit_velocity_direction(position, heading)
    radius = MODULE.EARTH_RADIUS_M + 550_000.0
    speed = np.sqrt(MODULE.EARTH_MU_M3_S2 / radius)
    satellite_velocity = speed * tangent
    observer = np.array([MODULE.EARTH_RADIUS_M, 0.0, 0.0])
    observer_velocity = np.array([0.0, MODULE.EARTH_RATE_RAD_S * MODULE.EARTH_RADIUS_M, 0.0])
    range_vector = position - observer
    range_m = np.linalg.norm(range_vector, axis=1)[:, None]
    relative_velocity = satellite_velocity - observer_velocity
    analytic = (
        relative_velocity - los * np.sum(los * relative_velocity, axis=1)[:, None]
    ) / range_m
    step = 1e-3
    numerical = (MODULE.propagate_los(los, 550_000.0, heading, step) - los) / step
    assert numerical == pytest.approx(analytic, rel=2e-5, abs=2e-9)


def test_baseline_formula_matches_cad_equal_offset_case() -> None:
    assert MODULE.baseline_length_m(0.0) == pytest.approx(0.080)
    assert MODULE.baseline_length_m(0.050) == pytest.approx(0.09736481777)
