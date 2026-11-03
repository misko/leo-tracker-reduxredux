"""Matched RX2 measurement interventions with unchanged causal hypotheses."""

import argparse
import copy
import time
from pathlib import Path

import numpy as np

from ds23_heteroscedastic_gates import metrics
from ds23_measurement_noise import learn_local_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_precision import precision_problem
from probe_ds23_refined_timestamps import apply_effective_times
from prototype_dsx01_continuous_position import latlon
from remeasure_ds23_rx2_cohort import OUT
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, final_scan, read, write, sha

METHODS = ('refined_original_noise', 'refined_local_noise', 'refined_local_noise_five_orbit')


def record(p, x, history):
    calculated = p.calculate(x)
    return dict(endpoint_east_north_km=x, endpoint_latlon=latlon(x), history=history,
        state=p.state(x), phase_reference=p.reference, active_points=int(p.keep.sum()),
        negative_twice_elbo=calculated['negative_twice_elbo'],
        RMS_hz=float(np.sqrt(np.mean(calculated['conditional_residual_hz'][p.keep]**2))),
        gates=metrics(p, x), effective_noise_hz=p.point_noise[p.keep],
        no_original_point_removed=True,
        eccentricity_receipts=getattr(p, 'eccentricity_receipts', None))


def run(case, method):
    started = time.monotonic()
    path = OUT / (case+'_'+method+'_position.json')
    if path.exists():
        raise FileExistsError('preserve completed scientific outputs')
    learned = read(LEARNED / (case+'.json'))
    primary = learned['results']['mean_and_distribution']
    model = learned['hyperparameters_from_pre_RF_TLE_only']
    node = read(SOURCE / case / 'result.json')['final_node']
    keep = np.array(primary['mask'], bool)
    powers = np.array(read(WEIGHTS / case / 'result.json')['results']['cross_rx_support']['weights'])
    scan = final_scan(case)
    base = problem(scan, node, 'c0', keep)
    _, receipt = phase_widths(scan, base.labels)
    means = forecast_phase_mean(receipt, model['shrinkage'])
    noise, radio, updates, times = {}, [], {}, {}
    if method != 'replay':
        raw = read(OUT / (case+'_refined.json'))
        if raw['qualification_only'] or not raw['all_sealed_requests_measured']:
            raise ValueError('full sealed RX2 panel required for position propagation')
        updates = update_values(scan, raw['rows'], 'joint_CFO_epoch_rate')
        times = apply_effective_times(scan, raw['rows'])
        if method.startswith('refined_local_noise'):
            noise, radio = learn_local_noise(raw)
    arms = {}
    for arm in ('c0', 'fitted_c'):
        reference, x, history = np.zeros(len(means)), np.zeros(2), []
        for _ in range(5):
            factory = eccentric_problem if method.endswith('five_orbit') else precision_problem
            p = factory(scan, node, keep, arm, reference, powers, means, model, noise)
            result = fit(p, x, iterations=48)
            x = np.array(result['parameters'])
            history.append(result)
            reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        arms[arm] = record(p, x, history)
        write(OUT / (case+'_'+method+'_position_partial.json'), dict(case=case, method=method, arms=arms))
    failed = sorted({r['component'] for a in arms.values() for r in a['gates']['tracks'] if not r['compatible']})
    active_ids = {oid for i, sl in zip(base.members, base.slices, strict=True)
                  for oid, good in zip(base.scan.tracks[i]['observation_ids'], keep[sl], strict=True) if good}
    write(path, dict(case=case, method=method, trial_arms=arms, paired_valid=not failed, failed_tracks=failed,
        policy_arms=arms if not failed else primary['arms'], baseline_arms=primary['arms'],
        original_mask=keep, CFO_updates=updates, effective_time_offsets_s=times,
        proposed_noise_by_id=noise, radio_noise_receipts=radio,
        active_refined_points=len(active_ids & set(updates.get('changed_observation_ids_and_delta_hz', {}))),
        active_noise_changed_points=len(active_ids & set(noise)),
        original_labels_aliases_points_powers_and_orbit_priors_unchanged=True,
        paired_failure_falls_back_to_incumbent_not_additional_trimming=True,
        gates_are_explicit_pointwise_noise_development_gates_with_legacy_checks_recorded=True,
        noise_estimated_from_complete_radio_curves_not_GPS_or_orbit_residuals=True,
        cold_region_start_and_five_rounds_48_steps_for_both_c_arms=True,
        GPS_used=False, source_sha256=sha(Path(__file__)),
        refined_sha256=None if method=='replay' else sha(OUT / (case+'_refined.json')),
        learned_sha256=sha(LEARNED / (case+'.json')), seconds=time.monotonic()-started))
    print(case, method, 'paired valid', not failed, 'seconds', round(time.monotonic()-started, 2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--method', choices=METHODS+('replay',), required=True)
    args = parser.parse_args()
    run(args.case, args.method)
