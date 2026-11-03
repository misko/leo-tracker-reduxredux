"""Marginalize one shared receiver phase per frame in target-IQ prediction."""

from functools import lru_cache
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp


def frame_statistics(source, target, source_basis, target_basis, source_variance, target_variance):
    x = np.column_stack((source_basis, np.ones(len(source))))
    coefficient = np.linalg.lstsq(x, source, rcond=1e-8)[0]
    gain_covariance = source_variance*np.linalg.inv(x.conj().T@x)[:-1, :-1]
    basis = target_basis-target_basis.mean(axis=0)
    y = np.asarray(target)-np.mean(target)
    mean = basis@coefficient[:-1]
    normal = np.linalg.inv(gain_covariance)+basis.conj().T@basis/target_variance
    def inverse(value):
        rhs = basis.conj().T@value/target_variance
        return value/target_variance-basis@np.linalg.solve(normal, rhs)/target_variance
    wy, wm = inverse(y), inverse(mean)
    logdet = ((len(target)-1)*np.log(target_variance)
        + np.linalg.slogdet(normal)[1]+np.linalg.slogdet(gain_covariance)[1])
    return dict(constant=float(logdet+(len(target)-1)*np.log(np.pi)),
        y_quadratic=float(np.vdot(y, wy).real), mean_quadratic=float(np.vdot(mean, wm).real),
        cross_real=float(np.vdot(mean, wy).real), cross_imag=float(np.vdot(mean, wy).imag))


@lru_cache(maxsize=4)
def phase_grid(size):
    phi = np.linspace(-np.pi, np.pi, size, endpoint=False)
    return phi, np.cos(phi), np.sin(phi)


def phase_NLL(statistics, sigma_rad, *, grid_size=4096):
    if not np.isfinite(sigma_rad) or sigma_rad < 0 or sigma_rad > np.pi:
        raise ValueError('shared receiver phase SD must be between0andpi')
    constant = statistics['constant']+statistics['y_quadratic']+statistics['mean_quadratic']
    if sigma_rad == 0:
        return float(constant-2*statistics['cross_real'])
    phi, cosine, sine = phase_grid(grid_size)
    images = phi[:, None]+2*np.pi*np.arange(-3, 4)[None]
    logprior = logsumexp(-.5*(images/sigma_rad)**2, axis=1)
    logprior -= logsumexp(logprior)
    likelihood = 2*(statistics['cross_real']*cosine+statistics['cross_imag']*sine)
    return float(constant-logsumexp(likelihood+logprior))


def fit_phase_sigma(training_statistics):
    if len(training_statistics) < 4:
        raise ValueError('four training frames required for receiver phase variance')
    def objective(log_sigma):
        return sum(phase_NLL(s, float(np.exp(log_sigma))) for s in training_statistics)
    result = minimize_scalar(objective, bounds=(-6., np.log(np.pi)), method='bounded', options=dict(xatol=1e-5))
    zero = sum(phase_NLL(s, 0.) for s in training_statistics)
    if result.fun >= zero:
        return dict(sigma_rad=0., training_NLL=float(zero), converged=True)
    return dict(sigma_rad=float(np.exp(result.x)), training_NLL=float(result.fun), converged=bool(result.success))
