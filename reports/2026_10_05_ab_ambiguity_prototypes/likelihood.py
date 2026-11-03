"""Frozen-identity Gaussian and min-entropy experiments, not calibrated evidence.

Only numpy/scipy inputs. Window masks and hard identities are frozen externally.
The ambiguity regularizer is conditional on signal and dynamically evaluated.
Reported soft responsibilities remain the unpenalized model probabilities.
"""
import numpy as np
from scipy.special import logsumexp

ALIAS = 1./4.4e-6


def freeze(probability, clutter):
    p = np.asarray(probability, float)
    clutter = np.asarray(clutter, float)
    if p.ndim != 2 or p.shape[1] < 2 or clutter.shape != (len(p),):
        raise ValueError('Expected at least two satellite columns and one clutter column')
    if not np.all(np.isfinite(p)) or np.any(p < 0) or np.any(clutter < -1e-12):
        raise ValueError('Invalid responsibilities')
    np.testing.assert_allclose(p.sum(axis=1)+clutter, 1., atol=2e-12, rtol=0)
    order = np.argsort(p, axis=1, kind='stable')
    winner = np.argmax(p, axis=1)
    second = p[np.arange(len(p)), order[:, -2]]
    real = p[np.arange(len(p)), winner] > clutter
    unambiguous = second <= .05
    return dict(winner=winner, second=second, real=real, unambiguous=unambiguous,
                keep=real & unambiguous)


def gaussian(residual, sigma):
    r = (np.asarray(residual)+ALIAS/2) % ALIAS - ALIAS/2
    copies = np.stack([r+j*ALIAS for j in (-1, 0, 1)])
    logs = -.5*(copies/sigma)**2 - np.log(sigma*np.sqrt(2*np.pi))
    logf = logsumexp(logs, axis=0)
    dg = np.sum(np.exp(logs-logf)*copies, axis=0)/sigma**2
    return logf, dg


class Likelihood:
    def __init__(self, measured, features, satellite_count, keep, owners, hard=False, eta=0.):
        self.measured = np.asarray(measured)
        self.features = np.asarray(features)
        self.coefficients = np.zeros(self.features.shape[1])
        self.keep = np.asarray(keep, bool).copy()
        self.owners = np.asarray(owners, int).copy()
        self.hard, self.eta = bool(hard), float(eta)
        self.alias_hz, self.clutter_rate = ALIAS, 2.
        self.detection_probability = .8/satellite_count
        self.last_result = None
        if self.keep.shape != self.measured.shape or self.owners.shape != self.measured.shape:
            raise ValueError('Mask/owner shape mismatch')
        if np.any(self.owners < 0) or np.any(self.owners >= satellite_count):
            raise ValueError('Invalid frozen owner')
        if eta < 0 or (hard and eta):
            raise ValueError('Separate hard-assignment and ambiguity-penalty arms required')

    def evaluate(self, predicted, visible, *, sigma_hz, **unused):
        pred = np.asarray(predicted) + (self.features @ self.coefficients)[:, None]
        visible = np.asarray(visible, bool)
        logf, dg = gaussian(self.measured[:, None]-pred, sigma_hz)
        q = self.detection_probability
        logs = np.where(visible, np.log(q/(1-q))+logf, -np.inf)
        signal = logsumexp(logs, axis=1)
        norm = np.logaddexp(np.log(self.clutter_rate/ALIAS), signal)
        probability = np.exp(logs-norm[:, None])
        clutter = np.exp(np.log(self.clutter_rate/ALIAS)-norm)
        logempty = -self.clutter_rate + visible.sum(axis=1)*np.log1p(-q)
        softlog = logempty + norm - np.log(-np.expm1(logempty))
        gradient = probability*dg
        precision = probability/sigma_hz**2
        ambiguity = np.zeros(len(pred))
        hard_invisible = 0
        if self.hard:
            idx = np.arange(len(pred))
            perwindow = logf[idx, self.owners].copy()
            chosen = np.zeros_like(probability)
            chosen[idx, self.owners] = 1.
            # Hard identity is a conditional Gaussian, not owner-or-clutter.
            # Below-horizon assigned observations are infeasible, not silently
            # switched to clutter. This guard is inactive in admitted results.
            invalid = ~visible[idx, self.owners] & self.keep
            hard_invisible = int(invalid.sum())
            perwindow[invalid] = -1e24
            gradient = chosen*dg
            gradient[invalid] = 0.
            precision = chosen/sigma_hz**2
        else:
            perwindow = softlog.copy()
            if self.eta:
                good = np.isfinite(signal)
                pi = np.zeros_like(probability)
                pi[good] = np.exp(logs[good]-signal[good, None])
                top = np.argmax(logs, axis=1)
                chosen = np.zeros_like(probability)
                chosen[np.flatnonzero(good), top[good]] = 1.
                ambiguity[good] = signal[good]-logs[np.flatnonzero(good), top[good]]
                perwindow -= self.eta*ambiguity
                gradient += self.eta*(chosen-pi)*dg
                # Positive preconditioner only, not the exact observed Hessian.
                # Actual regularized objective decides step acceptance.
                precision += self.eta*(pi+chosen)/sigma_hz**2
        result = dict(total_log_likelihood=float(self.keep @ perwindow),
            window_log_likelihood=perwindow, row_association_probability=probability,
            row_clutter_probability=clutter, prediction_gradient=self.keep[:, None]*gradient,
            irls_weights=self.keep[:, None]*precision,
            unpenalized_soft_nll=float(-(self.keep @ softlog)),
            ambiguity_penalty=float(self.eta*(self.keep @ ambiguity)),
            hard_invisible_windows=hard_invisible)
        self.last_result = result
        return result
