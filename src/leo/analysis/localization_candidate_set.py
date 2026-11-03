"""Normalized conditional candidate-set model on a frequency-alias circle."""
import numpy as np


def wrapped_cauchy_pdf(residual, period, scale):
    """Exactly normalized wrapped Cauchy using a stable Poisson-kernel form."""
    x = np.asarray(residual, dtype=float)
    if (not np.isfinite(period) or period <= 0 or not np.isfinite(scale) or scale <= 0
            or not np.all(np.isfinite(x))):
        raise ValueError('invalid wrapped frequency density inputs')
    a = 2*np.pi*scale/period
    rho = np.exp(-a)
    phase = ((x+period/2) % period-period/2)*np.pi/period
    denominator = np.expm1(-a)**2+4*rho*np.sin(phase)**2
    return -np.expm1(-2*a)/(period*denominator)


def candidate_set_log_ratio(candidates, means, *, period, scale, signal_probability=.5):
    """Log density ratio to uniform clutter, conditional on candidate count.

    With probability p exactly one uniformly chosen candidate comes from a
    uniform mixture of predicted frequencies; other candidates are uniform.
    Otherwise all are uniform clutter. Candidate order carries no information.
    Empty predictions or an empty set provide no evidence in this conditional
    model. Across probes this is only a composite score unless independence
    is justified separately.
    """
    y, mu = np.asarray(candidates, dtype=float), np.asarray(means, dtype=float)
    if (y.ndim != 1 or mu.ndim != 1 or not np.all(np.isfinite(y))
            or not np.all(np.isfinite(mu)) or not np.isfinite(signal_probability)
            or not 0 <= signal_probability <= 1):
        raise ValueError('invalid candidate set')
    wrapped_cauchy_pdf(np.array([0.]), period, scale)
    if not len(y) or not len(mu):
        return 0.
    signal_ratio = period*np.mean(wrapped_cauchy_pdf(y[:, None]-mu[None, :], period, scale))
    return float(np.log((1-signal_probability)+signal_probability*signal_ratio))
