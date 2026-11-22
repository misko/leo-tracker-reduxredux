from collections import Counter
from pathlib import Path
import runpy

import numpy as np
import pytest


RUNNER = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x/solver_grid_cross_arm_audit.py"
AUDIT = runpy.run_path(str(RUNNER))


def test_overlap_uses_all_state_bits_and_preserves_duplicate_row_hits():
    keys, matches = AUDIT["row_keys"], AUDIT["matches"]
    first = keys(np.array([[1., 2., 3.], [+0., 0., 0.]]))
    second = keys(np.array([[1., 2., 3.], [-0., 0., 0.], [1., 2., 3.], [4., 5., 6.]]))
    assert matches([first], second) == 2
    assert matches([keys(np.array([[4., 5., 6.]])), first], second) == 3
    assert matches([], second) == 0
    velocity = np.ones((2, 3))
    point = np.ones((2, 3))
    assert matches([keys(point, velocity)], keys(point, -velocity)) == 0


def test_ceiling_grants_all_observer_work_and_entire_eligible_kernels():
    clock = {
        "curved_c0_observer_cpu_ns": 3_000_000,
        "curved_fitted_c_observer_cpu_ns": 4_000_000,
        "curved_fitted_c_nominal_look_cpu_ns": 6_000_000,
        "curved_fitted_c_plus_look_cpu_ns": 8_000_000,
        "curved_fitted_c_minus_look_cpu_ns": 10_000_000,
        "curved_fitted_c_mode_cpu_ns": 12_000_000,
        "curved_c0_mode_cpu_ns": 14_000_000,
        "curved_fitted_c_geometry_cpu_ns": 60_000_000,
    }
    geometry = {"curved": {
        "nominal": {"position_rows_equal": 1, "state_rows_equal": 0},
        "plus": {"position_rows_equal": 0, "state_rows_equal": 0},
        "minus": {"position_rows_equal": 0, "state_rows_equal": 0},
        "mode_rows_equal": 1,
    }}
    assert AUDIT["ceiling"](clock, geometry) == dict(gross_cpu_s=.025, timed_parts={
        "curved_c0_observer_cpu_ns": 3_000_000,
        "curved_fitted_c_observer_cpu_ns": 4_000_000,
        "curved_fitted_c_nominal_look_cpu_ns": 6_000_000,
        "curved_fitted_c_mode_cpu_ns": 12_000_000,
    })


def test_incomplete_instrumentation_cannot_underestimate_the_ceiling():
    clock = Counter({
        f"curved_{arm}_{kernel}_calls": 12
        for arm in ("c0", "fitted_c")
        for kernel in ("geometry", "nominal_look", "plus_look", "minus_look", "mode")
    })
    validate = AUDIT["validate_clock_coverage"]
    validate(clock, {"curved": {}})
    clock["curved_fitted_c_plus_look_calls"] -= 1
    with pytest.raises(ValueError, match="curved_fitted_c"):
        validate(clock, {"curved": {}})
