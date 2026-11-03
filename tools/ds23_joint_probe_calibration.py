"""Conditional calibration from independently curved simultaneous components.

Original observations, powers and nuisance priors remain in their original
slots. Only additional components passing RF-only active-curvature screens
enter calibration. All linear observations remain posterior-predictive only.
"""

import numpy as np

from ds23_frame_peak_recovery import polynomial_screen
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry, predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior


def curved_entries(scan, entries, covariance):
    curved, linear, diagnostics = [], [], {}
    for entry in entries:
        track = scan.tracks[entry['track_index']]
        sigma = np.full(len(track['times']), covariance['marginal_sigma_hz'])
        evidence = polynomial_screen(track['times'], track['values'], sigma)
        diagnostics[entry['component']] = evidence
        (curved if evidence is not None else linear).append(entry)
    return curved, linear, diagnostics


def conditional_block(values, features, intercept, primary_values, primary_features,
                      primary_intercept, anchors, kappa):
    anchors = np.asarray(anchors, int)
    y, u, b = np.asarray(values), np.asarray(features), np.asarray(intercept)
    if y.ndim != 1 or u.ndim != 2 or u.shape[0] != len(y) or b.shape != y.shape or anchors.shape != y.shape:
        raise ValueError('aligned secondary rows and curved anchors required')
    if not np.isfinite(kappa) or not 0 <= kappa < 1:
        raise ValueError('conditional loading must lie in [0,1)')
    return (y-kappa*np.asarray(primary_values)[anchors],
            u-kappa*np.asarray(primary_features)[anchors],
            b-kappa*np.asarray(primary_intercept)[anchors])


def joint_problem(scan, node, mask, arm, reference, powers, means, hyper,
                  original_entries, extra_entries, anchors, covariance, correlated):
    calibration, predictive_extra, diagnostics = curved_entries(scan, extra_entries, covariance)
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    if not calibration:
        raise ValueError('joint experiment requires independently active curved secondary evidence')
    kappa = covariance['kappa'] if correlated else 0.
    sigma_conditional = covariance['marginal_sigma_hz']*np.sqrt(1-kappa*kappa)
    view, values, _, groups, slices = linear_geometry(p, calibration)
    flat_anchors = np.concatenate([anchors[e['component']] for e in calibration]).astype(int)
    if np.any(~mask[flat_anchors]):
        raise ValueError('every conditional calibration row needs an original active curved anchor')
    original_width = p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
    width = original_width+len(calibration)
    mean = np.zeros(width)
    phase_begin = p.hardware.shape[1]+p.smooth.shape[1]
    mean[phase_begin:phase_begin+len(p.labels)] = means/p.phase_sigma
    prior_groups = np.full(width, -1, int)
    if hyper['nu'] is not None:
        prior_groups[phase_begin:phase_begin+len(p.labels)] = np.arange(len(p.labels))
    scales = np.ones(width)
    scales[original_width-len(p.members):original_width] = .3
    biases = np.zeros((len(values), len(calibration)))
    biases[np.arange(len(values)), groups] = 300.
    present = np.unique(p.noise_groups[mask])
    # Frozen old replication powers never change. A new conditional curve gets
    # the smaller existing power of its two nominated families/anchor owners.
    new_powers = []
    for entry, sl in zip(calibration, slices, strict=True):
        family = [powers[k] for k, (row, old_sl) in enumerate(zip(p.rows, p.slices, strict=True))
                  if row['candidate_index'] == entry['candidate_index'] and mask[old_sl].any()]
        primary = powers[p.noise_groups[flat_anchors[sl]]]
        new_powers.append(min(float(np.min(primary)), min(family)))
    all_powers = np.r_[powers[present], new_powers]
    noise_groups = np.r_[p.noise_groups[mask], len(p.members)+groups]
    sigma = np.r_[p.point_noise[mask], np.full(len(values), sigma_conditional)]
    volume = float(2*np.sum(powers[p.noise_groups[mask]]*np.log(p.point_noise[mask]/40)))

    def calculate(position):
        old = geometry_features(p, position, 0.)
        old_design = np.column_stack((old['features'], np.zeros((len(p.values), len(calibration)))))
        secondary = geometry_features(view, position, 0.)
        secondary_design = np.column_stack((secondary['features'], biases))
        y, design, intercept = conditional_block(values, secondary_design, view.q*secondary['intercept'],
            p.values, old_design, p.q*old['intercept'], flat_anchors, kappa)
        response = np.r_[p.values[mask]-p.q[mask]*old['intercept'][mask], y-intercept]
        full_design = np.vstack((old_design[mask], design))
        bound = hierarchical_bound(response-full_design@mean, full_design*scales, sigma, noise_groups,
            powers=all_powers, prior_groups=None if hyper['nu'] is None else prior_groups,
            prior_nu=4 if hyper['nu'] is None else hyper['nu'])
        bound = scale_posterior(bound, scales)
        bound['latent_coefficient'] = bound['coefficient'].copy()
        bound['coefficient'] += mean
        noise_precision = bound['noise_precision'].copy()
        weights = all_powers*noise_precision
        _, mapped_groups = np.unique(noise_groups, return_inverse=True)
        gram = np.diag(bound['coefficient_prior_precision'])+full_design.T@(full_design*(weights[mapped_groups]/sigma**2)[:, None])
        original_precision = np.zeros(len(p.members))
        original_precision[present] = noise_precision[:len(present)]
        bound['noise_precision'] = original_precision
        bound['conditional_residual_hz'] = p.values-p.q*old['intercept']-old_design@bound['coefficient']
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        conditional_raw = y-intercept-design[:, :original_width]@bound['coefficient'][:original_width]
        marginal_raw = values-view.q*secondary['intercept']-secondary['features']@bound['coefficient'][:original_width]
        conditional_fitted = y-intercept-design@bound['coefficient']
        old.update(bound, features=old_design, joint_calibration_precision=gram,
            joint_secondary_conditional_raw_hz=conditional_raw,
            joint_secondary_marginal_raw_hz=marginal_raw,
            joint_secondary_fitted_residual_hz=conditional_fitted,
            joint_secondary_elevation=secondary['elevation'], joint_secondary_noise_precision=noise_precision[len(present):],
            joint_secondary_bias_hz=300*bound['coefficient'][original_width:],
            shared_probe_kappa=kappa)
        return old

    p.calculate = calculate
    p.joint_secondary_entries, p.joint_secondary_slices = calibration, slices
    p.joint_curvature_evidence = diagnostics
    p.joint_conditional_powers = new_powers
    entries = original_entries+predictive_extra
    if entries:
        new_view, new_values, new_sigma, new_groups, new_slices = linear_geometry(p, entries)
        rows, ix = [], []
        for entry, sl in zip(entries, new_slices, strict=True):
            if entry['component'] in anchors:
                rows.extend(range(sl.start, sl.stop)); ix.extend(anchors[entry['component']])
        rows, ix = np.array(rows, int), np.array(ix, int)
        new_sigma = new_sigma.copy(); new_sigma[rows] = sigma_conditional
        calibration_calculate = p.calculate
        def predictive(position):
            c = calibration_calculate(position)
            geometry = geometry_features(new_view, position, 0.)
            features = np.column_stack((geometry['features'], np.zeros((len(new_values), len(calibration)))))
            y, design, intercept = new_values.copy(), features.copy(), new_view.q*geometry['intercept']
            y[rows] -= kappa*p.values[ix]
            design[rows] -= kappa*c['features'][ix]
            intercept[rows] -= kappa*p.q[ix]*c['intercept'][ix]
            raw = y-intercept-design@c['coefficient']
            prediction = predictive_residual(raw, design, c['joint_calibration_precision'], new_sigma*np.sqrt(2), new_groups)
            c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
            c['negative_twice_elbo'] += prediction['objective']
            c['normalization_constant'] += prediction['normalization_constant']
            c['residual'] = np.r_[c['residual'], prediction['residual']]
            c['linear_raw_prediction_residual_hz'] = raw
            c['linear_elevation'] = geometry['elevation']
            c['linear_calibration_coefficient_unchanged'] = True
            return c
        p.calculate, p.curved_calculate = predictive, calibration_calculate
        p.linear_entries, p.linear_slices = entries, new_slices
    else:
        p.linear_entries, p.linear_slices = [], []
    return p
