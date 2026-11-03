import numpy as np

from ds23_common_receiver_clock import fit, predict
from audit_ds23_common_receiver_clock import component_NLL


def test_component_marginals_sum_to_joint_density_for_diagonal_covariance():
    rng = np.random.default_rng(41)
    t = np.arange(20)/750
    a = rng.normal(size=(20, 2))+1j*rng.normal(size=(20, 2))
    b = a*np.exp(2j*np.pi*t[:, None]*np.array([20., 30.]))+.1*(rng.normal(size=(20, 2))+1j*rng.normal(size=(20, 2)))
    covariance = np.tile(np.eye(2)*.02, (len(t), 1, 1))
    model = fit(t[:12], a[:12], b[:12], covariance[:12], covariance[:12], np.array([2000., 1990.]))
    parts = component_NLL(model, t[12:], a[12:], b[12:], covariance[12:], covariance[12:])
    joint = predict(model, t[12:], a[12:], b[12:], covariance[12:], covariance[12:])
    np.testing.assert_allclose(parts.sum(), joint, atol=1e-9)
