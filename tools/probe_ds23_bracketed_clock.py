"""Bounded common UTC profiling, learned from curved RF only and then frozen."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from algo02_scan import pair_passes
from ds23_bracketed_clock import clock_interval,clock_problem,attach_clock_prediction
from investigate_dsx01_localization_failures import fit
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import cached,summary
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_bracketed_clock'
COHORT=ROOT/'reports/2026_10_20_ds23_family_orbit_tail_v2'


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/ds23_bracketed_clock.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen common-clock experiment changed')
        return p
    old=read(COHORT/'protocol.json')
    p=dict(development_cases=old['development_cases'],confirmation_cases=old['confirmation_cases'],
        source_sha256=hashes(),workers=12,cohorts_reused_not_new_untouched_validation=True,
        hypothesis='the original host-bracket midpoint is an uncertain common UTC anchor, independent of per-satellite TLE phase errors',
        prior='uniform within original capture UTC interval; exact common time shift profiled with hard interval bounds',
        timing_parameter='one per scan; affects orbit evaluation and Earth rotation, not elapsed radio basis',
        curved_clock_search=dict(phase_rounds=5,iterations=48,start_east_north_clock=[0,0,0]),
        predictive_search=dict(clock_frozen_from_curved_only=True,phase_rounds=5,iterations=48,cold_start_east_north=[0,0]),
        zero_clock_control='same original point set and five-by-48 predictive search, common shift exactly zero',
        original_radio_orbit_phase_and_noise_priors_masks_labels_aliases_powers_unchanged=True,
        linear_points_do_not_update_radio_or_clock=True,paired_c0_fitted_c_budgets_and_bounds=True,
        acceptance='original paired curved/predictive residual gates and phase convergence; otherwise incumbent fallback',
        no_GPS_future_TLE_RF_collection_or_cross_scan_clock_calibration=True,
        primary='fitted-c mean AND median improve in each cohort; all c0 results disclosed',
        RF_profile_objective_not_a_calibrated_marginal_clock_evidence=True)
    write(path,p);return p


def refit(scan,node,keep,arm,powers,means,model,interval,entries,shift):
    reference=np.zeros(len(means));x=np.zeros(3 if shift is None else 2);history=[]
    for epoch in range(5):
        p=clock_problem(scan,node,keep,arm,reference,powers,means,model,interval,fixed_shift_s=shift)
        attach_clock_prediction(p,entries,powers);cached(p)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15);change=float(np.max(abs(phase-reference)))
        history.append(dict(epoch=epoch,fit=fitted,phase_change_s=change,clock_shift_s=p.clock_shift(x)))
        reference=phase
    result=summary(p,x,entries)
    # Position fields remain horizontal coordinates. The explicit physical
    # timing coordinate is recorded separately from the report's lat/lon.
    result['endpoint_east_north_km']=x[:2]
    return dict(result,history=history,final_phase_change_s=change,common_UTC_shift_s=p.clock_shift(x),
        clock_at_boundary=bool(min(p.clock_shift(x)-interval['lower_s'],interval['upper_s']-p.clock_shift(x))<1e-5))


def run(case):
    prepare();path=OUT/(case+'.json')
    if path.exists():return dict(case=case,cached=True)
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    interval=clock_interval(read(SOURCE/case/'tracking.json'),scan.receipt['origin_utc_ns'])
    incumbent=signed['policy_arms'];nulls=[]
    for arm in ('c0','fitted_c'):
        saved=incumbent[arm];x=np.asarray(saved['endpoint_east_north_km'])
        p=clock_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model,interval,fixed_shift_s=0.)
        attach_clock_prediction(p,entries,powers)
        delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3:raise ValueError('zero-clock endpoint does not reproduce incumbent')
        nulls.append(dict(arm=arm,RF_difference=delta))
    curved={a:refit(scan,node,keep,a,powers,means,model,interval,[],None) for a in ('c0','fitted_c')}
    pair={a:refit(scan,node,keep,a,powers,means,model,interval,entries,curved[a]['common_UTC_shift_s']) for a in ('c0','fitted_c')}
    valid=pair_passes(pair,include_linear=True)
    write(path,dict(case=case,arms=pair,clock_curved_arms=curved,paired_valid=valid,accepted=valid,
        policy_arms=pair if valid else incumbent,incumbent_arms=incumbent,null_endpoint_replays=nulls,
        interval=interval,original_mask=keep,incumbent_binding=binding,source_sha256=hashes(),
        GPS_used=False,future_TLE_used=False,clock_calibrated_from_curved_only=True,
        predictive_clock_frozen=True))
    print(case,'paired',valid,'shifts',[pair[a]['common_UTC_shift_s'] for a in ('c0','fitted_c')],flush=True)
    return dict(case=case,paired_valid=valid)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('development','confirmation'),required=True)
    args=parser.parse_args();protocol=prepare();receipts=[];cases=protocol[args.stage+'_cases']
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        futures={pool.submit(run,c):c for c in cases}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
            write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
    write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
    print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
