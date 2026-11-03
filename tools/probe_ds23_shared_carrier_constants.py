"""Matched physical satellite-carrier versus independent fragment-bias controls."""

import argparse
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_heteroscedastic_gates import metrics
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_cross_rf_constants import cross_rf_correlation
from probe_ds23_dense_receiver_prediction import context as dense_context, expand, OUT as PREDICTION
from probe_ds23_history_calibrated_phase import OUT as LEARNED, make_problem
from probe_ds23_refined_eccentricity import eccentric_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, final_scan, read, write, sha

OUT = ROOT / 'reports/2026_10_19_ds23_shared_carrier_constants'
MODES = ('independent', 'old_rho90', 'shared100', 'shared30')


def constant_covariance(labels, rf_hz, mode):
    labels, rf = np.asarray(labels), np.asarray(rf_hz, float)
    if mode not in MODES or labels.ndim != 1 or rf.shape != labels.shape or not len(rf) or not np.isfinite(rf).all() or np.any(rf <= 0):
        raise ValueError('known hypothesis and matching positive finite RF/family vectors required')
    if mode == 'independent':
        return np.eye(len(labels)) * 300**2
    if mode == 'old_rho90':
        return cross_rf_correlation(labels, rf, .9) * 300**2
    delta = 100 if mode == 'shared100' else 30
    q = rf / 11.5e9
    return np.eye(len(labels)) * delta**2 + (labels[:, None] == labels[None, :]) * (300**2 * np.outer(q, q))


def apply_covariance(p, covariance):
    """Existing 1000-Hz columns and .3 prior scaling yield the requested K."""
    c = np.asarray(covariance, float)
    n = len(p.members)
    if c.shape != (n, n) or not np.isfinite(c).all() or not np.allclose(c, c.T, atol=1e-9, rtol=1e-12):
        raise ValueError('finite symmetric covariance for every original fragment required')
    transform = np.linalg.cholesky(c) / 300
    p.constants = p.constants @ transform
    return transform


def context(case, scope, receiver):
    if scope == 'dense':
        scan, node, keep, powers, noise, radio, model, means = dense_context(case)
        baseline = read(PREDICTION / (case + '_' + receiver + '.json'))['arms']
    elif scope == 'incumbent' and receiver == 'baseline':
        scan = final_scan(case)
        node = read(SOURCE / case / 'result.json')['final_node']
        learned = read(LEARNED / (case + '.json'))
        prior = learned['results']['mean_and_distribution']
        keep = np.array(prior['mask'], bool)
        model = learned['hyperparameters_from_pre_RF_TLE_only']
        powers = np.array(read(WEIGHTS / case / 'result.json')['results']['cross_rx_support']['weights'])
        p = problem(scan, node, 'c0', keep)
        _, receipts = phase_widths(scan, p.labels)
        means = forecast_phase_mean(receipts, model['shrinkage'])
        noise, radio, baseline = {}, [], prior['arms']
    else:
        raise ValueError('incumbent comparison keeps its original receiver design')
    scan, node = expand(scan, node, receiver)
    return scan, node, keep, powers, noise, radio, model, means, baseline


def refit(scan, node, keep, powers, noise, model, means, arm, mode, scope):
    reference = np.zeros(len(means))
    x = np.zeros(2)
    history = []
    for _ in range(5):
        if scope == 'dense':
            p = eccentric_problem(scan, node, keep, arm, reference, powers, means, model, noise)
        else:
            p = make_problem(scan, node, keep, arm, reference, powers, means, model['multiplier'], model['nu'])
        labels = [r['candidate_index'] for r in p.rows]
        rf = [scan.tracks[i]['rf_hz'] for i in p.members]
        covariance = constant_covariance(labels, rf, mode)
        transform = apply_covariance(p, covariance)
        r = fit(p, x, iterations=48)
        x = np.array(r['parameters'])
        history.append(r)
        reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
    c = p.calculate(x)
    biases = 1000 * transform @ c['coefficient'][-len(p.members):]
    tracks = []
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        active = keep[sl]
        if not active.any():
            continue
        t = scan.tracks[i]
        tracks.append(dict(track=t['key'], receiver=t['receiver'], channel=t['channel'], rf_hz=t['rf_hz'],
            norad=row['candidate_norad'], points=int(active.sum()), time_s=t['times'][active],
            sigma_hz=p.point_noise[sl][active], posterior_fragment_bias_hz=float(biases[k]),
            conditional_residual_hz=c['conditional_residual_hz'][sl][active]))
    gates = metrics(p, x) if scope == 'dense' else retained_metrics(p, x)
    return dict(endpoint_east_north_km=x, endpoint_latlon=latlon(x), history=history, state=p.state(x),
        phase_reference=p.reference, negative_twice_elbo=c['negative_twice_elbo'], active_points=int(keep.sum()),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))), gates=gates, tracks=tracks,
        constant_covariance_hz2=covariance, posterior_fragment_bias_hz=biases)


def run(case, scope, receiver):
    scan, node, keep, powers, noise, radio, model, means, baseline = context(case, scope, receiver)
    directory = OUT / scope / receiver
    directory.mkdir(parents=True, exist_ok=True)
    results = {'independent': dict(arms=baseline, paired_valid=True, frozen_reference=True)}
    for mode in MODES[1:]:
        pair = {arm: refit(scan, node, keep, powers, noise, model, means, arm, mode, scope) for arm in ('c0', 'fitted_c')}
        valid = all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
        results[mode] = dict(arms=pair, paired_valid=valid)
        write(directory / (case + '_partial.json'), dict(case=case, results=results))
        print(case, scope, receiver, mode, 'paired valid', valid, 'c0 RF loss', round(pair['c0']['negative_twice_elbo'], 3), flush=True)
    selected = min((m for m in results if results[m]['paired_valid']), key=lambda m: results[m]['arms']['c0']['negative_twice_elbo'])
    write(directory / (case + '.json'), dict(case=case, scope=scope, receiver=receiver, results=results,
        selected=selected, selected_arms=results[selected]['arms'], mask=keep, radio_noise_receipts=radio,
        source_sha256=sha(Path(__file__)), learned_prior_sha256=sha(LEARNED / (case + '.json')),
        same_observations_noise_aliases_identities_and_other_priors=True,
        c_pair_has_identical_data_and_model_choice=True, no_GPS_used=True, no_point_removed=True,
        shared_carrier_prior_sigma_hz=300, reference_RF_hz=11.5e9,
        hypotheses_are_engineering_priors_not_fitted_to_GPS=True,
        full_pair_budget=dict(phase_rounds=5, position_steps=48, cold_start=[0, 0]),
        selection='minimum normalized c0 negative_twice_ELBO among paired-gate-passing hypotheses'))
    print(case, scope, receiver, 'RF selected', selected, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--scope', choices=['dense', 'incumbent'], required=True)
    parser.add_argument('--receiver', choices=['baseline', 'fast_rx1'], default='baseline')
    args = parser.parse_args()
    run(args.case, args.scope, args.receiver)
