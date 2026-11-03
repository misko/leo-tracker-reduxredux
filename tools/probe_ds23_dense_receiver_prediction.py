"""Predict omitted RX/family evidence using precise CFOs and complete orbit modes."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_heteroscedastic_gates import metrics
from ds23_measurement_noise import learn_local_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_band_covariance import split_basis
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_receiver_positions import merge_measurements
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE
from probe_ds23_refined_precision import OUT as PRECISE
from probe_ds23_refined_timestamps import apply_effective_times
from probe_ds23_receiver_prediction import gaussian_score
from prototype_dsx01_continuous_position import latlon
from refine_ds23_receiver_panel import OUT as DENSE
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, final_scan, read, write, sha
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis

OUT = ROOT / 'reports/2026_10_19_ds23_dense_receiver_prediction'
METHODS = ('baseline', 'fast_rx1', 'fast_both', 'fast_band_half')


def context(case):
    old = copy.deepcopy(read(RAW / (case + '_tracks.json')))
    companion = read(RAW / (case + '_companion.json'))
    old['rows'] += companion['rows']
    old['panel_metadata']['tracks'] += companion['panel_metadata']['tracks']
    data = merge_measurements(old, read(DENSE / (case + '_broad_refined.json')))
    noise, radio = learn_local_noise(data)
    scan = final_scan(case)
    catalogue = read(CATALOGUE / (case + '_companion.json'))
    node = changed_node(scan, read(SOURCE / case / 'result.json')['final_node'], catalogue['chosen']['proposal']['changes'])
    keep = np.array(read(PRECISE / (case + '_family.json'))['mask'], bool)
    model = read(LEARNED / (case + '.json'))['hyperparameters_from_pre_RF_TLE_only']
    powers = np.array(read(WEIGHTS / case / 'result.json')['results']['cross_rx_support']['weights'])
    update_values(scan, data['rows'], 'joint_CFO_epoch_rate')
    apply_effective_times(scan, data['rows'])
    p = problem(scan, node, 'c0', keep)
    _, receipts = phase_widths(scan, p.labels)
    means = forecast_phase_mean(receipts, model['shrinkage'])
    return scan, node, keep, powers, noise, radio, model, means


def expand(scan, node, method):
    if method not in METHODS:
        raise ValueError('unknown frozen receiver covariance hypothesis')
    if method == 'baseline':
        return scan, node
    changed, seed = copy.copy(scan), copy.deepcopy(node)
    basis = []
    for track, slow in zip(scan.tracks, scan.rx_basis, strict=True):
        # The shared model multiplies this basis by 200 Hz later.
        fast = projected_receiver_basis(track['times'], spacing_s=10, width_s=5) * .5
        if method == 'fast_rx1' and track['receiver'] != 1:
            fast *= 0
        if method == 'fast_band_half':
            fast = split_basis(fast, int(track['channel'] > 4), .5)
        basis.append(np.column_stack((slow, fast)))
    changed.rx_basis = basis
    old = np.asarray(seed['seed']['state']['smooth'])
    seed['seed']['state']['smooth'] = np.column_stack((old, np.zeros((2, basis[0].shape[1] - old.shape[1]))))
    return changed, seed


def folds(p, keep, maximum=3):
    candidates = []
    for j in p.labels:
        owners = {p.scan.tracks[i]['receiver'] for row, i, sl in zip(p.rows, p.members, p.slices, strict=True)
            if row['candidate_index'] == j and keep[sl].any()}
        count = sum(int(keep[sl].sum()) for row, sl in zip(p.rows, p.slices, strict=True) if row['candidate_index'] == j)
        if owners == {1, 2}:
            candidates.append((count, j))
    result = []
    for _, j in sorted(candidates, key=lambda r: (-r[0], r[1]))[:maximum]:
        for rx in (1, 2):
            test = np.zeros(len(keep), bool)
            for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
                if row['candidate_index'] == j and p.scan.tracks[i]['receiver'] == rx:
                    test[sl] = keep[sl]
            result.append(dict(family=j, receiver=rx, train=keep & ~test, test=test))
    return result


def derivative(p, x, coefficient, step=.01):
    """Freeze posterior coefficients but include every current feature column."""
    columns = []
    for k in (0, 1):
        delta = np.zeros(2)
        delta[k] = step
        values = []
        for position in (x + delta, x - delta):
            c = p.calculate(position)
            if c['features'].shape[1] != len(coefficient):
                raise ValueError('complete current feature coordinates required')
            values.append(p.q * c['intercept'] + c['features'] @ coefficient)
        columns.append((values[0] - values[1]) / (2 * step))
    return np.column_stack(columns)


def predictive(p, x, train, test, powers, held_family):
    if np.any(train & test) or not test.any() or not np.array_equal(p.keep, train):
        raise ValueError('disjoint training/test observations and training-only posterior required')
    if not np.any(train & (p.flat_labels == p.labels.index(held_family))):
        raise ValueError('held family needs opposite-receiver training evidence')
    c = p.calculate(x)
    d = derivative(p, x, c['coefficient'])
    full = np.column_stack((d, c['features']))
    w = powers[p.noise_groups[train]] * c['noise_precision'][p.noise_groups[train]] / p.point_noise[train]**2
    gram = np.diag(np.r_[np.zeros(2), c['coefficient_prior_precision']]) + full[train].T @ (full[train] * w[:, None])
    root = np.linalg.cholesky((gram + gram.T) / 2)
    projection = np.linalg.solve(root, full[test].T)
    covariance = np.diag(2 * p.point_noise[test]**2) + projection.T @ projection
    r = c['conditional_residual_hz'][test]
    return dict(gaussian_score(r, covariance), time_s=p.flat_times[test], residual_hz=r,
        marginal_sigma_hz=np.sqrt(np.diag(covariance)), full_feature_width=c['features'].shape[1],
        position_covariance_included=True, test_noise_Gamma_prior_inverse_mean=2,
        held_fragment_constants_and_noise_not_fitted=True)


def refit(scan, node, keep, powers, noise, model, means, arm, rounds, steps):
    reference = np.zeros(len(means))
    x = np.zeros(2)
    history = []
    for _ in range(rounds):
        p = eccentric_problem(scan, node, keep, arm, reference, powers, means, model, noise)
        result = fit(p, x, iterations=steps)
        x = np.array(result['parameters'])
        history.append(result)
        reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
    return p, x, history


def worker(case, method):
    OUT.mkdir(parents=True, exist_ok=True)
    scan0, node0, keep, powers, noise, radio, model, means = context(case)
    base = problem(scan0, node0, 'c0', keep)
    selected_folds = folds(base, keep)
    scan, node = expand(scan0, node0, method)
    records = []
    for fold in selected_folds:
        p, x, history = refit(scan, node, fold['train'], powers, noise, model, means, 'c0', 3, 24)
        prediction = predictive(p, x, fold['train'], fold['test'], powers, fold['family'])
        records.append(dict(receiver=fold['receiver'], norad=int(scan.norads[fold['family']]),
            train_points=int(fold['train'].sum()), test_points=int(fold['test'].sum()),
            prediction=prediction, training_history=history, endpoint_east_north_km=x))
        write(OUT / (case + '_' + method + '_partial.json'), dict(case=case, records=records))
        print(case, method, 'omit RX', fold['receiver'], 'NORAD', scan.norads[fold['family']],
            'predictive loss', round(prediction['negative_twice_log_density'], 3), flush=True)
    pair = {}
    for arm in ('c0', 'fitted_c'):
        p, x, history = refit(scan, node, keep, powers, noise, model, means, arm, 5, 48)
        c = p.calculate(x)
        pair[arm] = dict(endpoint_east_north_km=x, endpoint_latlon=latlon(x), history=history,
            state=p.state(x), negative_twice_elbo=c['negative_twice_elbo'], active_points=int(keep.sum()),
            phase_reference=p.reference, gates=metrics(p, x), RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))))
    valid = all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
    write(OUT / (case + '_' + method + '.json'), dict(case=case, method=method, records=records,
        arms=pair, paired_valid=valid, original_mask=keep, radio_noise_receipts=radio,
        source_sha256=sha(Path(__file__)), refined_data_sha256=sha(DENSE / (case + '_broad_refined.json')),
        prediction_uses_all_five_physical_shape_coordinates=True, no_GPS_used=True,
        qualification_conditional_on_frozen_identities_aliases_noise_and_prior_support=True,
        all_original_points_restored_for_matched_c_pair=True,
        train_budget=[3, 24], full_pair_budget=[5, 48], cold_start=[0, 0],
        box_center_latlon=[37.906, -122.545], box_width_km=25))
    print(case, method, 'paired full fit valid', valid, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--method', choices=METHODS, required=True)
    args = parser.parse_args()
    worker(args.case, args.method)
