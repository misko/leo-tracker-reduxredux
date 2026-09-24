import importlib.util
from pathlib import Path

import numpy as np
import pytest


def _load(name):
    path = Path(__file__).parents[2] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


subject = _load("report_phase_curvature_bound")
scenario = _load("report_phase_geometry_scenarios")


def test_interpolation_bound_is_tight_for_quadratic_on_unequal_intervals():
    times = [-0.3, 0.0, 1.7]
    acceleration = 4.2
    values = [7 + 3 * t + acceleration * t * t / 2 for t in times]
    residual, multiplier = subject.interpolation_residual(times, values)
    assert abs(residual) == pytest.approx(acceleration * multiplier)


def test_curvature_bound_contains_independent_orbit_finite_differences():
    rng = np.random.default_rng(8721)
    count = 256
    los = scenario.los_from_el_az(
        rng.uniform(0.1, np.pi / 2, count), rng.uniform(0, 2 * np.pi, count)
    )
    headings = rng.uniform(0, 2 * np.pi, count)
    baseline = rng.normal(size=(count, 3))
    baseline *= 0.115 / np.linalg.norm(baseline, axis=1)[:, None]
    for altitude in (350_000, 550_000, 1_200_000, 20_200_000):
        phases = []
        for t in (-0.05, 0, 0.05):
            sight = scenario.propagate_los(los, altitude, headings, t)
            rotated = scenario.rotate_z(baseline, scenario.EARTH_RATE_RAD_S * t)
            phases.append(scenario.phase_deg(scenario.RF_HZ, rotated, sight))
        numerical = (phases[2] - 2 * phases[1] + phases[0]) / 0.05**2
        _, bound = subject.circular_bounds(altitude, 0.115, scenario.RF_HZ)
        assert np.max(np.abs(numerical)) < bound


def test_rejects_nonphysical_bound_inputs():
    with pytest.raises(ValueError):
        subject.circular_bounds(0, 0.1, 11e9)
