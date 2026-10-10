from dataclasses import replace

import numpy as np
import pytest
from compare import compare

from leo.analysis.hard60_slope_prior import SlopePrior
from tests.analysis.test_hard60_joint import setup


def fixture():
    base, old = setup()
    model = SlopePrior(
        base,
        old.nodes,
        old.initial_clock.reshape(2, -1) @ old.null.T,
        np.full(len(base.bank.numbers), base.observations.time_center_s),
        0.5,
    )
    v = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = model.initial_clock.copy()
    endpoints = {}
    for arm in ("fitted-c", "zero-c"):
        vector = v.copy()
        if arm == "zero-c":
            vector[6] = 0
        endpoints[arm] = dict(
            vector=vector,
            clock_coefficients=clock.copy(),
            objective=model.evaluate_joint(vector, clock)[0],
        )
    rows = [
        dict(
            window_id=wid,
            status="complete",
            result=dict(
                parity="passed",
                scorer_kind="original-python-conditioned-scorer",
                original_passed=True,
                baseline_cfo_hz=float(value),
                logparabola_cfo_hz=float(value + 100),
                newton_cfo_hz=float(value + 90),
                changes={
                    "logparabola": dict(circular_hz=100, wrap_count=0),
                    "newton": dict(circular_hz=90, wrap_count=0),
                },
            ),
        )
        for wid, value in zip(
            model.observations.window_ids, model.observations.measured_hz, strict=True
        )
    ]
    return model, {"stages": {"B7": endpoints}}, rows


def test_six_calls_share_starts_and_preserve_failure_without_warm_start():
    model, archive, rows = fixture()
    calls = []

    def fit(candidate, vector, clock, arm):
        calls.append((vector.copy(), clock.copy(), arm, candidate.observations.measured_hz.copy()))
        # A fitter mutating its own seed must not warm-start any other attempt.
        vector[:] = 888
        clock[:] = 999
        if len(calls) == 3:
            raise ValueError("synthetic failed fit")
        return dict(converged=True)

    result = compare(model, archive, rows, fit)
    assert len(calls) == 6 and result["status"] == "attempt-failed"
    assert result["attempts"]["logparabola"]["fitted-c"]["status"] == "failed"
    assert result["attempts"]["newton"]["zero-c"]["qualified"]
    for v, c, arm, _ in calls:
        expected = archive["stages"]["B7"]["fitted-c"]["vector"].copy()
        if arm == "zero-c":
            expected[6] = 0
        np.testing.assert_array_equal(v, expected)
        np.testing.assert_array_equal(c, model.initial_clock)
    for index, change in enumerate((0, 100, 90)):
        for call in calls[2 * index : 2 * index + 2]:
            np.testing.assert_allclose(
                call[3], model.observations.measured_hz + change, atol=1e-8, rtol=0
            )


@pytest.mark.parametrize("fault", ["missing-row", "zero-objective"])
def test_complete_admission_precedes_every_fit(fault):
    model, archive, rows = fixture()
    if fault == "missing-row":
        rows.pop()
    else:
        archive["stages"]["B7"]["zero-c"]["objective"] += 1
    with pytest.raises(ValueError):
        compare(model, archive, rows, lambda *args: pytest.fail("No fits before admission"))


def test_postfit_integrity_failure_retains_all_attempts():
    model, archive, rows = fixture()

    def corrupt_control(*args):
        model.observations = replace(
            model.observations, measured_hz=model.observations.measured_hz + 100
        )
        return dict(converged=True)

    result = compare(model, archive, rows, corrupt_control)
    assert result["status"] == "model-integrity-failed"
    assert result["integrity_failures"]
    assert sum(len(arms) for arms in result["attempts"].values()) == 6
