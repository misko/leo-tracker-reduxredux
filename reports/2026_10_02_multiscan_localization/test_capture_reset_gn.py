import inspect
from types import SimpleNamespace

import capture_reset_gn as reset_gn
import gauss_newton
import numpy as np
import pytest
from prediction_jacobian import PairedPredictionJacobian
from prediction_plan import ExpandedJacobian


def synthetic_data():
    return SimpleNamespace(
        child_sessions=("first", "second", "third"),
        child_origins_utc_ns=np.array([0, 10_000_000_000, 20_000_000_000]),
        times=np.array([10.0, 20.0, 10.0, 30.0, 20.0]),
        rf=np.full(5, 12.0e9),
        receiver=np.array([0, 0, 1, 1, 0]),
        capture_index=np.array([0, 1, 2, 1, 2]),
    )


def synthetic_expanded_jacobian():
    satellites = np.array([2, 0])
    shared = np.arange(3 * 2 * 6, dtype=float).reshape(6, 6) / 10.0
    tau = np.array([0.5, -1.0, 1.5, 2.0, -0.25, 0.75])
    base = PairedPredictionJacobian(
        shared=shared,
        tau=tau,
        satellites=np.tile(satellites, 3),
        candidate_count=4,
    )
    inverse = np.array([0, 1, 0, 2, 1])
    order = np.argsort(inverse, kind="stable")
    counts = np.bincount(inverse)
    starts = np.r_[0, np.cumsum(counts[:-1])]
    expanded = ExpandedJacobian(base, order, starts, len(inverse), len(satellites))
    plan = SimpleNamespace(
        satellites=satellites,
        unique_rows=np.arange(3),
        inverse=inverse,
    )
    return plan, expanded


def test_capture_indicator_blocks_match_explicit_dense_design():
    data = synthetic_data()
    plan, expanded = synthetic_expanded_jacobian()
    prediction_gradient = np.array(
        [
            [1.0, -2.0],
            [3.0, 4.0],
            [-1.5, 0.25],
            [2.5, -3.5],
            [0.75, 1.25],
        ]
    )
    precision = np.arange(1.0, 11.0).reshape(5, 2) / 3.0

    gradient, hessian, cross = reset_gn.capture_indicator_fisher_terms(
        data, plan, expanded, prediction_gradient, precision
    )

    unique_dense = expanded.base.to_dense().reshape(3, 2, -1)
    base_design = unique_dense[plan.inverse].reshape(10, -1)
    reset_design = np.zeros((10, 4))
    for row, (capture, receiver) in enumerate(zip(data.capture_index, data.receiver, strict=True)):
        if capture:
            reset_design[2 * row : 2 * row + 2, 2 * (capture - 1) + receiver] = 1.0
    flat_gradient = prediction_gradient.ravel()
    flat_precision = precision.ravel()
    expected_gradient = -(reset_design.T @ flat_gradient)
    expected_hessian = reset_design.T @ (flat_precision[:, None] * reset_design)
    expected_cross = base_design.T @ (flat_precision[:, None] * reset_design)

    np.testing.assert_allclose(gradient, expected_gradient, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(hessian, expected_hessian, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(cross, expected_cross, rtol=0.0, atol=1e-12)


def test_capture_offsets_use_original_rows_after_prediction_reuse():
    data = synthetic_data()
    prediction = np.zeros((5, 2))
    jumps = np.array([[0.0, 0.0], [100.0, 200.0], [300.0, 400.0]])

    actual = reset_gn.apply_capture_offsets(data, prediction, jumps, 2)

    np.testing.assert_array_equal(
        actual,
        np.array(
            [
                [0.0, 0.0],
                [100.0, 100.0],
                [400.0, 400.0],
                [200.0, 200.0],
                [300.0, 300.0],
            ]
        ),
    )


def test_reset_gn_uses_exact_gnv2_projection_and_stationarity_helpers():
    assert reset_gn._project is gauss_newton._project
    assert reset_gn._projected_gradient is gauss_newton._projected_gradient
    assert reset_gn._free_variables is gauss_newton._free_variables
    assert reset_gn._newton_stationarity is gauss_newton._newton_stationarity


@pytest.mark.parametrize(
    "reason",
    [
        "budget_exhausted",
        "iteration_limit",
        "no_acceptable_step",
        "nonfinite_step",
        "singular_curvature",
        "tiny_accepted_step_without_gradient_convergence",
    ],
)
def test_largest_fallback_accepts_only_declared_numerical_failures(reason):
    assert reset_gn.numerical_failure_allows_fallback(
        {"success": False, "convergence_reason": reason}
    )
    assert not reset_gn.numerical_failure_allows_fallback(
        {"success": True, "convergence_reason": reason}
    )


@pytest.mark.parametrize(
    "reason",
    [
        "evaluation_error:ValueError:bad shape",
        "final_evaluation_failed_after_convergence",
        "observation_timeout",
        "implementation_error",
    ],
)
def test_largest_fallback_rejects_errors_and_observation_timeout(reason):
    assert not reset_gn.numerical_failure_allows_fallback(
        {"success": False, "convergence_reason": reason}
    )


def test_fresh_bank_starts_are_independent_and_never_cross_seeded():
    initialized = {
        "parameters": np.arange(12.0),
        "capture_jumps_hz": np.array([[0.0, 0.0], [10.0, -20.0]]),
    }
    starts = reset_gn.independent_fresh_bank_starts(initialized, 3)

    starts[0][0][0] = 999.0
    starts[1][1][1, 0] = 888.0

    assert starts[1][0][0] == 0.0
    assert starts[2][0][0] == 0.0
    assert starts[0][1][1, 0] == 10.0
    assert starts[2][1][1, 0] == 10.0


def test_largest_fallback_remains_same_bank_and_chains_only_its_attempts():
    calls = []

    def fake_refiner(
        data,
        parameters,
        jumps,
        satellites,
        support,
        likelihood,
        *,
        sigma_hz,
        budget_s,
    ):
        calls.append(
            {
                "parameters": np.asarray(parameters).copy(),
                "jumps": np.asarray(jumps).copy(),
                "satellites": np.asarray(satellites).copy(),
                "support": np.asarray(support).copy(),
                "sigma_hz": sigma_hz,
                "budget_s": budget_s,
            }
        )
        return {
            "parameters": np.asarray(parameters) + 1.0,
            "capture_jumps_hz": np.asarray(jumps) + [[0.0, 0.0], [1.0, 1.0]],
            "success": True,
            "convergence_reason": "projected_gradient",
            "objective": float(sigma_hz),
        }

    direct = {
        "parameters": np.arange(10.0),
        "capture_jumps_hz": np.array([[0.0, 0.0], [12.0, -34.0]]),
        "success": False,
        "convergence_reason": "budget_exhausted",
    }
    satellites = np.array([4, 1, 7])
    attempts = reset_gn.refine_largest_same_bank_fallback(
        fake_refiner,
        object(),
        direct,
        satellites,
        np.array([3.0, 2.0, 1.0]),
        object(),
    )

    assert [call["sigma_hz"] for call in calls] == [2000.0, 1000.0, 500.0, 200.0]
    assert [call["budget_s"] for call in calls] == [5.0, 5.0, 5.0, 20.0]
    for call in calls:
        np.testing.assert_array_equal(call["satellites"], satellites)
    np.testing.assert_array_equal(calls[0]["parameters"], direct["parameters"])
    for prior, following in zip(attempts[:-1], calls[1:], strict=True):
        np.testing.assert_array_equal(following["parameters"], prior["parameters"])


def test_reset_gn_has_no_evaluation_or_reference_dependency():
    source = inspect.getsource(reset_gn)
    assert "evaluation.json" not in source
    assert "reference_site" not in source
    assert "reference_locations" not in source
