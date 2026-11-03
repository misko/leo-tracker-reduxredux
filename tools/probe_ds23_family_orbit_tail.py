"""Causal qualification and matched single-scan position tests of joint tails."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_family_orbit_tail import qualify,make_joint_tail_problem
from ds23_joint_orbit_prior import transition
from ds23_frequency_events import attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import SOURCE
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import cached,summary
from probe_ds23_symmetric_family_selection import SIGNED
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_family_orbit_tail'
OLD=ROOT/'reports/2026_10_19_algo03_joint_orbit_prior'


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in
        (Path(__file__),ROOT/'tools/ds23_family_orbit_tail.py',ROOT/'tools/ds23_joint_orbit_prior.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen joint-tail experiment changed')
        return p
    available=sorted(read(SIGNED/'evaluation_audit.json')['evidence'])
    development=sorted(p.name.split('_prior')[0] for p in OLD.glob('DS23-*_prior.json'))
    development=[c for c in development if c in available]
    pool=[c for c in available if c not in development]
    confirmation=sorted(np.random.default_rng(2026102071).choice(pool,20,replace=False).tolist())
    p=dict(development_cases=development,confirmation_cases=confirmation,confirmation_seed=2026102071,
        source_sha256=hashes(),workers=12,
        hypothesis='one shared Student precision for each supported satellite phase and three physical shape modes',
        original_Student_degrees_marginal_variances_mean_scales_and_physical_modes_unchanged=True,
        difference_from_previous_studies='phase/shape share the same tail event; earlier shape Student and phase-shape correlation studies retained separate scales',
        qualification='pre-RF TLE updates: earlier nonheld satellites positive density gain, later all and later NORAD mod5 held gains >2log2; min30 each',
        continuous_hyperparameters_added=0,no_RF_GPS_future_TLE_or_satellite_subset_for_prior_learning=True,
        position='same signed-prior incumbent, masks, points, labels, aliases, noise, powers, 25km box, center start and five phase rounds of 48 iterations',
        predictive_linear_points_never_calibrate=True,
        acceptance='original paired c0/fitted-c gates; failed pair returns entire incumbent',
        primary='fitted-c mean AND median improve in development and disjoint recording confirmation',
        c0_regressions_reported=True,baseline_GPS_already_exposed_not_untouched_locations=True,
        frozen_before_joint_tail_RF_or_position_evaluation=True)
    write(path,p);return p


def prior(case):
    prepare();path=OUT/(case+'_prior.json')
    if path.exists():return read(path)
    hpath=SOURCE/'causal_phase_history'/(case+'.json');fpath=hpath.with_name(case+'_forecast.json')
    history,forecast=read(hpath),read(fpath);cutoff=history['cutoff_utc_ns']
    if sha(hpath)!=forecast['history_sha256']:raise ValueError('causal history changed')
    cached_prior=OLD/(case+'_prior.json');rows=[];rejected={}
    if cached_prior.exists():
        previous=read(cached_prior)
        if previous['history_sha256']!=sha(hpath):raise ValueError('cached causal transitions use different archive')
        rows=previous['transitions']
    else:
        for norad,versions in history['past_versions'].items():
            if any(max(v['epoch'],v['collected_utc_ns'])>cutoff for v in versions):
                raise ValueError('noncausal TLE in prior data')
            for k in range(2,len(versions)):
                try:
                    row=transition(*versions[k-2:k+1])
                    if row is None:reason='noncausal_or_unordered'
                    elif row['target_utc_ns']>cutoff:reason='historical_target_after_scan'
                    elif not np.isfinite(np.r_[row['shape_z'],row['phase_residual_s'],row['predicted_sigma_s']]).all():reason='nonfinite_transition'
                    else:reason=None
                except ValueError as exc:
                    reason=str(exc)
                if reason:rejected[reason]=rejected.get(reason,0)+1
                else:rows.append(dict(norad=int(norad),**row))
    if any(max(r['validation_time_ns'],r['target_utc_ns'])>cutoff for r in rows):
        raise ValueError('noncausal prior target')
    qualified=(forecast['distribution_validation']['count']>=30 and
        forecast['distribution_validation']['negative_twice_log_density']<forecast['original_distribution_validation']['negative_twice_log_density'])
    null=dict(nu=None,shrinkage=0.,multiplier=1.)
    prefix=forecast['prefix_distribution'] if qualified else null
    full=forecast['all_past_distribution'] if qualified else null
    selection=qualify(rows,forecast['temporal_split_boundary_ns'],prefix,full)
    result=dict(case=case,selection=selection,transitions=len(rows),rejected=rejected,
        history_sha256=sha(hpath),forecast_sha256=sha(fpath),cutoff_utc_ns=cutoff,
        source_sha256=hashes(),no_GPS_RF_or_future_TLE_used=True)
    write(path,result);return result


def refit(scan,node,keep,arm,powers,means,model,entries):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for k in range(5):
        p=make_joint_tail_problem(scan,node,keep,arm,reference,powers,means,model)
        attach_event_predictive(p,entries,powers);cached(p)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15);change=float(np.max(abs(phase-reference)))
        history.append(dict(epoch=k,fit=fitted,phase_change_s=change));reference=phase
    return dict(summary(p,x,entries),history=history,final_phase_change_s=change)


def run(case):
    prepare();path=OUT/(case+'.json')
    if path.exists():return dict(case=case,cached=True)
    before=time.monotonic();learned=prior(case)
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    incumbent=signed['policy_arms'];nulls=[]
    from ds23_frequency_events import make_event_problem
    for arm in ('c0','fitted_c'):
        saved=incumbent[arm]
        p=make_event_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        delta=p.calculate(np.asarray(saved['endpoint_east_north_km']))['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3:raise ValueError('signed null does not replay')
        nulls.append(dict(arm=arm,RF_difference=delta))
    offered=learned['selection']['qualified']
    pair={a:refit(scan,node,keep,a,powers,means,model,entries) for a in ('c0','fitted_c')} if offered else incumbent
    valid=pair_passes(pair,include_linear=True) if offered else True
    record=dict(case=case,qualified=offered,accepted=bool(offered and valid),paired_valid=valid,
        arms=pair,policy_arms=pair if valid else incumbent,incumbent_arms=incumbent,
        incumbent_binding=binding,null_endpoint_replays=nulls,original_mask=keep,
        prior_sha256=sha(OUT/(case+'_prior.json')),source_sha256=hashes(),
        GPS_used=False,future_TLE_used=False,seconds=time.monotonic()-before)
    write(path,record)
    print(case,'prior',offered,'paired',valid,'seconds',record['seconds'],flush=True)
    return dict(case=case,qualified=offered,paired_valid=valid)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','development','confirmation'),required=True)
    args=parser.parse_args();protocol=prepare()
    if args.stage!='prepare':
        receipts=[];cases=protocol[args.stage+'_cases']
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures={pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
