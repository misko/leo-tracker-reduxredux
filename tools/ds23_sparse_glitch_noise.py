"""Shared fragment variance plus a sparse, normalized measurement-glitch tail.

The fixed mixture has1percent probability of10times the core SD. Its variance
is normalized to one, so the original Gamma(2,2) marginal variance is retained.
All points contribute; no membership, label, alias, or residual gate changes.
"""

from math import lgamma
import numpy as np
from scipy.special import expit, xlogy

from ds23_observation_noise import observation_bound
from ds23_frequency_events import make_event_problem
from ds23_predictive_linear import attach_predictive_linear
from dsx01_joint_marginal import JointMarginal
from probe_ds23_receiver_smooth_prior import scale_posterior
from ds23_frozen_precision import conditional_gaussian
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features


def predictive_glitch_bound(raw, features, sigma, epsilon=.01, sd_ratio=10., iterations=128):
    """Integrate frozen calibration uncertainty; fit only latent glitch labels.

    Gaussian uncertainty coordinates are integrated within this predictive
    likelihood. Their conditional means never replace curved calibration.
    """
    y, u, s = np.asarray(raw, float), np.asarray(features, float), np.asarray(sigma, float)
    if not 0 <= epsilon < 1 or not np.isfinite(sd_ratio) or sd_ratio < 1 or iterations < 1:
        raise ValueError('valid fixed mixture and positive iteration budget required')
    ones, prior = np.ones(len(y)), np.ones(u.shape[1])
    def gaussian(relative):
        return conditional_gaussian(y, u, s/np.sqrt(relative), ones, ones, prior, 1.)
    if epsilon == 0:
        return dict(gaussian(ones), glitch_probability=np.zeros(len(y)), final_mixture_change=0., mixture_iterations=0)
    variances = np.array([1., sd_ratio**2])/(1-epsilon+epsilon*sd_ratio**2)
    rho = np.full(len(y), epsilon); change = np.inf
    for epoch in range(iterations):
        relative = (1-rho)/variances[0]+rho/variances[1]
        result = gaussian(relative)
        root = np.linalg.cholesky(np.eye(u.shape[1])+u.T@(u*(relative/s**2)[:, None]))
        transformed = np.linalg.solve(root, u.T)
        energy = ((y-u@result['coefficient'])**2+np.sum(transformed**2, axis=0))/s**2
        odds = np.log(epsilon/(1-epsilon))-.5*np.log(sd_ratio**2)+.5*energy*(1/variances[0]-1/variances[1])
        updated = expit(np.clip(odds, -40, 40)); change = float(np.max(abs(updated-rho))); rho = updated
        if change < 1e-5:
            break
    relative = (1-rho)/variances[0]+rho/variances[1]; result = gaussian(relative)
    logvariance = (1-rho)*np.log(variances[0])+rho*np.log(variances[1])
    gap = np.maximum(0., logvariance+np.log(relative))
    kl = np.maximum(0., 2*(xlogy(rho, rho/epsilon)+xlogy(1-rho, (1-rho)/(1-epsilon))))
    result['residual'] = np.r_[result['residual'], np.sqrt(gap), np.sqrt(kl)]
    result['objective'] += float(gap.sum()+kl.sum()); result['negative_twice_elbo'] = result['objective']
    result.update(glitch_probability=rho, final_mixture_change=change, mixture_iterations=epoch+1)
    return result


def attach_predictive_glitches(p, entries, powers, epsilon):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    curved = p.calculate
    def calculate(position):
        c = curved(position); g = p.noise_groups[p.keep]
        weights = np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:, None])
        geometry = geometry_features(view, position, 0.)
        mean = view.q*geometry['intercept']+geometry['features']@c['coefficient']
        root = np.linalg.cholesky(gram); uncertainty = np.linalg.solve(root, geometry['features'].T).T
        biases = np.eye(len(entries))[groups]*300
        prediction = predictive_glitch_bound(values-mean, np.column_stack((uncertainty, biases)), sigma*np.sqrt(2), epsilon)
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['linear_predictive_objective'] = prediction['objective']; c['negative_twice_elbo'] += prediction['objective']
        c['normalization_constant'] += prediction['normalization_constant']
        c['residual'] = np.r_[c['residual'], prediction['residual']]
        c['linear_raw_prediction_residual_hz'] = values-mean; c['linear_elevation'] = geometry['elevation']
        c['linear_glitch_probability'] = prediction['glitch_probability']
        c['linear_mixture_convergence'] = prediction['final_mixture_change']
        c['linear_calibration_coefficient_unchanged'] = True
        return c
    p.calculate, p.curved_calculate, p.linear_slices, p.linear_entries = calculate, curved, slices, entries
    return p


def glitch_bound(raw, features, sigma, owners, *, powers=1., prior_groups=None,
                 prior_nu=4., glitch_probability=.01, glitch_sd_ratio=10., iterations=256):
    y, u, owner = np.asarray(raw, float), np.asarray(features, float), np.asarray(owners)
    if not 0 <= glitch_probability < 1 or not np.isfinite(glitch_sd_ratio) or glitch_sd_ratio < 1:
        raise ValueError('probability in[0,1) and finite glitch SD ratio >=1 required')
    if glitch_probability == 0:
        result = observation_bound(y, u, sigma, owner, owner, powers=powers, prior_groups=prior_groups,
                                   prior_nu=prior_nu, iterations=iterations)
        result.update(glitch_probability=np.zeros(len(y)), point_relative_precision=np.ones(len(y)),
                      categorical_KL_cost=0., mixture_variance_gap_cost=0.)
        return result
    if (y.ndim != 1 or not len(y) or u.ndim != 2 or len(u) != len(y) or owner.shape != y.shape
            or not np.issubdtype(owner.dtype, np.integer) or np.any(owner < 0)):
        raise ValueError('matching nonempty measurements, features and integer owners required')
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if (not np.isfinite(y).all() or not np.isfinite(u).all() or not np.isfinite(s).all() or np.any(s <= 0)
            or not np.isfinite(prior_nu) or prior_nu <= 2 or iterations < 1):
        raise ValueError('finite inputs, positive scales and budget, prior degrees >2 required')
    _, g = np.unique(owner, return_inverse=True); counts, width = np.bincount(g), u.shape[1]
    power = np.broadcast_to(np.asarray(powers, float), counts.shape)
    if not np.isfinite(power).all() or np.any(power <= 0) or np.any(power > 1):
        raise ValueError('one power in(0,1] per fragment required')
    prior = np.full(width, -1, int) if prior_groups is None else np.asarray(prior_groups)
    if prior.shape != (width,) or not np.issubdtype(prior.dtype, np.integer) or np.any(prior < -1):
        raise ValueError('one prior group >=-1 per coefficient required')
    selected = prior >= 0; prior = prior.copy()
    _, inverse = np.unique(prior[selected], return_inverse=True); prior[selected] = inverse
    dimensions = np.bincount(inverse)
    alpha0 = beta0 = 2.; alpha = alpha0+power*counts/2
    pa0, pb0 = prior_nu/2, (prior_nu-2)/2; pa, v0 = pa0+dimensions/2, pa0/pb0
    rate, prior_rate = alpha.copy(), pa/v0
    epsilon, ratio2 = glitch_probability, glitch_sd_ratio**2
    variances = np.array([1., ratio2])/(1-epsilon+epsilon*ratio2)
    rho = np.full(len(y), epsilon); a, r = u/s[:, None], y/s
    blocks = []
    for k in range(len(counts)):
        ix = np.flatnonzero(g == k); cols = np.flatnonzero(np.any(a[ix] != 0, axis=0))
        blocks.append((ix, cols, a[np.ix_(ix, cols)]))

    def posterior(weight, relative, precision, covariance):
        gram, rhs = np.diag(precision), np.zeros(width)
        w = (power*weight)[g]*relative
        for ix, cols, local in blocks:
            gram[np.ix_(cols, cols)] += local.T@(local*w[ix, None]); rhs[cols] += local.T@(r[ix]*w[ix])
        root = np.linalg.cholesky(gram); mean = np.linalg.solve(root.T, np.linalg.solve(root, rhs)); cov = None
        if covariance:
            inverse_root = np.linalg.solve(root, np.eye(width)); cov = inverse_root.T@inverse_root
        return mean, cov, max(0., float(2*np.log(np.diag(root)).sum()-np.log(precision).sum()))

    history = []
    for _ in range(iterations):
        weight, v = alpha/rate, pa/prior_rate
        relative = (1-rho)/variances[0]+rho/variances[1]
        precision = np.ones(width); precision[selected] = v[prior[selected]]
        coefficient, covariance, _ = posterior(weight, relative, precision, True)
        native = (y-u@coefficient)/s; variance = np.zeros(len(y))
        for ix, cols, local in blocks:
            variance[ix] = np.sum((local@covariance[np.ix_(cols, cols)])*local, axis=1)
        energy = native**2+np.maximum(0., variance)
        next_rate = beta0+power*np.bincount(g, weights=relative*energy)/2
        prior_energy = np.bincount(prior[selected], weights=(coefficient**2+np.diag(covariance))[selected], minlength=len(dimensions))
        next_prior_rate = pb0+prior_energy/2
        logodds = np.log(epsilon/(1-epsilon))-.5*power[g]*np.log(ratio2)
        # Complete the Gamma coordinate update before the categorical update;
        # these two factors are dependent conditional on the Gaussian factor.
        logodds += .5*power[g]*(alpha/next_rate)[g]*energy*(1/variances[0]-1/variances[1])
        updated = expit(np.clip(logodds, -40, 40))
        change = max(float(np.max(abs(np.log(next_rate/rate)))),
            float(np.max(abs(np.log(next_prior_rate/prior_rate)), initial=0.)), float(np.max(abs(updated-rho))))
        rate, prior_rate, rho = next_rate, next_prior_rate, updated; history.append(change)
        if change < 1e-5:
            break
    weight, v = alpha/rate, pa/prior_rate
    relative = (1-rho)/variances[0]+rho/variances[1]
    precision = np.ones(width); precision[selected] = v[prior[selected]]
    coefficient, _, volume = posterior(weight, relative, precision, False)
    native = y-u@coefficient; innovation = native/s*np.sqrt((power*weight)[g]*relative)
    ratio = rate/beta0
    noise_gamma = np.maximum(0., 2*alpha*(np.log(ratio)+1/ratio-1))
    prior_gamma = np.maximum(0., 2*pa0*(np.log(v0/v)+v/v0-1))
    logvariance = (1-rho)*np.log(variances[0])+rho*np.log(variances[1])
    gap = np.maximum(0., power[g]*(logvariance+np.log(relative)))
    kl = 2*(xlogy(rho, rho/epsilon)+xlogy(1-rho, (1-rho)/(1-epsilon)))
    loggamma = np.vectorize(lgamma, otypes=[float])
    noise_constant = 2*lgamma(alpha0)-2*loggamma(alpha)+power*counts*np.log(beta0)
    prior_constant = 2*lgamma(pa0)-2*loggamma(pa)+dimensions*np.log(pa0)+2*pa*np.log(pa/pa0)-dimensions
    normalization = float(np.sum(power[g]*(np.log(2*np.pi)+2*np.log(s)-np.log(relative)))+
                          noise_constant.sum()+prior_constant.sum())
    residual = np.r_[innovation, coefficient*np.sqrt(precision), np.sqrt(volume), np.sqrt(noise_gamma),
                     np.sqrt(prior_gamma), np.sqrt(np.maximum(0., kl)), np.sqrt(gap)]
    return dict(residual=residual, coefficient=coefficient, quadratic=float(innovation@innovation+np.sum(precision*coefficient**2)),
        logvolume=volume, conditional_residual_hz=native, noise_precision=weight, coefficient_prior_precision=precision,
        prior_group_precision=v, noise_gamma_cost=float(noise_gamma.sum()), prior_gamma_cost=float(prior_gamma.sum()),
        gamma_cost=float(noise_gamma.sum()+prior_gamma.sum()), normalization_constant=normalization,
        negative_twice_elbo=float(residual@residual+normalization), effective_observations=float(power@counts),
        precision_iterations=len(history), final_log_precision_change=history[-1],
        glitch_probability=rho, point_relative_precision=relative, categorical_KL_cost=float(kl.sum()),
        mixture_variance_gap_cost=float(gap.sum()))


def make_glitch_problem(scan, node, mask, arm, reference, powers, means, hyper, entries, epsilon=.01, predictive_epsilon=0.):
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    owner = p.noise_groups.copy(); p.original_noise_groups = owner; p.noise_groups = np.arange(len(owner))
    point_powers = np.asarray(powers)[owner]
    begin = p.hardware.shape[1]+p.smooth.shape[1]; width = begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean = np.zeros(width); mean[begin:begin+len(p.labels)] = means/p.phase_sigma
    prior = np.full(width, -1, int)
    if hyper['nu'] is not None:
        prior[begin:begin+len(p.labels)] = np.arange(len(p.labels))
    scales = np.ones(width); scales[-len(p.members):] = .3
    def calculate(position):
        result = JointMarginal.calculate(p, position); features = result['features']
        raw = p.values-p.q*result['intercept']-features@mean; present = np.unique(owner[mask])
        bound = glitch_bound(raw[mask], (features*scales)[mask], p.point_noise[mask], owner[mask],
            powers=np.asarray(powers)[present], prior_groups=None if hyper['nu'] is None else prior,
            prior_nu=4 if hyper['nu'] is None else hyper['nu'], glitch_probability=epsilon)
        bound = scale_posterior(bound, scales)
        bound['latent_coefficient'] = bound['coefficient'].copy(); bound['coefficient'] += mean
        group_precision = np.zeros(len(p.members)); group_precision[present] = bound['noise_precision']
        precision = np.zeros(len(owner)); precision[mask] = group_precision[owner[mask]]*bound['point_relative_precision']
        bound['group_noise_precision'], bound['noise_precision'] = group_precision, precision
        probabilities = np.zeros(len(owner)); probabilities[mask] = bound['glitch_probability']; bound['glitch_probability'] = probabilities
        bound['conditional_residual_hz'] = p.values-p.q*result['intercept']-features@bound['coefficient']
        volume = float(2*np.sum(point_powers[mask]*np.log(p.point_noise[mask]/40)))
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        result.update(bound); return result
    p.calculate = calculate
    if predictive_epsilon:
        attach_predictive_glitches(p, entries, point_powers, predictive_epsilon)
    else:
        attach_predictive_linear(p, entries, point_powers)
    p.glitch_prior_probability = epsilon
    return p
