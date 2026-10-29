"""Conditional Gaussian controls separating precision feedback and log-volume.

These research controls freeze the incumbent c0 precision estimates. Fractional
likelihood powers define generalized evidence. The profile objective is a
penalized fit, not a marginal likelihood or a new estimate of identity certainty.
"""

import numpy as np

from ds23_height_problem import geometry_features
from probe_ds23_refined_precision import precision_problem


def arm_prior_precision(c0_precision, fitted_c):
    """The ninth hardware coordinate is the sole extra fitted-c nuisance."""
    precision = np.asarray(c0_precision, float)
    if precision.ndim != 1 or len(precision) < 8 or not np.isfinite(precision).all() or np.any(precision <= 0):
        raise ValueError('positive finite c0 prior precisions required')
    return np.insert(precision, 8, 1.) if fitted_c else precision.copy()


def conditional_gaussian(raw, features, sigma, power, noise_precision,
                         prior_precision, volume_weight):
    """Integrate or profile the same fixed diagonal Gaussian nuisance prior."""
    y, u = np.asarray(raw, float), np.asarray(features, float)
    s, power, tau = (np.asarray(v, float) for v in (sigma, power, noise_precision))
    prior = np.asarray(prior_precision, float)
    if (y.ndim != 1 or not len(y) or u.ndim != 2 or u.shape[0] != len(y)
            or s.shape != y.shape or power.shape != y.shape or tau.shape != y.shape
            or prior.shape != (u.shape[1],) or volume_weight not in (0., 1.)):
        raise ValueError('matching observations, design, positive precisions and volume weight 0 or 1 required')
    if (not all(np.isfinite(v).all() for v in (y,u,s,power,tau,prior))
            or any(np.any(v <= 0) for v in (s,power,tau,prior)) or np.any(power > 1)):
        raise ValueError('finite values, positive scales and powers <=1 required')
    root_weight = np.sqrt(power * tau) / s
    a, b = u * root_weight[:, None], y * root_weight
    gram = np.diag(prior) + a.T @ a
    root = np.linalg.cholesky(gram)
    coefficient = np.linalg.solve(root.T, np.linalg.solve(root, a.T @ b))
    innovation = (y-u@coefficient) * root_weight
    ridge = coefficient * np.sqrt(prior)
    volume = max(0., float(2*np.log(np.diag(root)).sum()-np.log(prior).sum()))
    quadratic = float(innovation@innovation+ridge@ridge)
    normalization = float(np.sum(power*(np.log(2*np.pi)+2*np.log(s)-np.log(tau))))
    residual = np.r_[innovation,ridge,np.sqrt(volume_weight*volume)]
    return dict(coefficient=coefficient,residual=residual,quadratic=quadratic,
        logvolume=volume,normalization_constant=normalization,
        objective=quadratic+volume_weight*volume+normalization,
        coefficient_prior_precision=prior.copy(),
        objective_kind='conditional_Gaussian_marginal' if volume_weight else 'penalized_Gaussian_profile',
        is_generalized_evidence=bool(np.any(power != 1)),
        negative_twice_elbo=quadratic+volume_weight*volume+normalization)


def make_frozen_problem(scan,node,keep,arm,reference,powers,means,model,
                        frozen_noise,frozen_prior,volume_weight):
    p=precision_problem(scan,node,keep,arm,reference,powers,means,model,{})
    prior=arm_prior_precision(frozen_prior,arm=='fitted_c')
    noise=np.asarray(frozen_noise,float)
    if noise.shape!=(len(p.members),):raise ValueError('one frozen noise precision per original fragment required')
    start=p.hardware.shape[1]+p.smooth.shape[1]
    mean=np.zeros(len(prior));mean[start:start+len(p.labels)]=means/p.phase_sigma
    def calculate(position):
        c=geometry_features(p,position,0.)
        features=c['features'];raw=p.values-p.q*c['intercept']-features@mean
        g=p.noise_groups[keep]
        result=conditional_gaussian(raw[keep],features[keep],p.point_noise[keep],
            np.asarray(powers)[g],noise[g],prior,volume_weight)
        result['latent_coefficient']=result['coefficient'].copy()
        result['coefficient']+=mean
        result['noise_precision']=noise.copy()
        result['conditional_residual_hz']=p.values-p.q*c['intercept']-features@result['coefficient']
        c.update(result)
        return c
    p.calculate=calculate
    return p
