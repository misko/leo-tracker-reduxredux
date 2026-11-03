"""Gaussian/Gamma calibration with noise groups separate from sparse owners.

One noise precision per point or short block preserves the original marginal
Gamma(2,2) noise prior. Sparse curve owners accelerate the same variational
updates; all observations and physical nuisance priors remain in the model.
"""

from math import lgamma
import numpy as np

from ds23_frequency_events import make_event_problem
from ds23_predictive_linear import attach_predictive_linear
from dsx01_joint_marginal import JointMarginal
from probe_ds23_receiver_smooth_prior import scale_posterior


def observation_bound(raw, features, sigma, groups, owners, *, powers=1., prior_groups=None,
                      noise_nu=4., prior_nu=4., iterations=256):
    y, u, original_groups, owner = np.asarray(raw, float), np.asarray(features, float), np.asarray(groups), np.asarray(owners)
    if (y.ndim != 1 or not len(y) or u.ndim != 2 or len(u) != len(y)
            or original_groups.shape != y.shape or owner.shape != y.shape
            or not np.issubdtype(original_groups.dtype, np.integer) or np.any(original_groups < 0)):
        raise ValueError('matching nonempty measurements, noise groups, and sparse owners required')
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if (not np.isfinite(y).all() or not np.isfinite(u).all() or not np.isfinite(s).all() or np.any(s <= 0)
            or not np.isfinite([noise_nu, prior_nu]).all() or noise_nu <= 0 or prior_nu <= 2 or iterations < 1):
        raise ValueError('finite data, positive scales and budgets, prior degrees >2 required')
    _, g = np.unique(original_groups, return_inverse=True)
    count, width = np.bincount(g), u.shape[1]
    power = np.broadcast_to(np.asarray(powers, float), count.shape)
    if not np.isfinite(power).all() or np.any(power <= 0) or np.any(power > 1):
        raise ValueError('one likelihood power in (0,1] per noise group required')
    prior = np.full(width, -1, int) if prior_groups is None else np.asarray(prior_groups)
    if prior.shape != (width,) or not np.issubdtype(prior.dtype, np.integer) or np.any(prior < -1):
        raise ValueError('one prior group >=-1 per coefficient required')
    selected = prior >= 0; prior = prior.copy()
    _, inverse = np.unique(prior[selected], return_inverse=True)
    prior[selected] = inverse; dimensions = np.bincount(inverse)
    alpha0 = beta0 = noise_nu/2; alpha = alpha0+power*count/2
    pa0, pb0 = prior_nu/2, (prior_nu-2)/2
    pa, v0 = pa0+dimensions/2, pa0/pb0
    rate, prior_rate = alpha.copy(), pa/v0
    a, r = u/s[:, None], y/s
    blocks = []
    for k in np.unique(owner):
        ix = np.flatnonzero(owner == k); cols = np.flatnonzero(np.any(a[ix] != 0, axis=0))
        blocks.append((ix, cols, a[np.ix_(ix, cols)]))

    def posterior(weight, precision, covariance):
        gram, rhs = np.diag(precision), np.zeros(width)
        w = (power*weight)[g]
        for ix, cols, local in blocks:
            gram[np.ix_(cols, cols)] += local.T@(local*w[ix, None])
            rhs[cols] += local.T@(r[ix]*w[ix])
        root = np.linalg.cholesky(gram)
        mean = np.linalg.solve(root.T, np.linalg.solve(root, rhs)); cov = None
        if covariance:
            inverse_root = np.linalg.solve(root, np.eye(width)); cov = inverse_root.T@inverse_root
        volume = max(0., float(2*np.log(np.diag(root)).sum()-np.log(precision).sum()))
        return mean, cov, volume

    history = []
    for _ in range(iterations):
        weight, v = alpha/rate, pa/prior_rate
        precision = np.ones(width); precision[selected] = v[prior[selected]]
        coefficient, covariance, _ = posterior(weight, precision, True)
        native = (y-u@coefficient)/s; variance = np.zeros(len(y))
        for ix, cols, local in blocks:
            variance[ix] = np.sum((local@covariance[np.ix_(cols, cols)])*local, axis=1)
        energy = np.bincount(g, weights=native**2+np.maximum(0., variance))
        next_rate = beta0+power*energy/2
        prior_energy = np.bincount(prior[selected], weights=(coefficient**2+np.diag(covariance))[selected],
                                   minlength=len(dimensions))
        next_prior_rate = pb0+prior_energy/2
        change = max(float(np.max(abs(np.log(next_rate/rate)))),
                     float(np.max(abs(np.log(next_prior_rate/prior_rate)), initial=0.)))
        rate, prior_rate = next_rate, next_prior_rate; history.append(change)
        if change < 1e-5:
            break
    weight, v = alpha/rate, pa/prior_rate
    precision = np.ones(width); precision[selected] = v[prior[selected]]
    coefficient, _, volume = posterior(weight, precision, False)
    native = y-u@coefficient; innovation = native/s*np.sqrt((power*weight)[g])
    ratio = rate/beta0
    noise_gamma = np.maximum(0., 2*alpha*(np.log(ratio)+1/ratio-1))
    prior_gamma = np.maximum(0., 2*pa0*(np.log(v0/v)+v/v0-1))
    loggamma = np.vectorize(lgamma, otypes=[float])
    noise_constant = 2*lgamma(alpha0)-2*loggamma(alpha)+power*count*np.log(beta0)
    prior_constant = 2*lgamma(pa0)-2*loggamma(pa)+dimensions*np.log(pa0)+2*pa*np.log(pa/pa0)-dimensions
    normalization = float(np.sum(power[g]*(np.log(2*np.pi)+2*np.log(s)))+noise_constant.sum()+prior_constant.sum())
    residual = np.r_[innovation, coefficient*np.sqrt(precision), np.sqrt(volume), np.sqrt(noise_gamma), np.sqrt(prior_gamma)]
    return dict(residual=residual, coefficient=coefficient, quadratic=float(innovation@innovation+np.sum(precision*coefficient**2)),
        logvolume=volume, conditional_residual_hz=native, noise_precision=weight, coefficient_prior_precision=precision,
        prior_group_precision=v, noise_gamma_cost=float(noise_gamma.sum()), prior_gamma_cost=float(prior_gamma.sum()),
        gamma_cost=float(noise_gamma.sum()+prior_gamma.sum()), normalization_constant=normalization,
        negative_twice_elbo=float(residual@residual+normalization), effective_observations=float(power@count),
        precision_iterations=len(history), final_log_precision_change=history[-1])


def noise_partition(owners, block_points):
    owners = np.asarray(owners)
    if block_points is not None and (not isinstance(block_points, int) or block_points < 1):
        raise ValueError('positive integer block size or None for whole fragments required')
    groups = np.zeros(len(owners), int); offset = 0
    for k in np.unique(owners):
        ix = np.flatnonzero(owners == k)
        local = np.zeros(len(ix), int) if block_points is None else np.arange(len(ix))//block_points
        groups[ix] = offset+local; offset += int(local.max())+1
    return groups


def make_observation_noise_problem(scan, node, mask, arm, reference, powers, means, hyper, entries, block_points):
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    owners = p.noise_groups.copy(); p.original_noise_groups = owners
    p.noise_groups = noise_partition(owners, block_points)
    new_powers = np.zeros(int(p.noise_groups.max())+1)
    for group in np.unique(p.noise_groups):
        original = np.unique(owners[p.noise_groups == group])
        if len(original) != 1:
            raise ValueError('noise group crosses original fragment')
        new_powers[group] = powers[original[0]]
    begin = p.hardware.shape[1]+p.smooth.shape[1]
    width = begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean = np.zeros(width); mean[begin:begin+len(p.labels)] = means/p.phase_sigma
    prior_groups = np.full(width, -1, int)
    if hyper['nu'] is not None:
        prior_groups[begin:begin+len(p.labels)] = np.arange(len(p.labels))
    scale = np.ones(width); scale[-len(p.members):] = .3
    def calculate(position):
        result = JointMarginal.calculate(p, position); features = result['features']
        raw = p.values-p.q*result['intercept']-features@mean
        present = np.unique(p.noise_groups[mask])
        bound = observation_bound(raw[mask], (features*scale)[mask], p.point_noise[mask],
            p.noise_groups[mask], owners[mask], powers=new_powers[present],
            prior_groups=None if hyper['nu'] is None else prior_groups, prior_nu=4 if hyper['nu'] is None else hyper['nu'])
        bound = scale_posterior(bound, scale)
        bound['latent_coefficient'] = bound['coefficient'].copy(); bound['coefficient'] += mean
        precision = np.zeros(len(new_powers)); precision[present] = bound['noise_precision']; bound['noise_precision'] = precision
        bound['conditional_residual_hz'] = p.values-p.q*result['intercept']-features@bound['coefficient']
        volume = float(2*np.sum(new_powers[p.noise_groups[mask]]*np.log(p.point_noise[mask]/40)))
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        result.update(bound); return result
    p.calculate = calculate
    attach_predictive_linear(p, entries, new_powers)
    p.point_noise_powers = new_powers; p.noise_block_points = block_points
    return p
