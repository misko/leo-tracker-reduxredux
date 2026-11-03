"""Shared Gaussian satellite carriers with heavy-tailed fragment deviations."""

import argparse
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_heteroscedastic_gates import metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_structured_joint import eccentricity_bank
from ds23_robust_carrier_prior import prior_groups
from investigate_dsx01_localization_failures import fit
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_refined_eccentricity import eccentric_problem, extra_columns
from probe_ds23_shared_carrier_constants import OUT as GAUSSIAN, context
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes

OUT = ROOT / 'reports/2026_10_19_ds23_robust_carrier_constants'


def bias_columns(labels, q, groups, families, fragments, delta):
    labels, q, groups = np.asarray(labels), np.asarray(q, float), np.asarray(groups)
    if labels.ndim != 1 or q.shape != labels.shape or groups.shape != labels.shape or not np.isfinite(q).all() or np.any(q <= 0) or delta <= 0:
        raise ValueError('matching positive finite RF scales and bias identities required')
    if not np.issubdtype(labels.dtype, np.integer) or not np.issubdtype(groups.dtype, np.integer) or np.any(labels < 0) or np.any(labels >= families) or np.any(groups < 0) or np.any(groups >= fragments):
        raise ValueError('family and fragment coordinates must be in range')
    return np.eye(families)[labels]*q[:, None]*300, np.eye(fragments)[groups]*delta


def extend(p, means, model, powers, delta, scope):
    if model['nu'] not in (None, 3.):
        raise ValueError('keep phase prior unchanged: this prototype supports Gaussian or nu3 phase')
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    m, labels = len(p.members), len(p.labels)
    shared, independent = bias_columns(p.flat_labels, p.q, p.noise_groups, labels, m, delta)
    eccentric = eccentricity_bank(p.scan, p.labels, p.supported)[0] if scope == 'dense' else None
    active = np.bincount(p.noise_groups[p.keep], minlength=m) > 0
    def calculate(x):
        # Build the existing geometry directly; avoid solving and discarding an
        # entire old Gamma posterior before solving the new one.
        c = JointMarginal.calculate(p, x)
        if eccentric is not None:
            modes = paired_frequency_modes(p.sky, eccentric, p.flat_times, p.flat_labels, p.reference, *latlon(x[:2]))
            extra = extra_columns(p.flat_labels, p.q, modes, p.supported_local)
            stop = c['features'].shape[1]-m
            c['features'] = np.column_stack((c['features'][:, :stop], extra, c['features'][:, stop:]))
        clock_begin = c['features'].shape[1]-m
        features = np.column_stack((c['features'][:, :clock_begin], shared, independent))
        mean = np.zeros(features.shape[1])
        mean[begin:begin+labels] = means/p.phase_sigma
        groups = prior_groups(features.shape[1], begin, labels, active, model['nu'])
        present = np.unique(p.noise_groups[p.keep])
        raw = p.values-p.q*c['intercept']-features@mean
        b = hierarchical_bound(raw[p.keep], features[p.keep], p.point_noise[p.keep], p.noise_groups[p.keep],
            powers=powers[present], prior_groups=groups, prior_nu=3.)
        b['latent_coefficient'] = b['coefficient'].copy()
        b['coefficient'] += mean
        precision = np.zeros(m)
        precision[present] = b['noise_precision']
        b['noise_precision'] = precision
        b['conditional_residual_hz'] = p.values-p.q*c['intercept']-features@b['coefficient']
        reference_hz = 1 if scope == 'dense' else 40
        volume = 2*np.sum(powers[p.noise_groups[p.keep]]*np.log(p.point_noise[p.keep]/reference_hz))
        b['residual'] = np.r_[b['residual'], np.sqrt(volume)]
        c.update(b, features=features, shared_carrier_begin=clock_begin)
        return c
    def conditional_frequency(x):
        c = calculate(x)
        # Keep the old gate accounting: profile the TOTAL frequency bias per fragment.
        stop = c['shared_carrier_begin']
        return c['intercept']+c['features'][:, begin:stop]@c['coefficient'][begin:stop]/p.q, c['elevation']
    p.calculate, p.conditional_frequency = calculate, conditional_frequency
    return p


def refit(scan, node, keep, powers, noise, model, means, arm, delta, scope):
    reference, x, history = np.zeros(len(means)), np.zeros(2), []
    for _ in range(5):
        p = (eccentric_problem(scan, node, keep, arm, reference, powers, means, model, noise) if scope == 'dense'
             else make_problem(scan, node, keep, arm, reference, powers, means, model['multiplier'], model['nu']))
        p = extend(p, means, model, powers, delta, scope)
        r = fit(p, x, iterations=48)
        x = np.array(r['parameters'])
        history.append(r)
        reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
    c = p.calculate(x)
    m, clock = len(p.members), c['shared_carrier_begin']
    shared = c['coefficient'][clock:clock+len(p.labels)]*300
    contrasts = c['coefficient'][-m:]*delta
    tracks = []
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        active, t = keep[sl], scan.tracks[i]
        if active.any():
            tracks.append(dict(track=t['key'], norad=row['candidate_norad'], receiver=t['receiver'], channel=t['channel'],
                points=int(active.sum()), time_s=t['times'][active], sigma_hz=p.point_noise[sl][active],
                shared_carrier_reference_hz=float(shared[p.labels.index(row['candidate_index'])]),
                fragment_contrast_hz=float(contrasts[k]), contrast_precision=float(c['coefficient_prior_precision'][-m+k]),
                conditional_residual_hz=c['conditional_residual_hz'][sl][active]))
    return dict(endpoint_east_north_km=x, endpoint_latlon=latlon(x), history=history, state=p.state(x),
        phase_reference=p.reference, negative_twice_elbo=c['negative_twice_elbo'], active_points=int(keep.sum()),
        gates=metrics(p, x) if scope == 'dense' else retained_metrics(p, x), tracks=tracks,
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        shared_carrier_reference_hz=shared, fragment_contrast_hz=contrasts,
        contrast_precision=c['coefficient_prior_precision'][-m:], delta_sigma_hz=delta,
        contrast_nu=3, phase_prior_unchanged=True)


def run(case, scope, receiver):
    scan, node, keep, powers, noise, radio, model, means, base = context(case, scope, receiver)
    gaussian_path = GAUSSIAN/scope/receiver/(case+'.json')
    gaussian = read(gaussian_path)
    results = dict(gaussian['results'])
    directory = OUT/scope/receiver
    directory.mkdir(parents=True, exist_ok=True)
    for delta in (100, 30):
        mode = 'robust'+str(delta)
        pair = {arm: refit(scan, node, keep, powers, noise, model, means, arm, delta, scope) for arm in ('c0', 'fitted_c')}
        valid = all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
        results[mode] = dict(arms=pair, paired_valid=valid)
        write(directory/(case+'_partial.json'), dict(case=case, results=results))
        print(case, scope, receiver, mode, 'valid', valid, 'c0 RF loss', round(pair['c0']['negative_twice_elbo'], 3), flush=True)
    chosen = min((m for m, r in results.items() if r['paired_valid']), key=lambda m:results[m]['arms']['c0']['negative_twice_elbo'])
    write(directory/(case+'.json'), dict(case=case, scope=scope, receiver=receiver, results=results, selected=chosen,
        selected_arms=results[chosen]['arms'], mask=keep, source_sha256=sha(Path(__file__)),
        gaussian_reference_sha256=sha(gaussian_path), no_GPS_used=True, no_point_removed=True,
        same_data_aliases_masks_noise_identities_and_other_priors=True,
        phase_prior_unchanged=True, contrast_nu=3, shared_carrier_sigma_hz=300,
        inactive_independent_contrast_priors_collapsed_exactly=True,
        mode_selection_uses_normalized_c0_RF_loss_and_paired_gates=True,
        full_pair_five_phase_rounds_48_steps_from_regional_center=True))
    print(case, scope, receiver, 'RF selected', chosen, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--scope', choices=['dense', 'incumbent'], required=True)
    parser.add_argument('--receiver', choices=['baseline', 'fast_rx1'], default='baseline')
    args = parser.parse_args()
    run(args.case, args.scope, args.receiver)
