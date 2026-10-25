"""Numerical oracle for the independent shared-SVD noise-scale audit."""
import numpy as np

from movement_audit import SCALES, score_svd_all_scales


def test_scaled_observation_svd_matches_dense_covariance_with_shared_modes():
    rng = np.random.default_rng(2026102507)
    raw = rng.normal(size=31)*40
    uncertainty = rng.normal(size=(31, 7))*70
    uncertainty[:, -1] = uncertainty[:, 0]*1.000001
    sigma = rng.uniform(2., 90., 31)
    scores = score_svd_all_scales(raw, uncertainty, sigma)
    for scale in SCALES:
        covariance = np.diag((sigma*scale)**2)+uncertainty@uncertainty.T
        quadratic = float(raw@np.linalg.solve(covariance, raw))
        logdet = float(np.linalg.slogdet(covariance)[1])
        np.testing.assert_allclose(scores[str(scale)]['quadratic'], quadratic, rtol=1e-11, atol=1e-9)
        np.testing.assert_allclose(scores[str(scale)]['logdet'], logdet, rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(scores[str(scale)]['negative_twice_log_density'],
            quadratic+logdet+len(raw)*np.log(2*np.pi), rtol=1e-11, atol=1e-9)
