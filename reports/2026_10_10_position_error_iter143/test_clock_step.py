import numpy as np
import pytest
from clock_step import step

from leo.analysis.hard60_slope_prior import SlopePrior
from tests.analysis.test_hard60_joint import setup


def fixture(arm):
    base, old = setup()
    model = SlopePrior(
        base,
        old.nodes,
        old.initial_clock.reshape(2, -1) @ old.null.T,
        np.full(len(base.bank.numbers), base.observations.time_center_s),
        0.5,
    )
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    if arm == "zero-c":
        vector[6] = 0
    clock = model.initial_clock.copy()
    clock[:model.smooth_clock_count] += 20
    clock[model.slope_slice] = np.arange(model.slope_slice.stop - model.slope_slice.start) + 1
    return model, vector, clock


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_real_b7_block_refresh_and_locks(arm):
    model, vector, clock = fixture(arm)
    originals = vector.copy(), clock.copy()
    result = step(model, vector, clock, arm)
    assert result["accepted"] and result["exact_evaluations"] == 2
    assert result["objective_after"] < result["objective_before"]
    np.testing.assert_array_equal(vector, originals[0])
    np.testing.assert_array_equal(clock, originals[1])
    np.testing.assert_array_equal(result["vector"], vector)
    np.testing.assert_array_equal(
        result["clock_coefficients"][model.slope_slice], clock[model.slope_slice]
    )
    if arm == "zero-c":
        assert np.all(result["clock_coefficients"][-2:] == 0)
    refreshed = model.evaluate_joint(vector, result["clock_coefficients"])[0]
    assert refreshed == result["objective_after"]


@pytest.mark.parametrize("fault", ["increase", "nonfinite", "exception"])
def test_refresh_failure_retains_exact_original_state(fault):
    model, vector, clock = fixture("fitted-c")
    original = model.evaluate_joint
    calls = []

    def evaluate(v, c):
        value = original(v, c)
        calls.append(value[0])
        if len(calls) == 2:
            if fault == "exception":
                raise ValueError("synthetic refresh failure")
            return (float("nan") if fault == "nonfinite" else calls[0] + 1, *value[1:])
        return value

    model.evaluate_joint = evaluate
    result = step(model, vector, clock, "fitted-c")
    assert not result["accepted"] and len(calls) == 2
    np.testing.assert_array_equal(result["clock_coefficients"], clock)
    assert result["objective_after"] == result["objective_before"]


def test_zero_c_invalid_start_rejected_before_evaluation():
    model, vector, clock = fixture("fitted-c")
    model.evaluate_joint = lambda *args: pytest.fail("No evaluation on invalid c0 start")
    with pytest.raises(ValueError, match="RF locks"):
        step(model, vector, clock, "zero-c")
