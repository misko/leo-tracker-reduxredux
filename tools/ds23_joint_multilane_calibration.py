"""Joint curved-component calibration with distinct per-lane RF covariance."""

import numpy as np

from ds23_frame_peak_recovery import polynomial_screen
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from ds23_multilane_prediction import condition_multiple, attach_multilane_prediction
from ds23_predictive_linear import linear_geometry, predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior


def joint_multilane_problem(d, arm, reference, extra_entries, correlated):
    scan, mask = d['enriched'], d['mask']
    powers, means, hyper = d['powers'], d['means'], d['hyper']
    p = make_event_problem(scan, d['node'], mask, arm, reference, powers, means, hyper, [])
    calibration, linear_extra, diagnostics = [], [], {}
    for entry in extra_entries:
        t = scan.tracks[entry['track_index']]; cov = d['covariance'][entry['component']]
        evidence = polynomial_screen(t['times'], t['values'], np.full(len(t['times']), cov['marginal_sigma_hz']))
        diagnostics[entry['component']] = evidence
        (calibration if evidence is not None else linear_extra).append(entry)
    p.joint_curvature_evidence = diagnostics
    p.joint_secondary_entries, p.joint_secondary_slices, p.joint_conditional_powers = calibration, [], []
    if not calibration:
        return attach_multilane_prediction(p, d['original_entries']+linear_extra, powers, d['anchors'], d['covariance'], correlated)
    view, values, _, groups, slices = linear_geometry(p, calibration)
    anchors = np.concatenate([d['anchors'][e['component']] for e in calibration]).astype(int)
    if np.any(~mask[anchors]) or len(set(anchors)) != len(anchors):
        raise ValueError('distinct original curved anchors required for conditional calibration')
    kappas, sigma = np.zeros(len(values)), np.zeros(len(values))
    new_powers = []
    for entry, sl in zip(calibration, slices, strict=True):
        cov = d['covariance'][entry['component']]; kappa = cov['kappa'] if correlated else 0.
        kappas[sl] = kappa; sigma[sl] = cov['marginal_sigma_hz']*np.sqrt(1-kappa*kappa)
        family = [powers[k] for k, (row, old_sl) in enumerate(zip(p.rows, p.slices, strict=True))
                  if row['candidate_index'] == entry['candidate_index'] and mask[old_sl].any()]
        new_powers.append(min(float(np.min(powers[p.noise_groups[anchors[sl]]])), min(family)))
    original_width = p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
    width = original_width+len(calibration)
    mean = np.zeros(width); phase_begin = p.hardware.shape[1]+p.smooth.shape[1]
    mean[phase_begin:phase_begin+len(p.labels)] = means/p.phase_sigma
    prior_groups = np.full(width, -1, int)
    if hyper['nu'] is not None:
        prior_groups[phase_begin:phase_begin+len(p.labels)] = np.arange(len(p.labels))
    scales = np.ones(width); scales[original_width-len(p.members):original_width] = .3
    biases = np.zeros((len(values), len(calibration))); biases[np.arange(len(values)), groups] = 300.
    present = np.unique(p.noise_groups[mask])
    all_powers = np.r_[powers[present], new_powers]
    noise_groups = np.r_[p.noise_groups[mask], len(p.members)+groups]
    sigmas = np.r_[p.point_noise[mask], sigma]
    _, mapped_groups = np.unique(noise_groups, return_inverse=True)
    volume = float(2*np.sum(powers[p.noise_groups[mask]]*np.log(p.point_noise[mask]/40)))
    def calculate(position):
        old = geometry_features(p, position, 0.)
        old_design = np.column_stack((old['features'], np.zeros((len(p.values), len(calibration)))))
        secondary = geometry_features(view, position, 0.)
        secondary_design = np.column_stack((secondary['features'], biases))
        y, design, intercept = condition_multiple(values, secondary_design, view.q*secondary['intercept'],
            p.values, old_design, p.q*old['intercept'], np.arange(len(values)), anchors, kappas)
        response = np.r_[p.values[mask]-p.q[mask]*old['intercept'][mask], y-intercept]
        features = np.vstack((old_design[mask], design))
        bound = hierarchical_bound(response-features@mean, features*scales, sigmas, noise_groups,
            powers=all_powers, prior_groups=None if hyper['nu'] is None else prior_groups,
            prior_nu=4 if hyper['nu'] is None else hyper['nu'])
        bound = scale_posterior(bound, scales)
        bound['latent_coefficient'] = bound['coefficient'].copy(); bound['coefficient'] += mean
        precision = bound['noise_precision'].copy()
        gram = np.diag(bound['coefficient_prior_precision'])+features.T@(features*((all_powers*precision)[mapped_groups]/sigmas**2)[:, None])
        original_precision = np.zeros(len(p.members)); original_precision[present] = precision[:len(present)]
        bound['noise_precision'] = original_precision
        bound['conditional_residual_hz'] = p.values-p.q*old['intercept']-old_design@bound['coefficient']
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        old.update(bound, features=old_design, joint_calibration_precision=gram,
            joint_secondary_conditional_raw_hz=y-intercept-design[:, :original_width]@bound['coefficient'][:original_width],
            joint_secondary_marginal_raw_hz=values-view.q*secondary['intercept']-secondary['features']@bound['coefficient'][:original_width],
            joint_secondary_fitted_residual_hz=y-intercept-design@bound['coefficient'],
            joint_secondary_elevation=secondary['elevation'], joint_secondary_noise_precision=precision[len(present):],
            joint_secondary_bias_hz=300*bound['coefficient'][original_width:])
        return old
    p.calculate = calculate
    p.joint_secondary_slices, p.joint_conditional_powers = slices, new_powers
    entries = d['original_entries']+linear_extra
    p.linear_entries, p.linear_slices = entries, []
    if entries:
        new_view, new_values, new_sigma, new_groups, new_slices = linear_geometry(p, entries)
        rows, original_anchors, loading = [], [], []
        new_sigma = new_sigma.copy()
        for entry, sl in zip(entries, new_slices, strict=True):
            key = entry['component']
            if key not in d['anchors']:
                continue
            cov = d['covariance'][key]; kappa = cov['kappa'] if correlated else 0.
            rows.extend(range(sl.start, sl.stop)); original_anchors.extend(d['anchors'][key]); loading.extend([kappa]*(sl.stop-sl.start))
            new_sigma[sl] = cov['marginal_sigma_hz']*np.sqrt(1-kappa*kappa)
        curved = p.calculate
        def predictive(position):
            c = curved(position); geometry = geometry_features(new_view, position, 0.)
            features = np.column_stack((geometry['features'], np.zeros((len(new_values), len(calibration)))))
            y, design, intercept = condition_multiple(new_values, features, new_view.q*geometry['intercept'],
                p.values, c['features'], p.q*c['intercept'], rows, original_anchors, loading)
            raw = y-intercept-design@c['coefficient']
            result = predictive_residual(raw, design, c['joint_calibration_precision'], new_sigma*np.sqrt(2), new_groups)
            c['curved_negative_twice_elbo'] = c['negative_twice_elbo']; c['negative_twice_elbo'] += result['objective']
            c['normalization_constant'] += result['normalization_constant']; c['residual'] = np.r_[c['residual'], result['residual']]
            c['linear_raw_prediction_residual_hz'] = raw; c['linear_elevation'] = geometry['elevation']
            c['linear_calibration_coefficient_unchanged'] = True
            return c
        p.calculate, p.curved_calculate = predictive, curved
        p.linear_slices = new_slices
    return p
