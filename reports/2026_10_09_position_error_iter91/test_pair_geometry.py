"""Synthetic geometry limits of a fixed antisymmetric receiver correction.

No recording, orbit model, optimizer, or reference-location data is accessed.
These identities concern known assignments and unwrapped Gaussian residuals;
they do not claim invariance for the full clutter/association mixture.
"""

import numpy as np


def gaussian_value_gradient(measured, prediction, jacobian, variance):
    residual = np.asarray(measured) - np.asarray(prediction)
    variance = np.broadcast_to(variance, residual.shape)
    return 0.5 * np.sum(residual**2 / variance), -(jacobian.T @ (residual / variance))


def test_balanced_pairs_preserve_common_spatial_gradient():
    rng = np.random.default_rng(9101)
    geometric = rng.normal(size=12)
    jacobian = rng.normal(size=(12, 2))
    measured = rng.normal(size=(12, 2))
    contrast = rng.normal(size=12)
    variance = np.repeat(rng.uniform(1, 4, size=12), 2)
    prediction = np.repeat(geometric, 2)
    derivative = np.repeat(jacobian, 2, axis=0)
    correction = np.column_stack([-contrast / 2, contrast / 2]).ravel()
    before = gaussian_value_gradient(measured.ravel(), prediction, derivative, variance)
    after = gaussian_value_gradient(measured.ravel(), prediction + correction, derivative, variance)
    np.testing.assert_allclose(after[1], before[1], atol=1e-13)
    common = measured.mean(axis=1) - geometric
    differential = measured[:, 1] - measured[:, 0] - contrast
    expected = np.sum((common**2 + differential**2 / 4) / variance[::2])
    np.testing.assert_allclose(after[0], expected, atol=1e-13)


def test_unequal_support_can_make_a_correct_contrast_change_spatial_gradient():
    # Two RX0 observations and one RX1: an injected differential bias no longer
    # cancels from the common-position score. There is no optimizer in this test.
    sign = np.array([-1.0, -1.0, 1.0])
    jacobian = np.tile([2.0, -3.0], (3, 1))
    prediction_at_truth = np.full(3, 8.0)
    correction = sign * 4.0 / 2
    measured = prediction_at_truth + correction
    before = gaussian_value_gradient(measured, prediction_at_truth, jacobian, 1.0)
    after = gaussian_value_gradient(measured, prediction_at_truth + correction, jacobian, 1.0)
    assert np.linalg.norm(before[1]) > 0
    np.testing.assert_array_equal(after[1], [0, 0])
    # A misspecified contrast on unbiased measurements produces a harmful
    # nonzero spatial gradient by exactly the same coupling mechanism.
    wrong = gaussian_value_gradient(
        prediction_at_truth, prediction_at_truth + correction, jacobian, 1.0
    )
    np.testing.assert_allclose(wrong[1], -before[1])


def test_equal_counts_with_unequal_receiver_variances_are_not_balanced():
    measured = np.array([2.0, 2.0])
    prediction = np.array([2.0, 2.0])
    derivative = np.ones((2, 1))
    variance = np.array([1.0, 4.0])
    before = gaussian_value_gradient(measured, prediction, derivative, variance)
    after = gaussian_value_gradient(measured, prediction + [-1, 1], derivative, variance)
    np.testing.assert_array_equal(before[1], [0])
    np.testing.assert_allclose(after[1], [-0.75])


def test_distinct_receiver_geometry_prevents_exact_doppler_cancellation():
    # g0(p)=p, g1(p)=2p represents different receiver geometry. Their difference
    # depends on p, so an antisymmetric correction can change its spatial score.
    position = 3.0
    derivative = np.array([[1.0], [2.0]])
    prediction = derivative[:, 0] * position
    measured = prediction.copy()
    before = gaussian_value_gradient(measured, prediction, derivative, 1.0)
    after = gaussian_value_gradient(measured, prediction + [-1, 1], derivative, 1.0)
    assert prediction[1] - prediction[0] == position
    np.testing.assert_array_equal(before[1], [0])
    np.testing.assert_allclose(after[1], [1])
