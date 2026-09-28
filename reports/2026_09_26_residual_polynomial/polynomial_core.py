"""Pure, training-only conditional polynomial residual diagnostics."""
import numpy as np


def fit_residual(times, residual, training, degree):
    t = np.asarray(times, float)
    y = np.asarray(residual, float)
    mask = np.asarray(training, bool)
    if t.ndim != 1 or t.shape != y.shape or mask.shape != t.shape:
        raise ValueError('aligned one-dimensional arrays required')
    if degree not in (0, 1, 2, 3) or mask.sum() <= degree + 1 or not (~mask).any():
        raise ValueError('unsupported degree or insufficient partition')
    if not np.isfinite(t).all() or not np.isfinite(y).all():
        raise ValueError('finite observations required')
    origin = float(t[mask].mean())
    scale = float(np.ptp(t[mask]) / 2)
    if scale <= 0:
        raise ValueError('nonzero training span required')
    design = np.polynomial.polynomial.polyvander((t-origin)/scale, degree)
    coef, _, rank, _ = np.linalg.lstsq(design[mask], y[mask], rcond=None)
    if rank != degree + 1:
        raise ValueError('rank deficient polynomial')
    correction = design @ coef
    error = y-correction
    shape = correction-coef[0]
    return {'degree': degree, 'origin_s': origin, 'scale_s': scale,
            'coefficients_scaled_hz': coef.tolist(),
            'coefficients_hz_per_s_power': (coef/scale**np.arange(degree+1)).tolist(),
            'training_rms_hz': float(np.sqrt(np.mean(error[mask]**2))),
            'evaluation_rms_hz': float(np.sqrt(np.mean(error[~mask]**2))),
            'training_shape_peak_to_peak_hz': float(np.ptp(shape[mask])),
            'evaluation_residual_hz': error[~mask].tolist()}
