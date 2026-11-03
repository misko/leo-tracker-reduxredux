from types import SimpleNamespace
import numpy as np
import pytest
from dsx01_joint_marginal import integrated_gaussian
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_shared_carrier_constants import constant_covariance, apply_covariance


def test_shared_clock_covariance_has_physical_RF_scaling_and_separates_families():
    q = np.array([.95, 1.05, 1.])
    c = constant_covariance([7, 7, 9], 11.5e9*q, 'shared30')
    np.testing.assert_allclose(np.diag(c), (300*q)**2 + 30**2)
    assert c[0, 1] == pytest.approx(300**2 * q[0]*q[1])
    assert c[0, 2] == c[1, 2] == 0
    assert np.linalg.eigvalsh(c).min() > 0


def test_old_control_preserves_300Hz_marginals_and_independent_mode_is_identity():
    c = constant_covariance([1, 1, 2], [10.9e9, 12.2e9, 11.1e9], 'old_rho90')
    np.testing.assert_array_equal(np.diag(c), np.full(3, 300**2))
    p = SimpleNamespace(members=[0, 1, 2], constants=np.array([[1000., 0, 0], [0, 1000., 0], [0, 0, 1000.]]))
    original = p.constants.copy()
    apply_covariance(p, constant_covariance([1, 1, 2], [10.9e9, 12.2e9, 11.1e9], 'independent'))
    np.testing.assert_array_equal(p.constants, original)


def test_compact_prior_equals_explicit_shared_carrier_plus_independent_fragment_model():
    rng = np.random.default_rng(62)
    fragment = np.repeat(np.arange(4), 8)
    labels, q = np.array([1, 1, 2, 2]), np.array([.95, 1.05, .95, 1.05])
    covariance = constant_covariance(labels, q*11.5e9, 'shared30')
    p = SimpleNamespace(members=list(range(4)), constants=1000*np.eye(4)[fragment])
    apply_covariance(p, covariance)
    compact = .3*p.constants
    explicit = np.column_stack((np.column_stack([(labels[fragment] == j)*q[fragment]*300 for j in (1, 2)]), 30*np.eye(4)[fragment]))
    np.testing.assert_allclose(compact @ compact.T, explicit @ explicit.T, rtol=1e-12, atol=1e-8)
    raw = rng.normal(size=len(fragment))*70
    a, b = [integrated_gaussian(raw, design, 12) for design in (compact, explicit)]
    np.testing.assert_allclose(a['quadratic']+a['logvolume'], b['quadratic']+b['logvolume'], rtol=1e-10)
    np.testing.assert_allclose(a['conditional_residual_hz'], b['conditional_residual_hz'], atol=1e-8)
    a, b = [hierarchical_bound(raw, design, 12, fragment) for design in (compact, explicit)]
    np.testing.assert_allclose(a['negative_twice_elbo'], b['negative_twice_elbo'], atol=1e-7)
    np.testing.assert_allclose(a['conditional_residual_hz'], b['conditional_residual_hz'], atol=1e-7)


def test_invalid_physical_inputs_and_nonpositive_covariance_fail_closed():
    with pytest.raises(ValueError):
        constant_covariance([1], [-1.], 'shared30')
    with pytest.raises(ValueError):
        constant_covariance([1, 2], [11e9], 'shared30')
    with pytest.raises(ValueError):
        constant_covariance([1], [11e9], 'unknown')
    p = SimpleNamespace(members=[0, 1], constants=np.eye(2))
    with pytest.raises(np.linalg.LinAlgError):
        apply_covariance(p, [[1, 2], [2, 1]])
