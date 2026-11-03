"""Independent clock integration checks before any geographic evaluation."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_marginal_clock import fixed_clock_node,attach_clock_prediction,MarginalClock
from algo02_scan import pair_passes
from probe_ds23_fft_grid_position import setup
from probe_ds23_marginal_clock import OUT,ARMS,prepare,components,fixed_quadrature
from run_algo01_ds23_sample import ROOT,read,write,sha


def verify_case(case):
    cache=OUT/'verification_cases'/(case+'.json')
    inputs={m:sha(OUT/(case+'_'+m+'.json')) for m in ('profile','marginal')}
    if cache.exists():
        saved=read(cache)
        if saved['input_sha256']!=inputs or saved['verification_source_sha256']!=sha(Path(__file__)):
            raise ValueError('cached numerical verification bindings changed')
        return saved
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    checks=[]
    for method in ('profile','marginal'):
        record=read(OUT/(case+'_'+method+'.json'));interval=record['interval']
        for arm in ARMS:
            r=record['arms'][arm];x=np.asarray(r['endpoint_east_north_km'])
            if method=='profile':
                shift=r['common_UTC_shift_s']
                if not interval['lower_s']-1e-12<=shift<=interval['upper_s']+1e-12:raise ValueError('UTC outside recorded bounds')
                p=fixed_clock_node(scan,node,keep,arm,np.asarray(r['phase_reference']),powers,means,model,shift)
                attach_clock_prediction(p,entries,powers);c=p.calculate(x)
                finer=None
            else:
                nodes=components(scan,node,keep,arm,powers,means,model,entries,np.asarray(r['clock_nodes_s']),np.asarray(r['phase_reference_by_node']))
                problem=MarginalClock(nodes,np.asarray(r['quadrature_weights']));c=problem.calculate(x)
                finer=fixed_quadrature(scan,node,keep,arm,powers,means,model,entries,interval,15,x)
            difference=float(c['negative_twice_elbo']-r['negative_twice_elbo'])
            if abs(difference)>1e-3:raise ValueError('saved correct-UTC RF endpoint does not reproduce')
            if r['linear_calibration_max_difference']>1e-10:raise ValueError('linear data changed node calibration')
            result=dict(method=method,arm=arm,RF_replay_difference=difference)
            if finer is not None:
                q=np.asarray(r['curved_clock_weights']);t=np.asarray(r['clock_nodes_s'])
                objective_difference=abs(finer['negative_twice_RF_bound']-r['negative_twice_elbo'])
                mean_difference=abs(finer['clock_mean_s']-float(q@t))
                result.update(endpoint_7_vs_15_objective_difference=objective_difference,
                    endpoint_clock_mean_difference_s=mean_difference,
                    refined_phase_change_s=finer['node_phase_change_s'],
                    quadrature_qualified=bool(objective_difference<=.01 and mean_difference<=.0001 and finer['node_phase_change_s']<=.01))
            checks.append(result)
    result=dict(case=case,checks=checks,input_sha256=inputs,verification_source_sha256=sha(Path(__file__)))
    cache.parent.mkdir(exist_ok=True);write(cache,result)
    return result


def stats(values):
    x=np.asarray(values)
    return dict(count=len(x),mean_km=float(x.mean()),median_km=float(np.median(x)),
                p90_km=float(np.quantile(x,.9)),maximum_km=float(x.max()),below_half_km=int(np.sum(x<=.5)))


def exact_original_rejection_fallback(trial):
    return bool(not trial['accepted'] and trial['policy_arms']==trial['incumbent_arms'] and
                not pair_passes(trial['arms'],include_linear=True))


def verify():
    protocol=prepare();cases=protocol['development_cases']+protocol['confirmation_cases']
    for part in ('development','confirmation'):
        e=read(OUT/(part+'_execution.json'))
        if not e['all_terminal'] or len(e['receipts'])!=2*len(protocol[part+'_cases']) or any('error'in r for r in e['receipts']):
            raise ValueError('all planned comparisons must complete before evaluation')
    checks=[];errors=[];pending=[]
    preserved=OUT/'verification_source_initial.py'
    accepted_sources={sha(Path(__file__))}
    if preserved.exists():accepted_sources.add(sha(preserved))
    # The numerical verification function and inference are unchanged. Bind
    # earlier complete checks to their preserved exact source and fit digests.
    for case in cases:
        cache=OUT/'verification_cases'/(case+'.json')
        if not cache.exists():pending.append(case);continue
        cached=read(cache)
        inputs={m:sha(OUT/(case+'_'+m+'.json')) for m in ('profile','marginal')}
        if cached['input_sha256']!=inputs or cached['verification_source_sha256'] not in accepted_sources:
            raise ValueError('existing numerical check source or fit binding changed')
        checks.append(cached)
    with ProcessPoolExecutor(max_workers=24) as pool:
        futures={pool.submit(verify_case,c):c for c in pending}
        for f in as_completed(futures):
            try:checks.append(f.result())
            except Exception as exc:errors.append(dict(case=futures[f],error=repr(exc)))
            write(OUT/'verification_progress.json',dict(completed=len(checks)+len(errors),total=len(cases),errors=errors))
    qualified=not errors and all(c.get('quadrature_qualified',True) for r in checks for c in r['checks'])
    rejected_failures=[];policy_qualified=not errors
    for r in checks:
        failed=[c for c in r['checks'] if not c.get('quadrature_qualified',True)]
        if not failed:continue
        trial=read(OUT/(r['case']+'_marginal.json'))
        exact_fallback=exact_original_rejection_fallback(trial)
        policy_qualified=bool(policy_qualified and exact_fallback)
        rejected_failures.append(dict(case=r['case'],failed_checks=failed,
            exact_original_fallback_verified=exact_fallback,
            original_phase_changes_s={a:trial['arms'][a]['final_phase_change_s'] for a in ARMS}))
    result=dict(checks=checks,errors=errors,all_terminal=True,all_numerically_qualified=qualified,
        all_policy_numerically_qualified=policy_qualified,rejected_trial_numerical_failures=rejected_failures,
        no_scan_or_observation_removed=True,failed_trial_never_promoted=True,
        no_GPS_read=True,source_sha256=sha(Path(__file__)))
    write(OUT/'verification.json',result);print('Verification: raw trials',qualified,'policies',policy_qualified,'errors',errors,flush=True)


def evaluate():
    protocol=prepare();validation=read(OUT/'verification.json')
    if not validation['all_terminal'] or not validation['all_policy_numerically_qualified']:
        raise ValueError('numerical verification must qualify before geographic evaluation')
    from report_algo02_ds23 import position_error
    rows=[];summary={};fig,axes=plt.subplots(2,2,figsize=(14,8))
    for row,part in enumerate(('development','confirmation')):
        summary[part]={}
        for col,arm in enumerate(ARMS):
            summary[part][arm]={};ax=axes[row,col]
            for offset,method in ((-.17,'profile'),(.17,'marginal')):
                before=[];after=[];raw=[];accepted=[]
                for case in protocol[part+'_cases']:
                    d=read(OUT/(case+'_'+method+'.json'));trial=d['arms'][arm];old=d['incumbent_arms'][arm]
                    before.append(position_error(old['endpoint_latlon']));after.append(position_error(d['policy_arms'][arm]['endpoint_latlon']))
                    raw.append(position_error(trial['endpoint_latlon']));accepted.append(d['accepted'])
                    q=np.asarray(trial.get('curved_clock_weights',[1.]));times=np.asarray(trial.get('clock_nodes_s',[trial.get('common_UTC_shift_s',0.)]))
                    rows.append(dict(case=case,cohort=part,arm=arm,method=method,accepted=d['accepted'],
                        incumbent_error_km=before[-1],policy_error_km=after[-1],raw_trial_error_km=raw[-1],
                        clock_mean_s=float(q@times),clock_sigma_s=float(np.sqrt(q@((times-q@times)**2))),
                        frequency_RMS_incumbent_hz=old['RMS_hz'],frequency_RMS_trial_MAP_hz=trial['RMS_hz'],
                        curved_clock_gate_pass_mass=trial.get('curved_clock_gate_pass_mass',1.)))
                change=np.asarray(after)-before
                summary[part][arm][method]=dict(incumbent=stats(before),policy=stats(after),raw_trial=stats(raw),
                    accepted=int(sum(accepted)),improved_scans=int(np.sum(change< -1e-9)),worsened_scans=int(np.sum(change>1e-9)),
                    mean_and_median_improve=bool(np.mean(after)<np.mean(before) and np.median(after)<np.median(before)))
                ax.bar(np.arange(len(change))+offset,1000*change,width=.32,label=method,
                    color='#638cb6' if method=='profile' else '#9b69ac')
            ax.axhline(0,color='black',lw=.8);ax.set(xticks=range(len(change)),xticklabels=[c.split('-')[-1] for c in protocol[part+'_cases']],
                xlabel='DS23 scan',ylabel='Position error change (m; negative improves)',title=f'{part} · {arm}')
            ax.tick_params(axis='x',rotation=60,labelsize=7);ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('DS23 · correct UTC geometry · point fit versus bounded clock integration\nOriginal observations, causal TLEs, priors and regional starts; failed paired gates retain the incumbent')
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'position_error_changes.png',dpi=175);plt.close(fig)
    primary={m:all(summary[p]['fitted_c'][m]['mean_and_median_improve'] for p in summary) for m in ('profile','marginal')}
    with (OUT/'position_comparison.csv').open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write(OUT/'evaluation.json',dict(summary=summary,primary_confirmed=primary,count=40,population=413,
        geometric_reference_only_here=True,verified_before_GPS=True,no_old_wrong_UTC_geometry_used=True,
        verification_sha256=sha(OUT/'verification.json'),source_sha256=sha(Path(__file__)),goal_achieved=False,
        rejected_trial_numerical_failures=validation['rejected_trial_numerical_failures']))
    print(summary,flush=True);print('Primary confirmed',primary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('verify','evaluate'),required=True)
    args=parser.parse_args();verify() if args.stage=='verify' else evaluate()
