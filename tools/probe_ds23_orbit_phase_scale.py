"""Causal physical-element scale qualification and matched DS23 position fits."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_orbit_phase_scale import qualify, scale_for_elements
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_continuous_forecast import COHORT, ARMS
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import refit
from probe_ds23_symmetric_family_selection import bound_incumbent
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_orbit_phase_scale'


def hashes():
    return {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__),
        ROOT/'tools/ds23_orbit_phase_scale.py', ROOT/'tools/ds23_continuous_forecast.py',
        ROOT/'tools/probe_ds23_frequency_events.py', ROOT/'tools/ds23_frequency_events.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path = OUT/'protocol.json'
    if path.exists():
        protocol = read(path)
        if protocol['source_sha256'] != hashes():
            raise ValueError('frozen physical-scale sources changed')
        return protocol
    cohort = read(COHORT)
    protocol = dict(development_cases=cohort['development_cases'], confirmation_cases=cohort['confirmation_cases'],
        pilot_cases=cohort['pilot_cases'], source_sha256=hashes(), workers=24,
        hypothesis='global phase uncertainty pools physically different orbits; condition its scale on preceding mean motion, eccentricity and Bstar',
        methods=['scalar', 'conditional'], features=['intercept', 'mean_motion', 'log_eccentricity', 'log_abs_bstar'],
        log_scale_coefficients_bounds=[-1., 1.], multiplier_bounds=[.25, 4.], coefficient_prior='unit Gaussian',
        qualification='later temporal AND held-satellite transitions each beat both baseline and scalar by >3log(training count)',
        train='first 70% historical publication epochs, excluding NORAD divisible by five',
        baseline_prefix_model_conditioned_not_relearned=True,
        existing_bias_enable_flag_conditioned_from_RF_incumbent=True,
        all_means_nu_masks_labels_aliases_powers_noise_and_other_priors_unchanged=True,
        scalar_control_and_conditional_policy_share_qualification_mask=True,
        cohort_reused_not_untouched_geographic_validation=True,
        cold_start_km=[0, 0], box_width_km=25, phase_rounds=5, position_iterations=48,
        acceptance='original paired gates, true phase/reference agreement <=.01, abs phases<=15; exact incumbent fallback',
        primary='conditional fitted-c mean AND median improve in development AND confirmation; report scalar and c0 controls',
        no_GPS_future_TLE_cross_scan_position_prior_or_new_RF=True,
        TLE_updates_correlated_prediction_proxies_not_orbit_truth=True)
    write(path, protocol)
    return protocol


def learn(case):
    prepare(); path = OUT/(case+'_scale.json')
    if path.exists():
        return dict(case=case, cached=True)
    old_path = SOURCE/case/'algo02_result.json'
    old = read(old_path); signed, binding = bound_incumbent(case)
    history_path = SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path = history_path.with_name(case+'_forecast.json')
    history, forecast = read(history_path), read(forecast_path)
    if forecast['history_sha256'] != sha(history_path) or history['cutoff_utc_ns'] != read(SOURCE/case/'receipt.json')['cutoff_utc_ns']:
        raise ValueError('causal history binding mismatch')
    enabled = bool(signed['accepted'] and signed['selection']['qualified'])
    bias = dict(kind=signed['selection']['kind'], coefficient=signed['selection']['coefficient']) if enabled else None
    model = old['hyperparameters_from_pre_RF_TLE_only']
    result = qualify(history, forecast, model, enabled, bias)
    write(path, dict(case=case, selection=result, bias_enabled=enabled, full_bias=bias, baseline_model=model,
        incumbent_binding=binding, history_sha256=sha(history_path), forecast_sha256=sha(forecast_path),
        cutoff_utc_ns=history['cutoff_utc_ns'], old_result_sha256=sha(old_path),
        scale_coefficients_use_no_current_RF_or_GPS=True))
    row = dict(case=case, qualified=result['qualified'], validation=result.get('validation'))
    print(row, flush=True)
    return row


def changed_model(scan, base, model, selection, method):
    coefficients = selection['all_past_'+method]['coefficients']
    multipliers = np.array([scale_for_elements(scan.elements[str(scan.norads[j])]['lines'], coefficients)
                            for j in base.labels])
    return dict(model, multiplier=model['multiplier']*multipliers), multipliers


def positions(case):
    prepare(); path = OUT/(case+'_position.json')
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic(); proposal = read(OUT/(case+'_scale.json'))
    scan,node,keep,base,old,signed,binding,model,powers,means,entries = setup(case)
    if binding != proposal['incumbent_binding']:
        raise ValueError('incumbent changed')
    # Refuse any observation-time element that was unavailable at cutoff.
    for j in base.labels:
        p = scan.elements[str(scan.norads[j])]['provenance']
        if max(p['element_epoch_utc_ns'], p['collected_utc_ns']) > proposal['cutoff_utc_ns']:
            raise ValueError('future runtime element')
    incumbent = signed['policy_arms']; null = []
    for arm in ARMS:
        r = incumbent[arm]
        p = make_event_problem(scan,node,keep,arm,np.asarray(r['phase_reference']),powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        difference = p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']
        if abs(difference) > 1e-3:
            raise ValueError('disabled physical-scale model failed replay')
        null.append(dict(arm=arm, RF_difference=difference))
    results = {}
    for method in ('scalar', 'conditional'):
        if not proposal['selection']['qualified']:
            results[method] = dict(accepted=False, arms={}, policy_arms=incumbent)
            continue
        modified, scales = changed_model(scan,base,model,proposal['selection'],method)
        arms = {a: refit(scan,node,keep,a,powers,means,modified,[],entries) for a in ARMS}
        actual = {a: float(np.max(abs(np.asarray(r['state']['phases'])[base.labels] -
                                    np.asarray(r['phase_reference'])))) for a,r in arms.items()}
        bounded = all(np.max(abs(np.asarray(r['state']['phases'])[base.labels])) <= 15 for r in arms.values())
        valid = bool(pair_passes(arms,include_linear=True) and bounded and all(v<=.01 for v in actual.values()))
        if any(r['linear_calibration_max_difference']>1e-10 for r in arms.values()):
            raise ValueError('predictive observations changed calibration')
        results[method] = dict(accepted=valid, arms=arms, policy_arms=arms if valid else incumbent,
            actual_phase_reference_difference_s=actual, per_label_scale_multipliers=scales,
            norads=[int(scan.norads[j]) for j in base.labels])
    write(path, dict(case=case, methods=results, incumbent_arms=incumbent, original_mask=keep,
        null_endpoint_replays=null, source_sha256=hashes(), proposal_sha256=sha(OUT/(case+'_scale.json')),
        incumbent_binding=binding, no_original_position_evidence_removed=True,
        seconds=time.monotonic()-began, no_GPS_used=True))
    row = dict(case=case, accepted={m:r['accepted'] for m,r in results.items()}, seconds=time.monotonic()-began)
    print(row,flush=True)
    return row


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare','qualify','pilot_positions','cohort_positions'), required=True)
    stage=parser.parse_args().stage; protocol=prepare()
    if stage != 'prepare':
        cases=protocol['pilot_cases'] if stage=='pilot_positions' else protocol['development_cases']+protocol['confirmation_cases']
        function=learn if stage=='qualify' else positions; receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(function,c):c for c in cases}
            for f in as_completed(futures):
                try: receipts.append(f.result())
                except Exception as exc: receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(stage+'_progress.json'),dict(completed=len(receipts),total=len(cases)))
        errors=[r for r in receipts if 'error' in r]
        write(OUT/(stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,errors=errors))
        print('Terminal',len(receipts),'errors',errors,flush=True)
