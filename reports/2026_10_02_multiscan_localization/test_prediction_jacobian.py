import importlib.util
from pathlib import Path

import numpy as np
from joint_inputs import JointData, observation_nodes
from prediction_jacobian import paired_prediction_jacobian


def synthetic_joint_data():
    times = np.array([0.37, 2.13, 4.81])
    nodes = observation_nodes(times)
    numbers = np.array([101, 202, 303], dtype=np.int64)
    position = np.empty((len(numbers), len(nodes), 3))
    velocity = np.empty_like(position)
    for satellite in range(len(numbers)):
        position[satellite, :, 0] = 7000.0 + 20 * satellite + 0.2 * nodes
        position[satellite, :, 1] = 500.0 - 5 * satellite + 1.3 * nodes
        position[satellite, :, 2] = 300.0 + satellite - 0.4 * nodes
        velocity[satellite, :, 0] = 0.1 + 0.001 * nodes
        velocity[satellite, :, 1] = 7.0 - 0.002 * nodes
        velocity[satellite, :, 2] = -0.2 + 0.0005 * nodes
    arrays = {
        "times": times,
        "measured": np.zeros(len(times)),
        "rf": np.array([11.0e9, 11.2e9, 11.4e9]),
        "receiver": np.array([0, 1, 0], dtype=np.int64),
        "channel": np.ones(len(times), dtype=np.int64),
        "group": np.arange(len(times), dtype=np.int64),
        "margin": np.ones(len(times)),
    }
    return JointData(
        dataset="synthetic",
        unit_id="synthetic-unit",
        child_sessions=("synthetic-child",),
        child_origins_utc_ns=np.array([1_000_000_000_000], dtype=np.int64),
        origin_utc_ns=1_000_000_000_000,
        reference_time_s=2.59,
        snapshot={"provider": "synthetic", "collected_utc_ns": 1, "digest": "synthetic"},
        arrays=arrays,
        nodes=nodes,
        numbers=numbers,
        position=position,
        velocity=velocity,
        initial=np.zeros(6 + len(numbers)),
        tracks=[],
        capture_index=np.zeros(len(times), dtype=np.int64),
        provenance={"reference_truth_read": False},
    )


def finite_difference(data, parameters, rows, satellites, location_step=1e-3):
    output = np.empty((rows.size, len(parameters)))
    for index in range(len(parameters)):
        step = location_step if index < 2 else 1e-5
        plus = parameters.copy()
        minus = parameters.copy()
        plus[index] += step
        minus[index] -= step
        plus_prediction, _ = data.predict(plus, rows, satellites)
        minus_prediction, _ = data.predict(minus, rows, satellites)
        output[:, index] = (plus_prediction - minus_prediction) / (2 * step)
    return output


def test_synthetic_prediction_and_all_parameter_jacobian_match_finite_difference():
    data = synthetic_joint_data()
    parameters = np.array([4.0, -3.0, 120.0, 0.7, -80.0, -0.4, 0.07, -0.11, 0.13])
    rows = np.array([0, 1, 2, 0, 1, 2])
    satellites = np.array([0, 1, 2, 2, 0, 1])

    prediction, visible, jacobian = paired_prediction_jacobian(data, parameters, rows, satellites)
    expected_prediction, expected_visible = data.predict(parameters, rows, satellites)
    numerical = finite_difference(data, parameters, rows, satellites)

    np.testing.assert_allclose(prediction, expected_prediction, rtol=0.0, atol=1e-10)
    np.testing.assert_array_equal(visible, expected_visible)
    np.testing.assert_allclose(jacobian.to_dense(), numerical, rtol=2e-5, atol=2e-5)

    weights = np.linspace(-1.0, 1.0, len(rows))
    np.testing.assert_allclose(
        jacobian.transpose_multiply(weights),
        weights @ jacobian.to_dense(),
        rtol=0.0,
        atol=1e-12,
    )


def load_old_bundle_module():
    reports_root = Path(__file__).resolve().parent.parent
    path = reports_root / "2026_10_02_localization_benchmark" / "bundle.py"
    spec = importlib.util.spec_from_file_location("jacobian_real_ds10_old_bundle", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load old bundle adapter from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_ds10_single_prediction_and_all_parameters_match_finite_difference():
    root = Path(__file__).resolve().parent
    directory = root / "scans" / "scan-fw-df44e74320bd2718"
    data = load_old_bundle_module().Data(directory)
    assert not hasattr(data, "reference_time_s")
    parameters = data.initial.copy()
    parameters[6:] += np.linspace(-0.08, 0.08, len(data.numbers))
    rows = np.linspace(0, len(data.times) - 1, 128, dtype=int)
    satellites = np.arange(len(rows), dtype=int) % len(data.numbers)

    prediction, visible, jacobian = paired_prediction_jacobian(data, parameters, rows, satellites)
    expected_prediction, expected_visible = data.predict(parameters, rows, satellites)
    numerical = finite_difference(data, parameters, rows, satellites)

    np.testing.assert_allclose(prediction, expected_prediction, rtol=0.0, atol=1e-10)
    np.testing.assert_array_equal(visible, expected_visible)
    np.testing.assert_allclose(jacobian.to_dense(), numerical, rtol=5e-5, atol=5e-5)
