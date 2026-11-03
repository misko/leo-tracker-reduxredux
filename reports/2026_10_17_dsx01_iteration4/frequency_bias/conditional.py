"""Conditional excluded-residual prediction: only new b is learned on train rows.

Physical/calibration/q baseline is already full-data conditioned. This is NOT a
clean cold-pipeline validation, identity test or geographic prediction test.
"""
from dataclasses import replace
import time

import numpy as np
from scipy.optimize import minimize

from leo.analysis.regional_position_score import ALIAS_HZ, circular
from model import PRIOR_WIDTHS_HZ, BIAS_BOUND_HZ


def masked_baseline(base, observations, mask):
    """Transport the unchanged baseline to a declared row mask, without refitting."""
    mask = np.asarray(mask, bool)
    rows = np.flatnonzero(mask)
    model = object.__new__(type(base))
    model.__dict__.update(base.__dict__)
    model.mask = mask.copy()
    model.mask.setflags(write=False)
    model.scored_observations = replace(observations,
        window_ids=tuple(observations.window_ids[i] for i in rows),
        **{key:getattr(observations, key)[rows] for key in
            ('times_s', 'measured_hz', 'rf_hz', 'receiver', 'channel', 'margin')})
    return model


class FixedResidualLikelihood:
    def __init__(self, baseline, vector, nuisance, sigma_hz):
        if sigma_hz not in PRIOR_WIDTHS_HZ:
            raise ValueError('Use the same predeclared 300/1000 Hz prior widths')
        ev, details = baseline.evaluate_details(vector, nuisance)
        self.sigma_bias = float(sigma_hz)
        self.residual = ev[3].residual_hz
        self.sigma = details['sigma_hz']
        p = details['visibility_weight']*details['detection_probability'][None, :]
        self.odds = p/(1-p)
        self.clutter = baseline.score.clutter_rate/ALIAS_HZ
        self.log_normalizer = np.log(baseline.score.clutter_rate+self.odds.sum(axis=1))
        self.fixed_prior = float(ev[0]-ev[3].nll)
        self.count = 0
        self.profile_calls = 0

    def terms(self, bias):
        b = np.asarray(bias, float)
        if b.shape != (self.residual.shape[1],) or not np.all(np.isfinite(b)) or np.any(abs(b) > BIAS_BOUND_HZ+1e-7):
            raise ValueError('Finite bounded K-satellite constant-Hz bias required')
        residual = circular(self.residual-b[None, :])
        signal = self.odds*np.exp(-.5*(residual/self.sigma[:, None])**2)/(self.sigma[:, None]*np.sqrt(2*np.pi))
        total = self.clutter+signal.sum(axis=1)
        nll = float(np.sum(self.log_normalizer-np.log(total)))
        gradient = np.sum(-signal/total[:, None]*residual/self.sigma[:, None]**2, axis=0)
        return nll, gradient, residual, signal, total

    def evaluate(self, bias):
        self.count += 1
        nll, gradient, _, _, _ = self.terms(bias)
        return (nll+self.fixed_prior+.5*float(np.asarray(bias)@bias)/self.sigma_bias**2,
            gradient+np.asarray(bias)/self.sigma_bias**2)

    def profile(self, current, proposed):
        nll, _, residual, signal, total = self.terms(current)
        remaining = np.maximum(total[:, None]-signal, self.clutter)
        rr = circular(residual-(np.asarray(proposed)-current)[None, :])
        new_signal = self.odds*np.exp(-.5*(rr/self.sigma[:, None])**2)/(self.sigma[:, None]*np.sqrt(2*np.pi))
        self.profile_calls += 1
        return (self.log_normalizer.sum()-np.log(remaining+new_signal).sum(axis=0)
            +self.fixed_prior+.5*np.sum(np.asarray(current)**2)/self.sigma_bias**2
            +.5*(np.asarray(proposed)**2-np.asarray(current)**2)/self.sigma_bias**2)

    def stats(self, bias):
        nll, _, residual, signal, _ = self.terms(bias)
        best = np.argmax(signal, axis=1)
        rows = np.arange(len(best))
        assigned = signal[rows, best] > self.clutter
        return dict(nll=nll, best=best, assigned=assigned, residual=residual[rows, best])


class Expired(Exception):
    pass


def fit_bias_only(likelihood, *, max_evaluations=300, max_seconds=30):
    """Exact full train-row J selection; all physical/q values stay outside fitter."""
    deadline = time.monotonic()+max_seconds
    bias = np.zeros(likelihood.residual.shape[1])
    value, gradient = likelihood.evaluate(bias)
    initial = value
    for _ in range(2):
        if likelihood.count >= max_evaluations*.3 or time.monotonic() >= deadline:
            break
        scores = np.full(len(bias), value)
        centers = bias.copy()
        for trial in np.arange(-4000., 4000.1, 250.):
            if time.monotonic() >= deadline:
                break
            proposed = np.full(len(bias), trial)
            score = likelihood.profile(bias, proposed)
            take = score < scores
            scores[take], centers[take] = score[take], proposed[take]
        fine = centers.copy()
        for offset in np.arange(-200., 200.1, 50.):
            if time.monotonic() >= deadline:
                break
            proposed = np.clip(fine+offset, -4000., 4000.)
            score = likelihood.profile(bias, proposed)
            take = score < scores
            scores[take], centers[take] = score[take], proposed[take]
        for k in np.argsort(scores, kind='stable')[:20]:
            if likelihood.count >= max_evaluations*.3 or time.monotonic() >= deadline:
                break
            proposed = bias.copy()
            proposed[k] = centers[k]
            trial, g = likelihood.evaluate(proposed)
            if trial < value-1e-7:
                bias, value, gradient = proposed, float(trial), g
    best = [value, bias.copy(), gradient.copy()]

    def objective(b):
        if likelihood.count >= max_evaluations or time.monotonic() >= deadline:
            raise Expired()
        v, g = likelihood.evaluate(b)
        if v < best[0]:
            best[:] = [float(v), b.copy(), g.copy()]
        return v, g

    reason = 'not-refined'
    try:
        solved = minimize(objective, bias, jac=True, method='L-BFGS-B',
            bounds=[(-4000., 4000.)]*len(bias),
            options=dict(maxiter=max_evaluations, ftol=1e-13, gtol=1e-8, maxls=30))
        reason = str(solved.message)
    except Expired:
        reason = 'density-evaluation-or-wall-budget'
    value, bias, gradient = best
    projected = 200.*gradient
    projected[(bias <= -4000.+1e-7) & (projected >= 0)] = 0
    projected[(bias >= 4000.-1e-7) & (projected <= 0)] = 0
    kkt = float(np.max(abs(projected), initial=0))
    return bias, dict(initial_train_objective=initial, final_train_objective=value,
        density_evaluations=likelihood.count, surrogate_profile_calls=likelihood.profile_calls,
        projected_bias_stationarity=kkt, accepted=bool(kkt <= .001), reason=reason,
        baseline_orbit_evaluations=1, final_positions_unchanged=True,
        qualification='Only new residual biases learned; all physical/calibration/q parameters fixed at a full-data-conditioned baseline.')
