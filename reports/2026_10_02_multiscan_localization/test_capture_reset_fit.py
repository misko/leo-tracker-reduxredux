import inspect
from types import SimpleNamespace

import capture_reset_fit as reset
import numpy as np
import pytest


def synthetic_data():
    return SimpleNamespace(
        child_sessions=("first", "second"),
        child_origins_utc_ns=np.array([1_000_000_000_000, 1_100_000_000_000]),
        origin_utc_ns=1_000_000_000_000,
        reference_time_s=200.0,
        numbers=np.array([101, 202, 303]),
        times=np.array([10.0, 110.0, 120.0]),
        capture_index=np.array([0, 1, 1]),
        receiver=np.array([0, 0, 1]),
    )


def child_receipt(session, position, rx0, rx1):
    parameters = np.zeros(9)
    parameters[:2] = position
    parameters[2:6] = [rx0[0], rx0[1], rx1[0], rx1[1]]
    return {
        "unit": {"unit_id": session, "size": 1, "session_ids": [session]},
        "fit": {
            "rough": {"position_km": list(position)},
            "rx_initial": parameters.tolist(),
        },
        "truth_trap": pytest.fail,
    }


def test_child_initializer_uses_unit_clock_zero_gauge_and_common_slopes():
    data = synthetic_data()
    receipts = {
        "first": child_receipt("first", [-4.0, 8.0], (100.0, 2.0), (-50.0, 4.0)),
        "second": child_receipt(
            "second", [6.0, -2.0], (400.0, 6.0), (-100.0, 8.0)
        ),
    }

    initialized = reset.initialize_from_child_fits(data, receipts)

    np.testing.assert_allclose(initialized["child_reference_times_in_unit_s"], [150.0, 250.0])
    np.testing.assert_allclose(initialized["parameters"][:2], [1.0, 3.0])
    np.testing.assert_allclose(initialized["parameters"][2:6], [300.0, 4.0, 250.0, 6.0])
    np.testing.assert_allclose(initialized["capture_jumps_hz"], [[0.0, 0.0], [-100.0, -650.0]])
    assert initialized["gauge"].startswith("capture index zero")


def test_capture_reset_prediction_adds_offsets_with_physical_sign(monkeypatch):
    data = synthetic_data()
    base_prediction = np.array([1.0, 2.0, 3.0])
    visible = np.array([True, True, False])
    jacobian = object()

    def fake_prediction(data_arg, parameters, rows, satellites):
        assert data_arg is data
        return base_prediction.copy(), visible.copy(), jacobian

    monkeypatch.setattr(reset, "paired_prediction_jacobian", fake_prediction)
    jumps = np.array([[0.0, 0.0], [10.0, -20.0]])
    rows = np.array([0, 1, 2])
    satellites = np.array([0, 1, 2])

    prediction, actual_visible, actual_jacobian = reset.paired_capture_reset_prediction(
        data, np.zeros(9), jumps, rows, satellites
    )

    np.testing.assert_allclose(prediction, [1.0, 12.0, -17.0])
    np.testing.assert_array_equal(actual_visible, visible)
    assert actual_jacobian is jacobian


def test_capture_reset_gradient_matches_indicator_finite_difference():
    data = synthetic_data()
    rows = np.array([0, 1, 2])
    weights = np.array([2.0, 3.0, 5.0])
    gradient = reset.capture_reset_gradient(data, rows, weights)
    base = np.zeros((2, 2))

    def objective(jumps):
        return float(weights @ reset.capture_reset_offsets(data, jumps, rows))

    numerical = np.empty_like(base)
    step = 1e-5
    for capture in range(2):
        for receiver in range(2):
            plus = base.copy()
            minus = base.copy()
            plus[capture, receiver] += step
            minus[capture, receiver] -= step
            if capture == 0:
                numerical[capture, receiver] = gradient[capture, receiver]
            else:
                numerical[capture, receiver] = (objective(plus) - objective(minus)) / (2 * step)

    np.testing.assert_allclose(gradient, [[2.0, 0.0], [3.0, 5.0]])
    np.testing.assert_allclose(gradient[1:], numerical[1:], rtol=0.0, atol=1e-10)


def test_alias_equivalent_resets_canonicalize_without_duplicate_alternative():
    alias = reset.DEFAULT_ALIAS_HZ
    jumps = np.array([[99.0, -41.0], [1234.5, -5678.25]])
    alternative = jumps.copy()
    alternative[1] += [alias, -alias]

    canonical = reset.canonicalize_capture_jumps(jumps)
    duplicate = reset.canonicalize_capture_jumps(alternative)

    np.testing.assert_allclose(canonical, duplicate, rtol=0.0, atol=1e-10)
    np.testing.assert_array_equal(canonical[0], np.zeros(2))
    assert reset.canonicalize_capture_jumps([[0.0, 0.0], [alias / 2, 0.0]])[1, 0] == pytest.approx(
        -alias / 2
    )


def test_nonzero_first_capture_gauge_is_rejected():
    data = synthetic_data()
    with pytest.raises(ValueError, match="zero-jump gauge"):
        reset.capture_reset_offsets(data, [[1.0, 0.0], [0.0, 0.0]], [0])


def test_model_penalty_counts_two_parameters_per_later_capture():
    penalty = reset.capture_reset_model_penalty(100, 8, 3)
    assert penalty["extra_parameter_count"] == 4
    assert penalty["baseline_penalty"] == pytest.approx(4 * np.log(100))
    assert penalty["extra_capture_reset_penalty"] == pytest.approx(2 * np.log(100))
    assert penalty["total_penalty"] == pytest.approx(6 * np.log(100))


def test_prototype_has_no_evaluation_or_reference_site_dependency():
    source = inspect.getsource(reset)
    assert "evaluation.json" not in source
    assert "reference_site" not in source
