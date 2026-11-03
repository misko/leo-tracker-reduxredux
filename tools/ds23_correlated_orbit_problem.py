"""Coupled phase/shape priors with unchanged native physical coordinates.

The first latent coordinate in each block retains the existing phase Student
prior. The three conditional shape coordinates remain Gaussian. Added-track
prediction uses the full native prior precision, including off-diagonals.
"""

import numpy as np
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry, predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem


def prior_transform(begin, labels, supported, members, correlation):
    correlation = np.asarray(correlation, float)
    if correlation.shape != (4,4) or not np.allclose(np.diag(correlation), 1.):
        raise ValueError("four-dimensional unit-diagonal phase/shape correlation required")
    if not np.allclose(correlation, correlation.T) or not np.isfinite(correlation).all():
        raise ValueError("finite symmetric correlation required")
    root = np.linalg.cholesky(correlation)
    width = begin+len(labels)+3*len(supported)+members
    transform = np.eye(width)
    for index, candidate in enumerate(supported):
        indices = [begin+labels.index(candidate), *range(begin+len(labels)+3*index, begin+len(labels)+3*index+3)]
        transform[np.ix_(indices, indices)] = root
    transform[:,-members:] *= .3
    return transform


def native_posterior(mean, transform, latent, prior_precision):
    inverse = np.linalg.solve(transform, np.eye(len(transform)))
    precision = inverse.T@(np.asarray(prior_precision)[:,None]*inverse)
    return np.asarray(mean)+transform@latent, precision


def make_correlated_problem(scan, node, keep, arm, reference, powers, means, model, correlation):
    p = make_problem(scan, node, keep, arm, reference, powers, means, model["multiplier"], model["nu"])
    begin = p.hardware.shape[1]+p.smooth.shape[1]
    transform = prior_transform(begin, p.labels, p.supported, len(p.members), correlation)
    inverse = np.linalg.solve(transform, np.eye(len(transform)))
    width = len(transform)
    mean = np.zeros(width)
    mean[begin:begin+len(p.labels)] = means/p.phase_sigma
    prior_groups = np.full(width, -1, int)
    if model["nu"] is not None:
        prior_groups[begin:begin+len(p.labels)] = np.arange(len(p.labels))
    def calculate(position):
        geometry = geometry_features(p, position, 0.)
        features = geometry["features"]
        raw = p.values-p.q*geometry["intercept"]-features@mean
        present = np.unique(p.noise_groups[keep])
        bound = hierarchical_bound(raw[keep], (features@transform)[keep], p.point_noise[keep],
            p.noise_groups[keep], powers=powers[present], prior_groups=prior_groups,
            prior_nu=model["nu"] or 4.)
        latent = bound["coefficient"].copy()
        latent_precision = bound["coefficient_prior_precision"].copy()
        native_precision = inverse.T@(latent_precision[:,None]*inverse)
        bound["coefficient"] = mean+transform@latent
        bound["latent_coefficient"] = transform@latent
        bound["coefficient_prior_matrix"] = native_precision
        bound["coefficient_prior_precision"] = np.diag(native_precision).copy()
        bound["native_prior_is_diagonal"] = bool(np.allclose(native_precision, np.diag(np.diag(native_precision))))
        bound["latent_prior_penalty"] = float(np.sum(latent**2*latent_precision))
        precision = np.zeros(len(p.members))
        precision[present] = bound["noise_precision"]
        bound["noise_precision"] = precision
        bound["conditional_residual_hz"] = p.values-p.q*geometry["intercept"]-features@bound["coefficient"]
        volume = float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound["residual"] = np.r_[bound["residual"], np.sqrt(volume)]
        geometry.update(bound)
        return geometry
    p.calculate = calculate
    p.phase_shape_correlation = correlation
    return p


def attach_correlated_prediction(p, entries, powers):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    curved_calculate = p.calculate
    def calculate(position):
        c = curved_calculate(position)
        g = p.noise_groups[p.keep]
        weight = np.asarray(powers)[g]*c["noise_precision"][g]/p.point_noise[p.keep]**2
        design = c["features"][p.keep]
        gram = c["coefficient_prior_matrix"]+design.T@(design*weight[:,None])
        geometry = geometry_features(view, position, 0.)
        mean = view.q*geometry["intercept"]+geometry["features"]@c["coefficient"]
        prediction = predictive_residual(values-mean, geometry["features"], gram, sigma*np.sqrt(2), groups)
        c["curved_negative_twice_elbo"] = c["negative_twice_elbo"]
        c["linear_predictive_objective"] = prediction["objective"]
        c["negative_twice_elbo"] += prediction["objective"]
        c["normalization_constant"] += prediction["normalization_constant"]
        c["residual"] = np.r_[c["residual"], prediction["residual"]]
        c["linear_raw_prediction_residual_hz"] = values-mean
        c["linear_elevation"] = geometry["elevation"]
        return c
    p.calculate = calculate
    p.curved_calculate = curved_calculate
    p.linear_entries = entries
    p.linear_slices = slices
    return p
