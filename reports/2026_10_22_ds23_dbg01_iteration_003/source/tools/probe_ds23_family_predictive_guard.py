"""RF-only validation of added curves against original satellite families.

Family folds are diagnostics, not data deletion from final estimates. This
engineering rule was designed after the iteration003 association regression;
its confirmation cohort is frozen before any fold scores are evaluated.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import csv
from pathlib import Path
import signal

import numpy as np

import audit_ds23_family_cavity as auditor
import probe_ds23_family_cavity_nominations as nomination
from ds23_family_cavity import predictive_density_reference
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import refit
import run_ds23_dbg01_iteration_002 as context
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_003_raw'


def training_masks(rows,slices,original,expanded,target):
    original,expanded=np.asarray(original,bool),np.asarray(expanded,bool)
    if original.shape!=expanded.shape or not expanded[original].all():
        raise ValueError('expanded model must retain every original curved measurement')
    held=np.zeros(len(original),bool)
    for row,sl in zip(rows,slices,strict=True):
        if row['candidate_index']==target:held[sl]=original[sl]
    training=expanded.copy();training[held]=False
    return training,held


def guard_decision(gains,valid):
    return bool(valid and all(np.sum(v)>2*np.log(2) and np.median(v)>=0 for v in gains.values()))


def held_prediction_data(d,p,x,held):
    c=p.curved_calculate(x) if d['entries'] else p.calculate(x)
    groups=p.noise_groups[p.keep];features=c['features'][p.keep]
    weights=d['powers'][groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
    covariance=np.linalg.inv(np.diag(c['coefficient_prior_precision'])+features.T@(features*weights[:,None]))
    nb=p.hardware.shape[1]+p.smooth.shape[1]
    values=[];times=[];radio=[];noise=[];q=[];members=[];labels=[];aliases=[]
    train_ids={oid for i,sl in zip(p.members,p.slices,strict=True)
               for oid,use in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if use}
    held_ids=set()
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        use=held[sl]
        if not use.any():continue
        t=p.scan.tracks[i];ids=np.asarray(t['observation_ids'])[use].tolist();held_ids.update(ids)
        members.append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=int(use.sum()),
                            row_index=k,observation_ids=ids,kind='curved'))
        labels.extend([len(members)-1]*int(use.sum()));aliases.append(int(p.alias[k]))
        times.extend(t['times'][use]);values.extend(t['values'][use]);q.extend(p.q[sl][use])
        radio.extend(c['features'][sl,:nb][use]);noise.extend(p.point_noise[sl][use]*np.sqrt(2/d['powers'][k]))
    if train_ids&held_ids:raise ValueError('held original family leaked into curved calibration')
    times,values,q,radio,noise,labels=map(np.asarray,[times,values,q,radio,noise,labels])
    return dict(p=p,coefficient=c['coefficient'],covariance=covariance,radio_width=nb,
        times=times,values=values,q=q,radio=radio,noise=noise,groups=labels,members=members,
        base_covariance=np.diag(noise**2)+radio@covariance[:nb,:nb]@radio.T+300.**2*(labels[:,None]==labels[None,:]),
        held_owners=len({(m['receiver'],m['channel']) for m in members}),held_ids=sorted(held_ids)),aliases


def fold(job):
    case,target,variant=job;out=RAW/'family_predictive_guard'/case;out.mkdir(exist_ok=True)
    path=out/f'fold_{target:04d}_{variant}.json'
    if path.exists():raise FileExistsError('preserve completed RF family fold')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 s RF family fold budget')))
    signal.alarm(180)
    try:
        d=context.current_setup(case);proposal=read(RAW/'all_curve_families'/(case+'_positions.json'))['selected']
        if proposal is None:raise ValueError('no valid expanded proposal for predictive guard')
        node=d['node'] if variant=='baseline' else proposal['node']
        expanded=d['keep'] if variant=='baseline' else np.asarray(proposal['mask'],bool)
        mask,held=training_masks(d['base'].rows,d['base'].slices,d['keep'],expanded,target)
        entries=[e for e in d['entries'] if e['candidate_index']!=target]
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
        j=target;number=int(d['scan'].norads[j]);arms={}
        for arm in ['c0','fitted_c']:
            trained=refit(d['scan'],node,mask,arm,d['powers'],means,d['model'],[],entries)
            p=make_event_problem(d['scan'],node,mask,arm,np.asarray(trained['phase_reference']),d['powers'],means,d['model'],[])
            attach_event_predictive(p,entries,d['powers']);x=np.asarray(trained['endpoint_east_north_km'])
            dd=dict(d,node=node,keep=mask,means=means,entries=entries,x=x)
            replay=p.calculate(x)['negative_twice_elbo']-trained['negative_twice_elbo']
            if abs(replay)>1e-5:raise ValueError('family-fold endpoint does not replay')
            density=auditor.density(dd,p,x,means,entries)
            data,aliases=held_prediction_data(dd,p,x,held);data['target']=target
            capture=[];original=nomination.gaussian_prediction
            def record(raw,features,covariance,sigma):
                capture.append((raw.copy(),features.copy(),covariance.copy(),sigma.copy()))
                return original(raw,features,covariance,sigma)
            nomination.gaussian_prediction=record
            try:prediction=nomination.candidate_prediction(dd,data,target,aliases)
            finally:nomination.gaussian_prediction=original
            direct,method=predictive_density_reference(*capture[-1]);delta=abs(direct-prediction['score'])
            if delta>2e-3:raise ValueError('family-fold predictive density failed independent check')
            active=sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if mask[sl].any()})
            valid=bool(trained['final_phase_change_s']<=.01 and max(abs(np.asarray(trained['state']['phases'])[active]))<=15.+1e-8
                       and prediction['qualified'])
            arms[arm]=dict(training_endpoint=trained,prediction=prediction,
                held_original_points=int(held.sum()),training_curved_points=int(mask.sum()),
                numerical_phase_and_visibility_valid=valid,
                training_density_audit=density,predictive_density_difference=delta,independent_method=method,
                held_observation_ids=data['held_ids'],held_IDs_disjoint_from_training=True,
                training_support_owner_gate_is_not_final_adoption_gate=True)
        result=dict(case=case,target=target,norad=number,variant=variant,status='complete',arms=arms,
            all_passed=True,no_GPS_or_following_TLE=True,source_sha256=sha(Path(__file__)))
        write(path,result)
        print(case,'family fold',number,variant,'complete',flush=True)
        return dict(case=case,target=target,variant=variant,status='complete',all_passed=True)
    except Exception as exc:
        import traceback
        result=dict(case=case,target=target,variant=variant,status='failed',error=repr(exc),traceback=traceback.format_exc())
        write(path.with_name(path.stem+'_failed.json'),result);return result
    finally:signal.alarm(0)


def select(case):
    d=context.current_setup(case);families=sorted({r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices) if d['keep'][sl].any()})
    gains={a:[] for a in ['c0','fitted_c']};rows=[];valid=True
    for target in families:
        records={v:read(RAW/'family_predictive_guard'/case/f'fold_{target:04d}_{v}.json') for v in ['baseline','expanded']}
        for arm in gains:
            a,b=[records[v]['arms'][arm] for v in ['baseline','expanded']]
            if a['held_observation_ids']!=b['held_observation_ids']:raise ValueError('family-fold scoring observations changed')
            gain=a['prediction']['score']-b['prediction']['score'];gains[arm].append(gain)
            valid=valid and a['numerical_phase_and_visibility_valid'] and b['numerical_phase_and_visibility_valid']
            rows.append(dict(norad=int(d['scan'].norads[target]),arm=arm,points=a['held_original_points'],gain=gain,
                             baseline_score=a['prediction']['score'],expanded_score=b['prediction']['score']))
    adopted=guard_decision(gains,valid)
    result=dict(case=case,adopted=adopted,rows=rows,
        summary={a:dict(sum_gain=float(np.sum(v)),median_gain=float(np.median(v)),families_improved=int(np.sum(np.asarray(v)>0))) for a,v in gains.items()},
        all_folds_numerically_valid=bool(valid),selection_sealed_before_new_geographic_reporting=True,
        policy='expanded' if adopted else 'published incumbent',
        composite_predictive_score_not_a_calibrated_Bayes_factor=True,
        development_rule_designed_after_observing_0390_regression=True,
        no_persistent_holdout_all_original_points_used_in_final_model=True)
    write(RAW/'family_predictive_guard'/(case+'_selection.json'),result)
    print(case,'RF family consistency',result['summary'],'adopted',adopted,flush=True)
    return result


def prepare():
    out=RAW/'family_predictive_guard';out.mkdir(exist_ok=True)
    cases=read(RAW/'protocol.json')['cases'];path=out/'protocol.json'
    if path.exists():
        record=read(path)
        if record['source_sha256']!=sha(Path(__file__)):raise ValueError('RF guard source changed after freezing')
        return record
    benchmark=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/tables/positions.csv'
    available=sorted({r['case'] for r in csv.DictReader(benchmark.open()) if r['policy']=='equal_assignment_priors' and r['arm']=='fitted_c'})
    excluded={'DS23-0081','DS23-0326','DS23-0035','DS23-0041','DS23-0111','DS23-0390','DS23-0405','DS23-0268','DS23-0080','DS23-0240'}
    confirmation=np.random.default_rng(2026102203).choice([c for c in available if c not in excluded],20,replace=False).tolist()
    record=dict(cases=cases,source_sha256=sha(Path(__file__)),
        engineering_hypothesis_designed_after_0390_regression=True,
        family_folds='hold each original curved family out of training; remove its predictive entries; keep proposed new curves in expanded training',
        held_scoring='same exact original curved IDs, fixed original family ID and alias; full correlated calibration posterior and causal phase/orbit/300Hz fragment priors',
        training='regional center, five phase rounds,48steps, both c arms; all remaining original curved and predictive points retained',
        guard='sum baseline-minus-expanded predictive score >2log(2) AND median family gain>=0 in BOTH c arms, valid phase convergence and visibility',
        no_model_or_prior_or_residual_gate_change=True,
        fold_endpoints_are_diagnostics_not_adopted_calibrations=True,
        no_final_holdout_all_original_points_restored=True,
        original_family_labels_are_hypotheses_not_ground_truth=True,
        rule_may_lock_in_bad_original_associations=True,
        conditional_Gaussian_predictive_scores_not_calibrated_full_posteriors=True,
        fold_scores_dependent_due_overlapping_training_data=True,
        no_GPS_or_following_TLE_or_manual_satellite_choice=True,
        confirmation_seed=2026102203,confirmation_cases=confirmation,
        confirmation_scan_disjoint_for_current_rule_but_same_site_and_previously_studied_dataset=True,
        no_confirmation_results_yet=True,per_fold_seconds=180)
    write(path,record);return record


def main():
    global RAW
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=RAW);parser.add_argument('--stage',choices=['folds','select'],required=True)
    parser.add_argument('--workers',type=int,default=12);args=parser.parse_args()
    RAW=args.raw;context.RAW=RAW;context.configure();protocol=prepare()
    if not 1<=args.workers<=24:raise ValueError('one to24workers')
    if args.stage=='select':
        if not read(RAW/'family_predictive_guard/folds_execution.json')['all_passed']:raise ValueError('finish and audit all family folds')
        rows=[select(c) for c in protocol['cases']]
        write(RAW/'family_predictive_guard/selection.json',dict(rows=rows,all_passed=True))
        return
    jobs=[]
    for case in protocol['cases']:
        d=context.current_setup(case)
        families=sorted({r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices) if d['keep'][sl].any()})
        jobs.extend((case,j,v) for j in families for v in ['baseline','expanded'])
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(fold,j) for j in jobs]):
            rows.append(future.result())
            write(RAW/'family_predictive_guard/folds_progress.json',dict(completed=len(rows),requested=len(jobs),rows=rows))
    write(RAW/'family_predictive_guard/folds_execution.json',dict(rows=rows,all_terminal=True,
          all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
