"""Residual checks against a curved-data posterior predictive covariance.

The new observations never update calibration. This is a conditional Gaussian
check at fixed hierarchical precisions, not a calibrated identity probability.
"""

import numpy as np

from .polynomial_satellite_diagnostics import batch_noise_screen


def predictive_track_gate(raw, design, calibration_precision, sigma, times, *, bias_sigma=300.):
    """Whiten unseen residuals using measurement, calibration and bias uncertainty."""
    residual, u, precision, t = (np.asarray(v, float) for v in
                                (raw, design, calibration_precision, times))
    if residual.ndim != 1 or u.ndim != 2 or u.shape[0] != len(residual):
        raise ValueError('matching residual vector and calibration design required')
    s = np.broadcast_to(np.asarray(sigma, float), residual.shape)
    if t.shape != residual.shape or len(t) < 4 or precision.shape != (u.shape[1], u.shape[1]):
        raise ValueError('matching time vector and square calibration precision required')
    if not all(np.isfinite(v).all() for v in (residual, u, precision, t, s)) or np.any(s <= 0):
        raise ValueError('finite inputs and strictly positive measurement noise required')
    if not np.isfinite(bias_sigma) or bias_sigma < 0 or np.any(np.diff(t) <= 0):
        raise ValueError('nonnegative finite bias SD and increasing times required')
    if not np.allclose(precision, precision.T, rtol=1e-10, atol=1e-10):
        raise ValueError('symmetric calibration precision required')
    root = np.linalg.cholesky(precision)
    uncertainty = np.linalg.solve(root, u.T).T
    covariance = np.diag(s*s) + uncertainty @ uncertainty.T + bias_sigma**2
    predictive_root = np.linalg.cholesky(covariance)
    # Existing screen's 75 Hz floor becomes one standardized unit. No scale is
    # fitted to these new residuals, and no gate threshold is increased.
    innovations = 75. * np.linalg.solve(predictive_root, residual)
    diagnostic = batch_noise_screen(innovations[None, :], t)
    return dict(compatible=bool(diagnostic['noise_screen_pass'][0]),
                whitened_innovations_hz=innovations,
                diagnostics={k:float(v[0]) for k,v in diagnostic.items() if k != 'noise_screen_pass'},
                predictive_variance_hz2=np.diag(covariance))
