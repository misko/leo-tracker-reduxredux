"""Verify the centered projected check and its evaluation receipt."""

import numpy as np
import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.variants import v5_armijo_fit as coarse
from tools.pipeline_eval.variants.v5_armijo_tail import CHECK_KM, _stage, bounded_armijo_tail


def solve(residual, initial, lower=(-2.0, -2.0), upper=(2.0, 2.0)):
    points = []

    def observed(x):
        assert np.all((lower <= x) & (x <= upper))
        points.append(x.copy())
        return residual(x)

    fit = bounded_armijo_tail(observed, initial, lower, upper, iterations=48)
    assert fit["evaluations"] == len(points)
    np.testing.assert_array_equal(fit["history"][-1]["parameters"], fit["parameters"])
    assert fit["score"] == pytest.approx(np.sum(residual(fit["parameters"]) ** 2))
    scores = [trial["score"] for trial in fit["history"]]
    assert all(a > b for a, b in zip(scores, scores[1:], strict=False))
    return fit, points


def test_centered_check_finishes_a_sub_twenty_meter_fit():
    target = np.array([0.011, -0.007])

    def residual(x):
        return x - target

    earlier = coarse.bounded_armijo(residual, [0.0, 0.0], [-2, -2], [2, 2])
    checked, _ = solve(residual, [0.0, 0.0])
    np.testing.assert_array_equal(earlier["parameters"], [0.0, 0.0])
    np.testing.assert_allclose(checked["parameters"], target, atol=CHECK_KM)
    assert checked["stopped"] == "centered_small_step"


def test_centered_check_cannot_revisit_a_rejected_point():
    def residual(x):
        return np.array([1.0 - x[0] if abs(x[0]) <= 0.001 else 2.0, 5.0])

    # The local slope proposes a rejected large step in the coarse phase.
    rejected, points = solve(residual, [0.0, 0.0])
    assert rejected["stopped"] == "no_accepted_armijo_step"
    assert len({tuple(p) for p in points[3:]}) == coarse.TRIALS

    def below_twenty_meters(x):
        return np.array([0.015 - x[0] if abs(x[0]) <= 0.001 else 2.0, x[1]])

    refined, points = solve(below_twenty_meters, [0.0, 0.0])
    rejected_steps = [p[0] for p in points[8:12]]
    assert refined["rejected_trials"] == 4
    assert all(a > b > 0 for a, b in zip(rejected_steps, rejected_steps[1:], strict=False))
    assert len(set(rejected_steps)) == 4


@pytest.mark.parametrize("weak_axis", [0.0, 1e-11])
def test_centered_bound_and_degenerate_direction(weak_axis):
    def residual(x):
        return np.array([x[0] - 2.2, weak_axis * (x[1] - 1.0)])

    checked, _ = solve(residual, [1.99, 0.5])
    np.testing.assert_allclose(checked["parameters"], [2.0, 0.5], atol=1e-7)
    assert checked["stopped"] == "centered_small_step"


def test_curved_regression_keeps_contracting_and_reaches_either_axis_minimum():
    def residual(x):
        return np.array([x[0] ** 2 - 1.0, x[1]])

    checked, points = solve(residual, [0.4, 0.0])
    rejected = points[3]
    assert sum(np.array_equal(p, rejected) for p in points) == 1
    np.testing.assert_allclose(points[4] - [0.4, 0.0], (rejected - [0.4, 0.0]) / 2)
    np.testing.assert_allclose(checked["parameters"], [1.0, 0.0], atol=CHECK_KM)


def test_stage_trace_binds_component_identity_mask_aliases_and_gate():
    sources = [
        dict(component="SCAN-RX1-CH1-T001", candidate_index=np.int64(23),
             active_curvature=np.bool_(True))
    ]
    node = dict(seed={"rows": sources}, aliases=[np.int64(-1)])
    base = dict(node=node, keep=np.array([True, False]), accepted=np.bool_(True))
    entry = dict(component="SCAN-RX0-CH2-T001", candidate_index=np.int64(23),
                 alias=np.int64(2), points=np.int64(17))
    trace = _stage(
        "history_policy", dict(base, entries=[entry], linear_paired_valid=np.bool_(False))
    )
    assert trace["assignments"] == dict(tracks=[["SCAN-RX1-CH1-T001", 23, True]], aliases=[-1])
    assert trace["linear_entries"] == [["SCAN-RX0-CH2-T001", 23, 2, 17]]
    changed = _stage("history_policy", dict(base, keep=np.array([False, True])))
    assert trace["mask"]["retained"] == changed["mask"]["retained"] == 1
    assert trace["mask"]["sha256"] != changed["mask"]["sha256"]
    encoded(trace)
