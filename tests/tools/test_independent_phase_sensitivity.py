import numpy as np

from tools.research.audit_independent_phase_sensitivity import (
    maximum_phase_rms,
    provisional_baseline,
    remove_polynomial,
)


def test_local_nuisance_removes_only_declared_polynomial():
    times = np.linspace(90, 90.12, 24)
    tau = times - times.mean()
    values = np.column_stack([2 + 3 * tau, 4 * tau**2, 5 * tau**3])
    linear = remove_polynomial(values, times, 1)
    assert np.max(np.abs(linear[:, 0])) < 1e-12
    assert np.linalg.norm(linear[:, 1]) > 1e-3
    quadratic = remove_polynomial(values, times, 2)
    assert np.max(np.abs(quadratic[:, :2])) < 1e-12
    assert np.linalg.norm(quadratic[:, 2]) > 1e-5


def test_orientation_upper_bound_is_attained_and_rotation_invariant():
    residual = np.random.default_rng(9).normal(size=(24, 3))
    _, _, vectors = np.linalg.svd(residual, full_matrices=False)
    actual = np.sqrt(np.mean((20 * residual @ (0.08 * vectors[0])) ** 2))
    np.testing.assert_allclose(maximum_phase_rms(residual, 20), actual)
    q, _ = np.linalg.qr(np.random.default_rng(10).normal(size=(3, 3)))
    np.testing.assert_allclose(maximum_phase_rms(residual @ q, 20), actual)


def test_hypothetical_baseline_is_horizontal_and_eight_cm():
    baseline = provisional_baseline({"latitude_deg": 0.0, "longitude_deg": 0.0})
    np.testing.assert_allclose(np.linalg.norm(baseline), 0.08)
    np.testing.assert_allclose(baseline[0], 0.0, atol=1e-14)
