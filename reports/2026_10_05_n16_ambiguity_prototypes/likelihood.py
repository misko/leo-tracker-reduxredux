"""Ambiguity prototypes with the N-cohort's variable-q smooth horizon.

No position truth, storage or satellite selection enters this likelihood.
Hard identities and masks are fixed externally; the ambiguity penalty is
conditional-signal min-entropy, not additional independent physical evidence.
"""
import numpy as np
from scipy.special import logsumexp

from smooth_visibility_model import gate_terms
from position_structure_study import ALIAS, density_terms


def freeze(p, clutter):
    p, clutter = np.asarray(p), np.asarray(clutter)
    if p.ndim != 2 or p.shape[1] < 2 or clutter.shape != (len(p),):
        raise ValueError('Expected satellite responsibility matrix and clutter vector')
    if np.any(~np.isfinite(p)) or np.any(p < 0) or np.any(clutter < -1e-12):
        raise ValueError('Invalid responsibility')
    np.testing.assert_allclose(p.sum(axis=1)+clutter, 1., atol=2e-12, rtol=0)
    winner = np.argmax(p, axis=1)
    second = np.sort(p, axis=1)[:, -2]
    real = p.max(axis=1) > clutter
    return dict(winner=winner, second=second, real=real,
                unambiguous=second <= .05, keep=real & (second <= .05))


class Likelihood:
    def __init__(self, data, features, frozen, mode):
        self.measured, self.features = data.measured, features
        self.coefficients = np.zeros(features.shape[1])
        self.alias_hz, self.clutter_rate = ALIAS, 2.
        self.detection_probability = .8/len(data.numbers)
        self.keep = np.ones(len(data.times), bool)
        if mode in ('signal_only', 'hard_only'):
            self.keep = frozen['real'].copy()
        if mode in ('drop_only', 'drop_hard'):
            self.keep = frozen['keep'].copy()
        self.owners = frozen['winner'].copy()
        self.hard = mode in ('hard_only', 'drop_hard')
        self.eta = float(mode[-1]) if mode.startswith('penalty_') else 0.
        self.geometry = None
        self.last_result = None

    def evaluate(self, predicted, visible, *, sigma_hz, **unused):
        sine, log_factor = self.geometry
        if np.any(log_factor != 0):
            raise ValueError('This matched experiment has no cone weighting')
        gate, derivative = gate_terms(sine, 'Q1')
        q = self.detection_probability*gate
        dq = self.detection_probability*derivative
        pred = predicted+(self.features@self.coefficients)[:, None]
        residual = (self.measured[:, None]-pred+ALIAS/2)%ALIAS-ALIAS/2
        logf, dg, precision = density_terms(residual, 'C1', sigma_hz)
        logq = np.full_like(q, -np.inf)
        np.log(q, out=logq, where=q > 0)
        logs = logq-np.log1p(-q)+logf
        signal = logsumexp(logs, axis=1)
        norm = np.logaddexp(np.log(self.clutter_rate/ALIAS), signal)
        p = np.exp(logs-norm[:, None])
        logempty = -self.clutter_rate+np.log1p(-q).sum(axis=1)
        nonempty = -np.expm1(logempty)
        softlog = logempty+norm-np.log(nonempty)
        perwindow = softlog.copy()
        gradient = p*dg
        weights = p*precision
        # d log L / d sin(elevation), including the finite-set normalizer.
        geom = (np.exp(logf-norm[:, None])/(1-q)**2
                -1/((1-q)*nonempty[:, None]))*dq
        ambiguity = np.zeros(len(p))
        invisible = 0
        if self.hard:
            idx = np.arange(len(p))
            chosen = np.zeros_like(p)
            chosen[idx, self.owners] = 1.
            perwindow = logf[idx, self.owners].copy()
            invalid = (sine[idx, self.owners] < 0) & self.keep
            invisible = int(invalid.sum())
            perwindow[invalid] = -1e24
            gradient = chosen*dg
            gradient[invalid] = 0.
            weights = chosen*precision
            geom[:] = 0.  # Conditional fixed-ID Gaussian, not owner-or-clutter.
        elif self.eta:
            good = np.isfinite(signal)
            pi = np.zeros_like(p)
            pi[good] = np.exp(logs[good]-signal[good, None])
            idx = np.flatnonzero(good)
            top = np.argmax(logs, axis=1)
            chosen = np.zeros_like(p)
            chosen[idx, top[good]] = 1.
            ambiguity[good] = signal[good]-logs[idx, top[good]]
            perwindow -= self.eta*ambiguity
            gradient += self.eta*(chosen-pi)*dg
            # Piecewise exact derivative away from ties. At q=0 the compact
            # horizon gate has zero derivative; do not evaluate 0/0 there.
            logodds_derivative = np.zeros_like(q)
            np.divide(dq, q*(1-q), out=logodds_derivative, where=q > 0)
            geom += self.eta*(chosen-pi)*logodds_derivative
            # Positive preconditioner only; acceptance uses the actual loss.
            weights += self.eta*(pi+chosen)*precision
        result = dict(total_log_likelihood=float(self.keep@perwindow),
            window_log_likelihood=perwindow, row_association_probability=p,
            row_clutter_probability=np.exp(np.log(self.clutter_rate/ALIAS)-norm),
            prediction_gradient=self.keep[:, None]*gradient,
            irls_weights=self.keep[:, None]*weights,
            sine_loss_gradient=-(self.keep[:, None]*geom),
            log_factor_loss_gradient=np.zeros_like(q),
            unpenalized_soft_nll=float(-(self.keep@softlog)),
            ambiguity_penalty=float(self.eta*(self.keep@ambiguity)),
            mean_conditional_min_entropy=float(np.mean(ambiguity)),
            hard_invisible_windows=invisible)
        self.last_result = result
        return result
