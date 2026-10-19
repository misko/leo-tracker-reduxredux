"""Fixed RX1 covariance qualification on the original twenty development scans."""

import argparse
from pathlib import Path
import numpy as np
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_dense_receiver_prediction import OUT as DENSE_PREDICTION, expand, folds, predictive
from probe_ds23_history_calibrated_phase import OUT as LEARNED, make_problem, refit
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, final_scan, read, write, sha

OUT = DENSE_PREDICTION / 'incumbent20'


def qualify(baseline, alternative, valid, RF_delta):
    if len(baseline) != len(alternative) or not baseline:
        return dict(qualified=False, reason='no matched prediction folds')
    gains = {}
    for rx in (1, 2):
        gains[str(rx)] = sum(a['prediction']['negative_twice_log_density'] - b['prediction']['negative_twice_log_density']
            for a, b in zip(baseline, alternative, strict=True) if a['receiver'] == rx)
    qualified = valid and RF_delta < 0 and min(gains.values()) > 0 and sum(gains.values()) > 2 * np.log(2)
    return dict(qualified=bool(qualified), per_receiver_gain=gains, total_gain=sum(gains.values()),
        RF_loss_change=RF_delta, mode_penalty=2 * np.log(2), same_rule_for_every_scan=True)


def run(case):
    OUT.mkdir(parents=True, exist_ok=True)
    scan0 = final_scan(case)
    node0 = read(SOURCE / case / 'result.json')['final_node']
    learned = read(LEARNED / (case + '.json'))
    baseline = learned['results']['mean_and_distribution']
    keep = np.array(baseline['mask'], bool)
    model = learned['hyperparameters_from_pre_RF_TLE_only']
    powers = np.array(read(WEIGHTS / case / 'result.json')['results']['cross_rx_support']['weights'])
    base = problem(scan0, node0, 'c0', keep)
    _, receipts = phase_widths(scan0, base.labels)
    means = forecast_phase_mean(receipts, model['shrinkage'])
    selected_folds = folds(base, keep)
    records, pair = {}, None
    for method in ('baseline', 'fast_rx1'):
        scan, node = expand(scan0, node0, method)
        records[method] = []
        for fold in selected_folds:
            reference = np.zeros(len(means))
            x = np.zeros(2)
            history = []
            for _ in range(3):
                p = make_problem(scan, node, fold['train'], 'c0', reference, powers, means, model['multiplier'], model['nu'])
                r = fit(p, x, iterations=24)
                x = np.array(r['parameters'])
                history.append(r)
                reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            prediction = predictive(p, x, fold['train'], fold['test'], powers, fold['family'])
            records[method].append(dict(receiver=fold['receiver'], norad=int(scan.norads[fold['family']]),
                train_points=int(fold['train'].sum()), test_points=int(fold['test'].sum()),
                prediction=prediction, training_endpoint_east_north_km=x, training_history=history))
        print(case, method, 'prediction folds', len(selected_folds), flush=True)
        write(OUT / (case + '_partial.json'), dict(case=case, records=records))
        if method == 'fast_rx1':
            pair = {arm: refit(scan, node, keep, arm, powers, means, model['multiplier'], model['nu']) for arm in ('c0', 'fitted_c')}
    valid = all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
    delta = pair['c0']['negative_twice_elbo'] - baseline['arms']['c0']['negative_twice_elbo']
    selection = qualify(records['baseline'], records['fast_rx1'], valid, delta)
    selected = pair if selection['qualified'] else baseline['arms']
    write(OUT / (case + '.json'), dict(case=case, records=records, trial_arms=pair, paired_valid=valid,
        baseline_arms=baseline['arms'], selected_arms=selected, selection=selection, original_mask=keep,
        source_sha256=sha(Path(__file__)), dense_probe_source_sha256=sha(ROOT / 'tools/probe_ds23_dense_receiver_prediction.py'),
        learned_input_sha256=sha(LEARNED / (case + '.json')), noise_and_power_unchanged=True,
        no_GPS_used=True, no_original_point_removed=True, no_raw_IQ_or_post_scan_TLE_used=True,
        same_identities_aliases_priors_masks_and_paired_c_budgets=True,
        baseline_is_frozen_previously_completed_five_round_48_step_fit=True,
        prediction_is_conditional_on_frozen_noise_identities_and_support=True,
        covariance_width_engineering_hypothesis_not_GPS_tuned=True))
    print(case, 'RX1 variant valid', valid, 'qualified', selection['qualified'], 'predictive gain', selection.get('total_gain'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    run(parser.parse_args().case)
