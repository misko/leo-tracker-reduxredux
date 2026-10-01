"""Design-only white-noise control matched in the fixed dense contrast space."""
import numpy as np


def matched_white_variance(raw_scale, contrasts):
    raw_scale, contrasts = np.asarray(raw_scale, dtype=float), np.asarray(contrasts, dtype=float)
    if raw_scale.ndim != 2 or raw_scale.shape[0] != raw_scale.shape[1] or contrasts.ndim != 2 or contrasts.shape[1] != raw_scale.shape[0]:
        raise ValueError('Invalid covariance/contrast shapes')
    if not np.all(np.isfinite(raw_scale)) or not np.all(np.isfinite(contrasts)):
        raise ValueError('Nonfinite covariance or contrasts')
    if not np.allclose(raw_scale, raw_scale.T, rtol=0, atol=1e-8):
        raise ValueError('Asymmetric scale')
    np.linalg.cholesky(raw_scale)
    denominator = float(np.trace(contrasts@contrasts.T))
    if denominator <= 0:
        raise ValueError('Empty contrast space')
    variance = float(np.trace(contrasts@raw_scale@contrasts.T)/denominator)
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError('Invalid matched white variance')
    return variance
