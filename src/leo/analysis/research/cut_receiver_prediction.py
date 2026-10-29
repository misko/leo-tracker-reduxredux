"""Modular target prediction without updating the receiver posterior.

At each fixed phase, integrate the unchanged receiver Gaussian after fitting
satellite nuisance coordinates conditional on it. Phase weights use the target
training marginal likelihood; their factorization from the receiver posterior
is an explicit approximation, not the ordinary joint Bayesian posterior.
"""
import numpy as np
from scipy.linalg import cho_solve
from scipy.special import logsumexp
from leo.analysis.research.predictive_track import gaussian_log_density, mixture_prediction


def cut_receiver_prediction(observed, means, covariances, frozen_covariance,
                            log_prior, training, held):
    y, m, cov, frozen, lp = (np.asarray(v, float) for v in
                            (observed, means, covariances, frozen_covariance, log_prior))
    train, test = np.asarray(training, bool), np.asarray(held, bool)
    if (y.ndim != 1 or m.ndim != 2 or m.shape[1:] != y.shape or
            cov.shape != (len(m), len(y), len(y)) or frozen.shape != (len(y), len(y)) or
            lp.shape != (len(m),)):
        raise ValueError('matching mixture and frozen receiver covariance required')
    if train.shape != y.shape or test.shape != y.shape or np.any(train & test) or not test.any():
        raise ValueError('disjoint training and nonempty held masks required')
    if (not all(np.isfinite(v).all() for v in (y, m, cov, frozen)) or
            not np.isfinite(lp).any() or np.isnan(lp).any() or np.isposinf(lp).any()):
        raise ValueError('finite geometry and at least one finite prior required')
    if not np.allclose(frozen, frozen.T, rtol=1e-10, atol=1e-8):
        raise ValueError('symmetric frozen covariance required')
    if np.linalg.eigvalsh(frozen).min() < -1e-8 * max(1., np.max(abs(frozen))):
        raise ValueError('positive semidefinite frozen covariance required')
    held_means, held_cov, training_log = [], [], []
    for mean, total in zip(m, cov, strict=True):
        # B contains satellite nuisance and observation noise; F is frozen.
        b = total - frozen
        if not np.allclose(b, b.T, rtol=1e-10, atol=1e-8):
            raise ValueError('symmetric satellite/noise covariance required')
        np.linalg.cholesky((b+b.T)/2)
        mu = mean[test].copy()
        variance = total[np.ix_(test, test)].copy()
        likelihood = 0.
        if train.any():
            bt = b[np.ix_(train, train)]
            cross = b[np.ix_(test, train)]
            gain = cho_solve((np.linalg.cholesky(bt), True), cross.T).T
            residual = y[train] - mean[train]
            mu += gain @ residual
            ft = frozen[np.ix_(train, train)]
            fh = frozen[np.ix_(test, train)]
            variance += -gain @ cross.T + gain @ ft @ gain.T - gain @ fh.T - fh @ gain.T
            likelihood = gaussian_log_density(residual, total[np.ix_(train, train)])
        held_means.append(mu)
        held_cov.append((variance+variance.T)/2)
        training_log.append(likelihood)
    weights = lp - logsumexp(lp) + training_log
    evidence = logsumexp(weights)
    result = mixture_prediction(y[test], np.asarray(held_means), np.asarray(held_cov), weights,
                                np.zeros(test.sum(), bool), np.ones(test.sum(), bool))
    result.update(training_negative_twice_log_density=float(-2*evidence),
                  receiver_posterior_frozen=True, phase_receiver_factorization=True,
                  prediction_kind='modular_frozen_receiver')
    return result
