"""Raw target-IQ predictive density with a Gaussian latent pilot gain vector."""

import numpy as np


def target_gain_density(samples, basis, mean, covariance, noise_variance):
    y, b, mu, covariance = map(np.asarray, (samples, basis, mean, covariance))
    if b.ndim != 2 or b.shape != (len(y), len(mu)) or covariance.shape != (len(mu), len(mu)):
        raise ValueError('matching target IQ, component basis, and Gaussian gain prior required')
    if noise_variance <= 0 or np.linalg.eigvalsh(covariance).min() <= 0:
        raise ValueError('positive target noise and gain covariance required')
    centered = b-b.mean(axis=0)
    residual = y-b@mu
    residual -= residual.mean()
    normal = np.linalg.inv(covariance)+centered.conj().T@centered/noise_variance
    rhs = centered.conj().T@residual/noise_variance
    quadratic = float(np.vdot(residual, residual).real/noise_variance
        - np.vdot(rhs, np.linalg.solve(normal, rhs)).real)
    logdet = ((len(y)-1)*np.log(noise_variance)
        + np.linalg.slogdet(normal)[1]+np.linalg.slogdet(covariance)[1])
    return float(quadratic+logdet+(len(y)-1)*np.log(np.pi))
