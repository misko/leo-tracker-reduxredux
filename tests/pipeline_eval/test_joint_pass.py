import numpy as np
import pytest

from tools.pipeline_eval.variants import joint_pass as fit


def test_free_offset_cancels_and_held_samples_cannot_refit_clock_or_phase():
    t = np.linspace(0, 21, 16)
    h = np.array([90 * np.cos(t / 3), -160 * np.sin(t / 7)])
    shape = 30 * t + 2 * h
    a, phase, drift = fit.profile(shape, h, t, 10, independent=True)
    copy = shape + 5678
    copy[:, 10:] += 3000
    b, late, late_rate = fit.profile(copy, h, t, 10, independent=True)
    np.testing.assert_allclose(phase, late)
    np.testing.assert_allclose(drift, late_rate)
    np.testing.assert_allclose(a[:, :10], b[:, :10], atol=1e-9)
    np.testing.assert_allclose(a[:, 10:] + 3000, b[:, 10:], atol=1e-9)


def test_clock_schur_complement_detects_a_spatial_direction_absorbed_by_nuisance():
    H = np.array([[9.0, 0.0, 2.0], [0.0, 16.0, 0.0], [2.0, 0.0, 1.0]])
    retained, radius = fit.condition(H, 5)
    assert retained == pytest.approx(np.sqrt(5 / 9))
    assert radius == pytest.approx(56)
    H[0, 2] = H[2, 0] = 3
    assert fit.condition(H, 5) == (0, None)


def test_soft_orbit_mixture_protects_background_and_rejects_equal_identity_ties():
    tied, _ = fit.posterior(np.array([0.2, 0.2]))
    open_set, _ = fit.posterior(np.array([50.0, 40.0]))
    distinct, _ = fit.posterior(np.array([0.05, 7.0]))
    assert tied.max() < 0.55
    assert open_set.sum() < 1e-6
    assert distinct.max() > 0.99
