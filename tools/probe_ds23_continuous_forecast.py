"""TLE-only gain refinement, then matched fixed-evidence position tests."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_continuous_forecast import qualify
from ds23_causal_phase_location import adjust_means
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import refit
from probe_ds23_symmetric_family_selection import bound_incumbent
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_continuous_phase_forecast'
COHORT = ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json'
ARMS = ('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
        ROOT/'tools/ds23_continuous_forecast.py',ROOT/'tools/probe_ds23_causal_phase_mean.py',
        ROOT/'tools/ds23_causal_phase_location.py',ROOT/'tools/ds23_frequency_events.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path = OUT/'protocol.json'
    if path.exists():
        p = read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen continuous-forecast experiment changed')
        return p
    previous = read(COHORT)
    p = dict(development_cases=previous['development_cases'],confirmation_cases=previous['confirmation_cases'],
        pilot_cases=previous['pilot_cases'],source_sha256=hashes(),workers=24,
        cohort_reused_from_catalogue_trial_not_untouched_locations=True,
        hypothesis='the five-point causal forecast-gain grid discards predictable phase information; continuous gain changes only the prior mean',
        methods=['coarse_conditional_refit','continuous_conditional_refit'],
        original_gain_grid=[0.,.25,.5,.75,1.],continuous_domain=[0.,1.],
        gain_training='earlier 70% historical publication events, excluding NORAD divisible by five',
        qualification='both later historical revisions and held-satellite later revisions improve NLL by >2log33; at least 30 rows in each partition',
        baseline_prefix_variance_and_tail_degrees_conditioned_not_refit=True,
        incumbent_signed_bias_enable_flag_held_fixed=True,
        prefix_bias_from_training_only_full_bias_from_existing_pre_RF_selection=True,
        posterior_model='same observation masks, labels, aliases, powers, noise, prior widths/degrees, radio variables and position box',
        cold_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations=48,
        acceptance='each method separately needs original paired gates and actual phase/reference agreement <=0.01 within 15s; exact incumbent fallback otherwise',
        primary='continuous fitted-c mean AND median improve in both cohorts; report coarse control and all c0 results',
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        no_linear_measurement_updates_calibration=True,
        historical_TLE_revisions_correlated_proxies_not_true_orbits=True)
    write(path,p)
    return p


def learn(case):
    prepare()
    path = OUT/(case+'_forecast.json')
    if path.exists():return dict(case=case,cached=True)
    began = time.monotonic()
    old_path = SOURCE/case/'algo02_result.json'
    old = read(old_path)
    signed,binding = bound_incumbent(case)
    model = old['hyperparameters_from_pre_RF_TLE_only']
    history_path = SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path = history_path.with_name(case+'_forecast.json')
    history,forecast = read(history_path),read(forecast_path)
    receipt = read(SOURCE/case/'receipt.json')
    if forecast['history_sha256']!=sha(history_path) or not forecast['strictly_pre_RF'] or forecast['GPS_or_radio_used']:
        raise ValueError('historical TLE forecast lacks causal binding')
    if history['cutoff_utc_ns']!=receipt['cutoff_utc_ns']:
        raise ValueError('historical TLE cutoff differs from original scan cutoff')
    if any(max(v['epoch'],v['collected_utc_ns'])>history['cutoff_utc_ns']
            for versions in history['past_versions'].values() for v in versions):
        raise ValueError('future TLE in phase forecast training')
    if any(r['validation_time_ns']>history['cutoff_utc_ns'] for r in forecast['transitions']):
        raise ValueError('forecast validation crosses scan cutoff')
    enabled = bool(signed['accepted'] and signed['selection']['qualified'])
    bias = (dict(kind=signed['selection']['kind'],coefficient=signed['selection']['coefficient'])
            if enabled else None)
    result = qualify(forecast,model,enabled,bias)
    write(path,dict(case=case,selection=result,baseline_bias_enabled=enabled,
        baseline_model=model,baseline_full_bias=bias,incumbent_binding=binding,
        historical_forecast_sha256=sha(forecast_path),history_sha256=sha(history_path),
        old_result_sha256=sha(old_path),cutoff_utc_ns=history['cutoff_utc_ns'],
        no_GPS_or_current_RF_values_used_to_fit_gain=True,
        legacy_bias_flag_conditioned_from_incumbent=True,seconds=time.monotonic()-began))
    row = dict(case=case,qualified=result['qualified'],seconds=time.monotonic()-began,
        gain=result.get('all_past_fine',{}).get('gain'))
    print(row,flush=True)
    return row


def means_for(receipts,model,signed,rho):
    result = forecast_phase_mean(receipts,rho)
    if signed['accepted']:
        result = adjust_means(result,receipts,model,signed['selection'])
    return result


def positions(case):
    prepare()
    path = OUT/(case+'_position.json')
    if path.exists():return dict(case=case,cached=True)
    began = time.monotonic()
    proposal = read(OUT/(case+'_forecast.json'))
    scan,node,keep,base,old,signed,binding,model,powers,old_means,entries = setup(case)
    if proposal['incumbent_binding']!=binding or proposal['old_result_sha256']!=sha(SOURCE/case/'algo02_result.json'):
        raise ValueError('continuous mean proposal input changed')
    incumbent = signed['policy_arms']
    _,receipts = phase_widths(scan,base.labels)
    np.testing.assert_allclose(means_for(receipts,model,signed,model['shrinkage']),old_means,atol=1e-12,rtol=0)
    replays = []
    for arm in ARMS:
        r = incumbent[arm]
        p = make_event_problem(scan,node,keep,arm,np.asarray(r['phase_reference']),powers,old_means,model,[])
        attach_event_predictive(p,entries,powers)
        difference = p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']
        if abs(difference)>1e-3:raise ValueError('disabled mean model does not replay incumbent')
        replays.append(dict(arm=arm,RF_difference=difference))
    results = {}
    for method,key in (('coarse','all_past_coarse'),('continuous','all_past_fine')):
        if not proposal['selection']['qualified']:
            results[method] = dict(accepted=False,qualified=False,policy_arms=incumbent,arms={})
            continue
        rho = proposal['selection'][key]['gain']
        changed_means = means_for(receipts,model,signed,rho)
        if np.max(abs(changed_means-old_means))<1e-12:
            results[method] = dict(accepted=False,qualified=True,unchanged=True,gain=rho,
                policy_arms=incumbent,arms={})
            continue
        arms = {a:refit(scan,node,keep,a,powers,changed_means,model,[],entries) for a in ARMS}
        actual = {a:float(np.max(abs(np.asarray(r['state']['phases'])[base.labels]-np.asarray(r['phase_reference']))))
                  for a,r in arms.items()}
        bounded = all(np.max(abs(np.asarray(r['state']['phases'])[base.labels]))<=15 for r in arms.values())
        valid = bool(pair_passes(arms,include_linear=True) and bounded and all(v<=.01 for v in actual.values()))
        if any(r['linear_calibration_max_difference']>1e-10 for r in arms.values()):
            raise ValueError('linear observations changed radio calibration')
        results[method] = dict(accepted=valid,qualified=True,gain=rho,means_s=changed_means,
            arms=arms,policy_arms=arms if valid else incumbent,actual_reference_change_s=actual)
    write(path,dict(case=case,methods=results,incumbent_arms=incumbent,
        original_mask=keep,null_endpoint_replays=replays,
        proposal_sha256=sha(OUT/(case+'_forecast.json')),incumbent_binding=binding,
        seconds=time.monotonic()-began,no_GPS_or_future_TLE_used=True,
        no_original_position_evidence_removed=True,source_sha256=hashes()))
    row = dict(case=case,accepted={m:r['accepted'] for m,r in results.items()},seconds=time.monotonic()-began)
    print(row,flush=True)
    return row


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('prepare','qualify','pilot_positions','cohort_positions'),required=True)
    args = parser.parse_args()
    protocol = prepare()
    if args.stage!='prepare':
        cases = (protocol['pilot_cases'] if args.stage=='pilot_positions' else
                 protocol['development_cases']+protocol['confirmation_cases'])
        function = learn if args.stage=='qualify' else positions
        receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(function,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(completed=len(receipts),total=len(cases)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,
            errors=[r for r in receipts if 'error'in r]))
        print('Terminal',len(receipts),'errors',sum('error'in r for r in receipts),flush=True)
