"""Actual coarse KKT constraints on synthetic metadata; no orbit/model calls."""

from types import SimpleNamespace

import numpy as np

from leo.analysis.hard60_bounded_fit import _Problem


def fixture():
    model = SimpleNamespace(
        size=9,
        prior=SimpleNamespace(radius_km=100.0),
        bank=SimpleNamespace(numbers=[1, 2], nodes_s=np.array([-100.0, 100.0])),
        observations=SimpleNamespace(times_s=np.array([0.0, 1.0])),
        basis=np.array([[1.0], [-1.0]]) / np.sqrt(2),
    )
    vector = np.zeros(9)
    vector[:2] = [1.0, 2.0]
    return model, vector


def test_actual_zero_and_fixed_locks_change_only_intended_kkt_coordinates():
    model, vector = fixture()
    zero = _Problem(model, vector, fixed_position=True, rf_arm="zero-c")
    fitted = _Problem(model, vector, fixed_position=True, rf_arm="fitted-c")
    gradient = np.zeros(9)
    gradient[:2] = [100.0, -100.0]
    gradient[6] = 0.01
    assert zero.stationarity(vector, gradient) == 0.0
    assert fitted.stationarity(vector, gradient) == 2.0
    assert set(fitted.free) - set(zero.free) == {6}
    assert not set(zero.free) & {0, 1, 6}
    changed = vector.copy()
    changed[6] = 1.0
    assert not zero.feasible(changed)
    assert fitted.feasible(changed)
    changed = vector.copy()
    changed[0] += 0.1
    assert not fitted.feasible(changed)


def test_actual_slope_common_and_coupled_timing_bounds_audit_original_state():
    model, vector = fixture()
    problem = _Problem(model, vector, fixed_position=True, rf_arm="fitted-c")
    for index, value in [(3, 60.01), (5, -60.01), (7, 10.01), (6, 5000.01)]:
        changed = vector.copy()
        changed[index] = value
        assert not problem.feasible(changed)
    changed = vector.copy()
    changed[7] = 10.0
    changed[8] = 15.0
    assert np.max(problem.matrix @ changed) > 20.0
    assert not problem.feasible(changed)
    # Constructor may project its private start; the audit must use the saved vector.
    projected = _Problem(model, changed, fixed_position=True, rf_arm="fitted-c")
    assert projected.feasible(projected.start)
    assert not projected.feasible(changed)
