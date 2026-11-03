import numpy as np
import pytest
from prediction_jacobian import paired_prediction_jacobian
from prediction_plan import SharedPredictionPlan
from test_staged_gradient import synthetic_orbital_data


def test_repeated_alternatives_preserve_predictions_and_full_gradient():
    data, parameters = synthetic_orbital_data()
    indices = np.array([2, 0, 1, 2, 3, 0, 2])
    for name in ("times", "rf", "receiver", "group", "measured", "channel", "margin"):
        setattr(data, name, getattr(data, name)[indices])
    satellites = np.array([2, 0])
    rows = np.repeat(np.arange(len(indices)), 2)
    paired_satellites = np.tile(satellites, len(indices))
    expected, visible, jacobian = paired_prediction_jacobian(
        data, parameters, rows, paired_satellites
    )
    plan = SharedPredictionPlan(data, satellites)
    actual, actual_visible, actual_jacobian = plan.predict(parameters)
    assert len(plan.unique_rows) == 4
    assert len(actual) == len(indices) * len(satellites)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual_visible, visible)
    weights = np.random.default_rng(123).normal(size=len(actual))
    np.testing.assert_allclose(
        actual_jacobian.transpose_multiply(weights),
        jacobian.transpose_multiply(weights),
        rtol=1e-12,
        atol=1e-9,
    )
    precision = weights**2
    dense = jacobian.to_dense()
    expected_normal = dense.T @ (precision[:, None] * dense)
    np.testing.assert_allclose(
        jacobian.normal_matrix(precision), expected_normal, rtol=1e-12, atol=1e-7
    )
    np.testing.assert_allclose(
        actual_jacobian.normal_matrix(precision), expected_normal, rtol=1e-12, atol=1e-7
    )
    with pytest.raises(ValueError, match="nonnegative"):
        actual_jacobian.normal_matrix(-precision)
    with pytest.raises(ValueError, match="expanded paired"):
        actual_jacobian.transpose_multiply(weights[:-1])


def test_prediction_reuse_does_not_require_or_merge_source_groups():
    data, parameters = synthetic_orbital_data()
    data.times[:] = data.times[0]
    data.rf[:] = data.rf[0]
    data.receiver[:] = 0
    data.group = np.arange(4)
    plan = SharedPredictionPlan(data, [0])
    predicted, _, _ = plan.predict(parameters)
    assert len(plan.unique_rows) == 1
    assert len(predicted) == 4
    np.testing.assert_array_equal(data.group, np.arange(4))
