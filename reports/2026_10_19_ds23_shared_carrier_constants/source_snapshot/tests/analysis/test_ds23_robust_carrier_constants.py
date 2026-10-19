import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_robust_carrier_constants import bias_columns
from probe_ds23_shared_carrier_constants import constant_covariance
from ds23_robust_carrier_prior import prior_groups


def test_explicit_bias_columns_have_the_same_prior_covariance_as_compact_model():
    labels = np.array([0, 0, 1, 1])
    q = np.array([.95, 1.05, .95, 1.05])
    common, individual = bias_columns(labels, q, np.arange(4), 2, 4, 30)
    features = np.column_stack((common, individual))
    np.testing.assert_allclose(features@features.T, constant_covariance(labels, q*11.5e9, 'shared30'))


def test_heavy_fragment_prior_admits_one_large_deviation_without_shifting_the_shared_carrier():
    fragment = np.repeat(np.arange(3), 24)
    common, individual = bias_columns(np.zeros(72, int), np.ones(72), fragment, 1, 3, 30)
    features = np.column_stack((common, individual))
    y = np.repeat([300., 300., 900.], 24)
    result = hierarchical_bound(y, features, 10, fragment, prior_groups=np.array([-1, 0, 1, 2]), prior_nu=3.)
    assert abs(result['coefficient'][0]*300-300) < 20
    assert np.max(abs(result['coefficient'][1:3]*30)) < 20
    assert result['coefficient'][3]*30 > 500
    assert result['coefficient_prior_precision'][3] < min(result['coefficient_prior_precision'][1:3])*.1
    assert np.sqrt(np.mean(result['conditional_residual_hz']**2)) < 3


def test_unobserved_independent_contrast_does_not_add_artificial_evidence_penalty():
    y = np.linspace(-10, 10, 12)
    features = np.column_stack((np.full(12, 300.), np.full(12, 30.), np.zeros(12)))
    groups = prior_groups(3, 0, 0, [True, False], None)
    actual = hierarchical_bound(y, features, 20, np.zeros(12, int), prior_groups=groups, prior_nu=3.)
    collapsed = hierarchical_bound(y, features[:, :2], 20, np.zeros(12, int), prior_groups=groups[:2], prior_nu=3.)
    np.testing.assert_allclose(actual['negative_twice_elbo'], collapsed['negative_twice_elbo'], atol=1e-10)
    np.testing.assert_allclose(actual['conditional_residual_hz'], collapsed['conditional_residual_hz'], atol=1e-10)
