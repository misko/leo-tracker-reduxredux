"""Exercise measurement replacement on the actual B7 nuisance model."""

import numpy as np
from measurement import clone_measurement_model, shared_starts

from leo.analysis.hard60_slope_prior import SlopePrior
from tests.analysis.test_hard60_joint import setup


def test_real_slope_model_preserves_control_and_nuisance_layout():
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    centers = np.full(len(base.bank.numbers), base.observations.time_center_s)
    model = SlopePrior(base, old.nodes, knots, centers, 0.5)
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = model.initial_clock.copy()
    original = model.evaluate_joint(vector, clock)

    control = clone_measurement_model(model, model.observations.measured_hz)
    candidate = clone_measurement_model(model, model.observations.measured_hz + 100)
    unchanged = control.evaluate_joint(vector, clock)
    changed = candidate.evaluate_joint(vector, clock)
    for before, after in zip(original[:3], unchanged[:3], strict=True):
        # Copying strided design arrays can change BLAS summation roundoff.
        np.testing.assert_allclose(before, after, rtol=0, atol=1e-12)
    assert abs(changed[0] - original[0]) > 1e-6
    for before, after in zip(original[:3], model.evaluate_joint(vector, clock)[:3], strict=True):
        np.testing.assert_array_equal(before, after)
    np.testing.assert_array_equal(candidate.precision, model.precision)
    np.testing.assert_array_equal(candidate.centers_s, model.centers_s)
    np.testing.assert_array_equal(candidate.clock_design, model.clock_design)
    assert candidate.offset_slice == model.offset_slice
    assert candidate.slope_slice == model.slope_slice

    # Satellite nuisance columns precede the two RF-time columns in this model.
    rf_columns = np.arange(len(clock) - 2, len(clock))
    assert model.slope_slice.stop == rf_columns[0]
    clock[model.slope_slice] = 17
    clock[rf_columns] = [23, -31]
    starts = shared_starts(vector, clock, rf_clock_columns=rf_columns)
    for variant in ("original", "logparabola", "newton"):
        zero = starts[(variant, "zero-c")]
        np.testing.assert_array_equal(zero["clock_coefficients"][model.slope_slice], 17)
        np.testing.assert_array_equal(zero["clock_coefficients"][rf_columns], 0)
        assert zero["vector"][6] == 0
