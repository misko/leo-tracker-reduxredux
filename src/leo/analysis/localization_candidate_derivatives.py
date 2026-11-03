"""Exact frequency-mixture derivatives and profiled-offset chain rule."""
import numpy as np

from leo.analysis.localization_candidate_set import candidate_set_log_ratio, wrapped_cauchy_pdf


def candidate_set_derivatives(candidates, means, *, period, scale, signal_probability=.5):
    """Return log ratio, gradient in component means and signal responsibilities."""
    value = candidate_set_log_ratio(candidates, means, period=period, scale=scale,
                                    signal_probability=signal_probability)
    y, mu = np.asarray(candidates, dtype=float), np.asarray(means, dtype=float)
    if not y.size or not mu.size:
        return value, np.zeros(mu.size), np.zeros((y.size, mu.size))
    residual = y[:, None]-mu[None, :]
    density = wrapped_cauchy_pdf(residual, period, scale)
    responsibility = signal_probability*period*density/(y.size*mu.size*np.exp(value))
    a = 2*np.pi*scale/period
    rho = np.exp(-a)
    phase = ((residual+period/2) % period-period/2)*np.pi/period
    denominator = np.expm1(-a)**2+4*rho*np.sin(phase)**2
    mean_score = (4*rho*np.pi/period)*np.sin(2*phase)/denominator
    return value, np.sum(responsibility*mean_score, axis=0), responsibility


def profile_offset_jacobian(raw_jacobian, training_count, training_weights):
    """Derivative of check mean plus the GLS offset estimated on training data.

    Raw rows are training followed by checking samples. Measurements and GLS
    weights are fixed; the fitted offset's derivative is minus the weighted
    training prediction derivative. Keeping it is essential for clock/drift
    and geometry parameters that also change the training predictions.
    """
    j = np.asarray(raw_jacobian, dtype=float)
    w = np.asarray(training_weights, dtype=float)
    if (j.ndim != 2 or not isinstance(training_count, int)
            or not 0 < training_count < len(j) or w.shape != (training_count,)
            or not np.all(np.isfinite(j)) or not np.all(np.isfinite(w))
            or not np.isclose(w.sum(), 1., atol=1e-12, rtol=1e-12)):
        raise ValueError('invalid profiled offset inputs')
    return j[training_count:]-w@j[:training_count]
