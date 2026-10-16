"""Explicit original joint-event and unit selected-CFO Gaussian observation ports."""

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit, logit

from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood, circular


def detection_probabilities(basis, theta, budget):
    basis, theta = np.asarray(basis, float), np.asarray(theta, float)
    if (basis.ndim != 2 or theta.shape != (basis.shape[1],)
            or not np.isfinite(basis).all() or not np.isfinite(theta).all()
            or not 0 < budget < len(basis)):
        raise ValueError("Finite catalogue basis and valid full-bank detection budget required")
    u = basis@theta
    a0 = float(logit(budget/len(basis)))
    if np.ptp(u) < 1e-14:
        a, q = a0-float(u.mean()), np.full(len(basis), budget/len(basis))
    else:
        a = brentq(lambda x: float(expit(x+u).sum()-budget), a0-u.max(), a0-u.min(),
                   xtol=1e-14, rtol=1e-14)
        q = expit(a+u)
    if abs(q.sum()-budget) > 1e-11 or np.any((q <= 0)|(q >= 1)):
        raise ValueError("Full-bank detection probability budget failed")
    slope = q*(1-q)
    centered = basis-(slope[:, None]*basis).sum(axis=0)/slope.sum()
    return q, slope[:, None]*centered, float(a)


def score(measured, prediction, visible, sigma, q, config, *, conditional):
    measured, prediction = np.asarray(measured, float), np.asarray(prediction, float)
    visible, sigma, q = np.asarray(visible), np.asarray(sigma, float), np.asarray(q, float)
    if (prediction.ndim != 2 or measured.shape != (len(prediction),)
            or visible.shape != prediction.shape or visible.dtype != bool
            or sigma.shape != measured.shape or q.shape != (prediction.shape[1],)
            or not np.isfinite(measured).all() or not np.isfinite(prediction).all()
            or not np.isfinite(sigma).all() or np.any((sigma <= 0)|(sigma > 1000))
            or not np.isfinite(q).all() or np.any((q <= 0)|(q >= 1))
            or abs(q.sum()-config.detection_budget) > 1e-10):
        raise ValueError("Finite aligned narrow-Gaussian arrays and full-bank q budget required")
    residual = circular(measured[:, None]-prediction)
    odds = q/(1-q)
    signal = np.exp(-.5*(residual/sigma[:, None])**2)*visible
    signal *= odds[None, :]/(sigma[:, None]*np.sqrt(2*np.pi))
    total = config.clutter_rate/ALIAS_HZ+signal.sum(axis=1)
    responsibility = signal/total[:, None]
    clutter = config.clutter_rate/ALIAS_HZ/total
    log_p0 = -config.clutter_rate+(visible*np.log1p(-q)[None, :]).sum(axis=1)
    z = config.clutter_rate+(visible*odds[None, :]).sum(axis=1)
    log_mass = log_p0-np.log(-np.expm1(log_p0))+np.log(z)
    joint_nll = -log_p0+np.log(-np.expm1(log_p0))-np.log(total)
    conditional_nll = np.log(z)-np.log(total)
    rows = conditional_nll if conditional else joint_nll
    prediction_gradient = -responsibility*residual/sigma[:, None]**2
    sigma_gradient = (responsibility*(1-(residual/sigma[:, None])**2)).sum(axis=1)
    if conditional:
        q_gradient = (visible/(z[:, None]*(1-q)[None, :]**2)
                      -responsibility/(q*(1-q))[None, :]).sum(axis=0)
    else:
        q_gradient = (visible/((-np.expm1(log_p0))[:, None]*(1-q)[None, :])
                      -responsibility/(q*(1-q))[None, :]).sum(axis=0)
    terms = WindowLikelihood(float(rows.sum()), responsibility, clutter,
                             prediction_gradient, residual)
    return terms, dict(row_nll=rows, joint_event_nll=joint_nll,
        conditional_cfo_nll=conditional_nll, log_integrated_event_mass=log_mass,
        p0=np.exp(log_p0), selected_cfo_normalizer=z, full_bank_budget=float(q.sum()),
        visible_probability_sum=visible@q, visible_odds_sum=visible@odds,
        sigma_log_gradient=sigma_gradient, detection_probability_gradient=q_gradient)
