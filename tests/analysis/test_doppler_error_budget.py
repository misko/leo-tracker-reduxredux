"""Nuisance profiling must not leak evaluation observations or invent information."""

import numpy as np
import pytest

from leo.analysis.research.doppler_error_budget import information, profile, profile_shared_drift


def test_offsets_use_training_only_and_support_matrix_jacobians():
    group = np.array([0, 0, 0, 1, 1, 1])
    train = np.array([True, True, False] * 2)
    y = np.array([10.0, 12.0, 1000.0, 20.0, 24.0, -1000.0])
    got = profile(y, group, train)
    np.testing.assert_allclose(got, [-1, 1, 989, -2, 2, -1022])
    np.testing.assert_allclose(
        profile(np.column_stack([y, 2 * y]), group, train), np.column_stack([got, 2 * got])
    )


def test_drift_is_fitted_on_training_only():
    t = np.arange(6.0)
    train = np.array([True, False, True, False, True, False])
    y = 80 + 3 * t
    y[~train] += 17
    r = profile(y, np.zeros(6, int), train, time=t)
    np.testing.assert_allclose(r[train], 0, atol=1e-12)
    np.testing.assert_allclose(r[~train], 17, atol=1e-12)


def test_unobservable_position_returns_no_finite_bound():
    out = information(np.ones((20, 2)), 10)
    assert out["rank"] == 1
    assert out["covariance_m2"] is None


def test_information_scales_with_noise_and_replication():
    j = np.tile(np.eye(2), (10, 1))  # Hz/km
    a = information(j, 1)
    b = information(np.tile(j, (4, 1)), 2)
    np.testing.assert_allclose(a["covariance_m2"], b["covariance_m2"])
    assert a["rank"] == 2


def test_group_without_training_is_rejected():
    with pytest.raises(ValueError, match="training"):
        profile(np.arange(4.0), np.array([0, 0, 1, 1]), np.array([True, True, False, False]))


def test_common_receiver_drift_preserves_distinct_offsets_and_evaluation():
    t = np.arange(12.0)
    g = np.repeat(np.arange(4), 3)
    session = g // 2
    train = np.tile([True, False, True], 4)
    y = 100 * g + (session + 1) * t
    y[~train] += 99
    r = profile_shared_drift(y, g, session, train, t)
    np.testing.assert_allclose(r[train], 0, atol=1e-10)
    np.testing.assert_allclose(r[~train], 99, atol=1e-10)
