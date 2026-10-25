"""Independent observation-space Gaussian identities; no inference components."""
import numpy as np


def dense_nll(raw, covariance):
    raw, covariance = np.asarray(raw, float), np.asarray(covariance, float)
    root = np.linalg.cholesky(covariance)
    white = np.linalg.solve(root, raw)
    quadratic = float(white @ white)
    logdet = float(2*np.log(np.diag(root)).sum())
    return dict(quadratic=quadratic, logdet=logdet,
        negative_twice_log_density=quadratic+logdet+len(raw)*np.log(2*np.pi))


def schur_factorization(raw, covariance, parent_count):
    """Exact p(existing_predictive,target | curved) factorization."""
    raw, covariance = np.asarray(raw, float), np.asarray(covariance, float)
    n = int(parent_count)
    if n == 0:
        return dense_nll(raw, covariance)['negative_twice_log_density']
    cee, cet, ctt = covariance[:n, :n], covariance[:n, n:], covariance[n:, n:]
    conditional_raw = raw[n:] - cet.T @ np.linalg.solve(cee, raw[:n])
    conditional_covariance = ctt - cet.T @ np.linalg.solve(cee, cet)
    return (dense_nll(raw[:n], cee)['negative_twice_log_density']
        + dense_nll(conditional_raw, conditional_covariance)['negative_twice_log_density'])


def covariance_from_features(native_sigma, uncertainty):
    sigma, uncertainty = np.asarray(native_sigma, float), np.asarray(uncertainty, float)
    return np.diag(sigma**2) + uncertainty @ uncertainty.T
