import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("surface_fusion", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_quadratic_refine_recovers_sub_grid_minimum():
    grid = np.asarray([(x, y) for x in np.arange(-20, 21, 5) for y in np.arange(-20, 21, 5)])
    objective = (grid[:, 0] - 2.25) ** 2 + 2 * (grid[:, 1] + 1.75) ** 2
    result = MODULE.quadratic_refine(grid, objective)
    assert result["quadratic_qualified"] is True
    assert np.allclose([result["reported_east_km"], result["reported_north_km"]], [2.25, -1.75])


def test_delta_mse_is_additive_offset_invariant():
    values = np.asarray([4.0, 9.0, 16.0, 25.0])
    assert np.allclose(
        MODULE.transform_surface(values, "delta_mse"),
        MODULE.transform_surface(values + 12345.0, "delta_mse"),
    )


def test_scaled_delta_is_positive_scale_invariant_without_floor():
    values = np.asarray([4.0, 9.0, 16.0, 25.0])
    assert np.allclose(
        MODULE.transform_surface(values, "robust_scaled_delta_mse"),
        MODULE.transform_surface(values * 7.0, "robust_scaled_delta_mse"),
    )


def test_fractional_rank_is_monotonic_transform_invariant():
    values = np.asarray([4.0, 25.0, 9.0, 16.0])
    assert np.allclose(
        MODULE.transform_surface(values, "fractional_rank"),
        MODULE.transform_surface(np.exp(values), "fractional_rank"),
    )


def test_common_grid_stays_inside_declared_radius():
    grid = MODULE.common_grid()
    assert len(grid) > 4_000
    assert np.max(np.linalg.norm(grid, axis=1)) <= MODULE.GRID_RADIUS_KM + 1e-9
