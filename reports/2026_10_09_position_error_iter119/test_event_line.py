import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "event_line119", Path(__file__).with_name("event_line.py")
)
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


def test_nearest_crossing_and_interpolation_knot_are_distinct():
    row = E.horizon_events([0, 1, 2], [-2, -1, 3], 0.5, 1.5)
    # First interpolation knot at alpha1/3, horizon root at alpha1/2.
    assert row["events"] == pytest.approx([0.5], rel=0, abs=1e-15)
    assert E.open_cells(row["events"]) == [(0.0, 0.5), (0.5, 1.0)]


def test_reverse_time_two_events_and_tangent_boundary():
    row = E.horizon_events([0, 1, 2], [-1, 1, -1], 2, -2)
    assert row["events"] == pytest.approx([0.25, 0.75], rel=0, abs=1e-15)
    tangent = E.horizon_events([0, 1, 2], [-1, 0, -1], 0, 2)
    assert tangent["events"] == [0.5]
    assert E.horizon_events([0, 1], [0, 0], 0, 1)["flat_boundary"]


def test_actual_step_can_cross_event_and_improve_unchanged_score():
    event = E.horizon_events([0, 1], [-0.2, 0.8], 0, 1)["events"][0]

    def objective(x):
        return (x - 1) ** 2 + 0.1 * (x >= event)

    assert objective(1) < objective(0)
    assert 2 * (1 - 1) == 0  # Smooth full derivative at the accepted interior point.
    assert objective(event) > objective(np.nextafter(event, 0))


def test_boundary_approach_does_not_qualify_under_unchanged_gradient_gate():
    event = 0.2

    def objective(x):
        return (x - 1) ** 2 + 2 * (x >= event)

    left = event - 10.0 ** (-np.arange(2, 8))
    values = np.array([objective(x) for x in left])
    assert np.all(np.diff(values) < 0)
    assert objective(event) > values[-1]
    assert abs(2 * (left[-1] - 1)) > 1.5  # Never meets0.001, even arbitrarily close.
    # Open left cell has infimum0.64, not an attained minimizer.
    assert values[-1] > 0.64 and abs(values[-1] - 0.64) < 1e-6


def test_end_support_and_nonfinite_fail_explicitly():
    with pytest.raises(ValueError, match="support"):
        E.horizon_events([0, 1], [-1, 1], 0.5, 1)
    with pytest.raises(ValueError, match="finite"):
        E.horizon_events([0, 1], [-1, np.nan], 0, 1)
