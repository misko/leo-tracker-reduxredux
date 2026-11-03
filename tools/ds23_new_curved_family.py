"""Conditional curved evidence for a family with a new causal phase coordinate.

Real added curves have dormant seed rows solely to instantiate their phase
coordinates. Their measurements enter once through conditional calibration;
the dormant rows have no likelihood weight. Original observations stay intact.
"""

import numpy as np
from ds23_frequency_events import make_event_problem
from ds23_predictive_linear import linear_geometry, predictive_residual, attach_predictive_linear
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior


def make_new_family_problem(d, arm, reference, include_new=True):
    p = make_event_problem(d['enriched'], d['node'], d['mask'], arm, reference,
                           d['powers'], d['means'], d['hyper'], [])
    extras = d['extra'] if include_new else []
    p.joint_secondary_entries, p.joint_secondary_slices, p.joint_conditional_powers = [], [], []
    p.linear_entries, p.linear_slices = d['original_entries'], []
    if not extras:
        return attach_predictive_linear(p, d['original_entries'], d['powers'])
    view, values, _, groups, slices = linear_geometry(p, extras)
    anchors = np.concatenate([d['anchors'][e['component']] for e in extras]).astype(int)
    if np.any(~d['mask'][anchors]) or len(set(anchors)) != len(anchors):
        raise ValueError('distinct original active curved anchors required')
    if np.any(d['mask'][d['original_flat_count']:]):
        raise ValueError('new family seed rows must be dormant; no double counting')
    kappas, sigma, newpowers = np.zeros(len(values)), np.zeros(len(values)), []
    for e, sl in zip(extras, slices, strict=True):
        covariance = d['covariance'][e['component']]
        kappas[sl] = covariance['kappa']; sigma[sl] = covariance['marginal_sigma_hz']*np.sqrt(1-covariance['kappa']**2)
        primary_power = float(np.min(d['powers'][p.noise_groups[anchors[sl]]]))
        newpowers.append(min(primary_power, d['new_family_powers'][e['candidate_index']]))
    width0 = p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
    width = width0+len(extras); phase_begin = p.hardware.shape[1]+p.smooth.shape[1]
    mean = np.zeros(width); mean[phase_begin:phase_begin+len(p.labels)] = d['means']/p.phase_sigma
    prior_groups = np.full(width, -1, int)
    if d['hyper']['nu'] is not None:
        prior_groups[phase_begin:phase_begin+len(p.labels)] = np.arange(len(p.labels))
    scales = np.ones(width); scales[width0-len(p.members):width0] = .3
    biases = np.eye(len(extras))[groups]*300
    present = np.unique(p.noise_groups[d['mask']])
    powers = np.r_[d['powers'][present], newpowers]
    noise_groups = np.r_[p.noise_groups[d['mask']], len(p.members)+groups]
    _, mapped = np.unique(noise_groups, return_inverse=True)
    sigmas = np.r_[p.point_noise[d['mask']], sigma]
    volume = float(2*np.sum(d['powers'][p.noise_groups[d['mask']]]*np.log(p.point_noise[d['mask']]/40)))
    def calculate(position):
        old = geometry_features(p, position, 0.)
        old_u = np.column_stack((old['features'], np.zeros((len(p.values), len(extras)))))
        new = geometry_features(view, position, 0.); new_u = np.column_stack((new['features'], biases))
        response = values-kappas*p.values[anchors]
        intercept = view.q*new['intercept']-kappas*p.q[anchors]*old['intercept'][anchors]
        design = new_u-kappas[:, None]*old_u[anchors]
        raw = np.r_[p.values[d['mask']]-p.q[d['mask']]*old['intercept'][d['mask']], response-intercept]
        features = np.vstack((old_u[d['mask']], design))
        bound = hierarchical_bound(raw-features@mean, features*scales, sigmas, noise_groups, powers=powers,
            prior_groups=None if d['hyper']['nu'] is None else prior_groups,
            prior_nu=4 if d['hyper']['nu'] is None else d['hyper']['nu'])
        bound = scale_posterior(bound, scales)
        bound['latent_coefficient'] = bound['coefficient'].copy(); bound['coefficient'] += mean
        precision = bound['noise_precision'].copy()
        gram = np.diag(bound['coefficient_prior_precision'])+features.T@(features*((powers*precision)[mapped]/sigmas**2)[:, None])
        original_precision = np.zeros(len(p.members)); original_precision[present] = precision[:len(present)]
        bound['noise_precision'] = original_precision
        bound['conditional_residual_hz'] = p.values-p.q*old['intercept']-old_u@bound['coefficient']
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        old.update(bound, features=old_u, joint_calibration_precision=gram,
            joint_secondary_conditional_raw_hz=response-intercept-design[:, :width0]@bound['coefficient'][:width0],
            joint_secondary_marginal_raw_hz=values-view.q*new['intercept']-new['features']@bound['coefficient'][:width0],
            joint_secondary_fitted_residual_hz=response-intercept-design@bound['coefficient'],
            joint_secondary_elevation=new['elevation'], joint_secondary_noise_precision=precision[len(present):],
            joint_secondary_bias_hz=300*bound['coefficient'][width0:])
        return old
    p.calculate = calculate
    p.joint_secondary_entries, p.joint_secondary_slices, p.joint_conditional_powers = extras, slices, newpowers
    if d['original_entries']:
        lv, ly, lsigma, lg, lsl = linear_geometry(p, d['original_entries']); curved = p.calculate
        def predictive(position):
            c = curved(position); geometry = geometry_features(lv, position, 0.)
            lu = np.column_stack((geometry['features'], np.zeros((len(ly), len(extras)))))
            raw = ly-lv.q*geometry['intercept']-lu@c['coefficient']
            prediction = predictive_residual(raw, lu, c['joint_calibration_precision'], lsigma*np.sqrt(2), lg)
            c['curved_negative_twice_elbo'] = c['negative_twice_elbo']; c['negative_twice_elbo'] += prediction['objective']
            c['normalization_constant'] += prediction['normalization_constant']; c['residual'] = np.r_[c['residual'], prediction['residual']]
            c['linear_raw_prediction_residual_hz'] = raw; c['linear_elevation'] = geometry['elevation']
            return c
        p.calculate, p.curved_calculate, p.linear_slices = predictive, curved, lsl
    return p
