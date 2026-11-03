"""Verify TLE-only mean selection and RF replay before geographic reporting."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from algo02_scan import pair_passes
from ds23_continuous_forecast import qualify
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import summary
from probe_ds23_continuous_forecast import OUT,ARMS,prepare,means_for
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import read,write,sha


def verify_case(case):
    proposal_path,position_path=OUT/(case+'_forecast.json'),OUT/(case+'_position.json')
    proposed,record=read(proposal_path),read(position_path)
    scan,node,keep,base,old,signed,binding,model,powers,old_means,entries=setup(case)
    forecast_path=SOURCE/'causal_phase_history'/(case+'_forecast.json')
    if sha(forecast_path)!=proposed['historical_forecast_sha256'] or sha(proposal_path)!=record['proposal_sha256']:
        raise ValueError('historical forecast or proposal bytes changed')
    recomputed=qualify(read(forecast_path),model,proposed['baseline_bias_enabled'],proposed['baseline_full_bias'])
    if recomputed!=proposed['selection']:
        raise ValueError('historical forecast qualification or gain changed')
    if binding!=record['incumbent_binding'] or record['incumbent_arms']!=signed['policy_arms']:
        raise ValueError('published incumbent binding changed')
    np.testing.assert_array_equal(keep,record['original_mask'])
    _,receipts=phase_widths(scan,base.labels)
    checks=[]
    for method,key in (('coarse','all_past_coarse'),('continuous','all_past_fine')):
        result=record['methods'][method]
        if not result['arms']:
            if result['policy_arms']!=record['incumbent_arms'] or result['accepted']:
                raise ValueError('unfitted method did not retain the exact incumbent')
            continue
        rho=proposed['selection'][key]['gain']
        if rho!=result['gain']:
            raise ValueError('RF fit used a different gain')
        means=means_for(receipts,model,signed,rho)
        np.testing.assert_allclose(means,result['means_s'],atol=1e-12,rtol=0)
        fresh={};actual=[]
        for arm in ARMS:
            r=result['arms'][arm]
            p=make_event_problem(scan,node,keep,arm,np.asarray(r['phase_reference']),powers,means,model,[])
            attach_event_predictive(p,entries,powers)
            x=np.asarray(r['endpoint_east_north_km'])
            d=summary(p,x,entries)
            difference=d['negative_twice_elbo']-r['negative_twice_elbo']
            if abs(difference)>1e-3:raise ValueError('refined mean endpoint does not replay')
            if [g['compatible'] for g in d['gates']['tracks']+d['linear_gates']] != [g['compatible'] for g in r['gates']['tracks']+r['linear_gates']]:
                raise ValueError('original residual gates changed')
            phase=np.asarray(d['state']['phases'])[base.labels]
            actual.append(np.max(abs(phase-np.asarray(r['phase_reference'])))<=.01 and np.max(abs(phase))<=15)
            fresh[arm]=dict(d,final_phase_change_s=r['final_phase_change_s'])
            checks.append(dict(method=method,arm=arm,RF_difference=difference))
        accepted=bool(pair_passes(fresh,include_linear=True) and all(actual))
        if result['accepted']!=accepted or result['policy_arms']!=(result['arms'] if accepted else record['incumbent_arms']):
            raise ValueError('method acceptance or entire-pair fallback changed')
    return dict(case=case,checks=checks,position_sha256=sha(position_path),proposal_sha256=sha(proposal_path),no_GPS_used=True)


def verify(part):
    protocol=prepare()
    cases=protocol['pilot_cases'] if part=='pilot' else protocol['development_cases']+protocol['confirmation_cases']
    receipts,errors=[],[]
    with ProcessPoolExecutor(max_workers=min(16,len(cases))) as pool:
        futures={pool.submit(verify_case,c):c for c in cases}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:errors.append(dict(case=futures[f],error=repr(exc)))
    write(OUT/(part+'_verification.json'),dict(all_terminal=True,qualified=not errors and len(receipts)==len(cases),
        receipts=receipts,errors=errors,no_GPS_used=True))
    print('Verified',len(receipts),'errors',errors,flush=True)


def stats(values):
    a=np.asarray(values)
    return dict(count=len(a),mean_km=float(a.mean()),median_km=float(np.median(a)),p90_km=float(np.quantile(a,.9)),below_half_km=int(np.sum(a<=.5)))


def evaluate():
    protocol=prepare();validation=read(OUT/'cohort_verification.json')
    if not validation['qualified'] or len(validation['receipts'])!=40:
        raise ValueError('complete RF verification required before geographic evaluation')
    bindings={r['case']:r for r in validation['receipts']}
    from report_algo02_ds23 import position_error
    rows,results=[],{}
    figure,axes=plt.subplots(2,2,figsize=(14,9))
    for row,cohort in enumerate(('development','confirmation')):
        results[cohort]={}
        for column,arm in enumerate(ARMS):
            values={k:[] for k in ('incumbent','coarse','continuous')}
            for case in protocol[cohort+'_cases']:
                path=OUT/(case+'_position.json')
                if sha(path)!=bindings[case]['position_sha256']:raise ValueError('verified fit changed')
                r=read(path);proposal=read(OUT/(case+'_forecast.json'))
                values['incumbent'].append(position_error(r['incumbent_arms'][arm]['endpoint_latlon']))
                for method in ('coarse','continuous'):
                    m=r['methods'][method]
                    values[method].append(position_error(m['policy_arms'][arm]['endpoint_latlon']))
                    rows.append(dict(case=case,cohort=cohort,arm=arm,method=method,
                        historically_qualified=proposal['selection']['qualified'],accepted=m['accepted'],
                        incumbent_error_km=values['incumbent'][-1],policy_error_km=values[method][-1],
                        gain=m.get('gain'),incumbent_gain=proposal['baseline_model']['shrinkage'],
                        RF_RMS_incumbent_hz=r['incumbent_arms'][arm]['RMS_hz'],RF_RMS_policy_hz=m['policy_arms'][arm]['RMS_hz']))
            results[cohort][arm]={k:stats(v) for k,v in values.items()}
            for method in ('coarse','continuous'):
                results[cohort][arm][method]['mean_and_median_improve']=bool(
                    np.mean(values[method])<np.mean(values['incumbent']) and np.median(values[method])<np.median(values['incumbent']))
            ax=axes[row,column]
            for kind,color,label in (('incumbent','black','Published signed prior'),('coarse','#3d83a5','Matched five-point gain'),('continuous','#a064aa','Continuous gain')):
                a=np.sort(values[kind]);ax.step(np.r_[0,a],np.r_[0,np.arange(1,len(a)+1)/len(a)],where='post',color=color,label=label)
            ax.axvline(.5,color='gray',ls=':');ax.set(title=cohort+' · '+arm,xlabel='Position error (km)',ylabel='Fraction of complete cohort',ylim=(0,1.02));ax.grid(alpha=.15);ax.legend(fontsize=8)
    figure.suptitle('DS23 · causal phase-forecast gain refinement · all other priors and observations fixed\n'
        'Historical time/satellite validation before RF fitting; original paired gates and exact fallback')
    figure.tight_layout(rect=(0,0,1,.92));figure.savefig(OUT/'position_error_distribution.png',dpi=175);plt.close(figure)
    primary=all(results[c]['fitted_c']['continuous']['mean_and_median_improve'] for c in results)
    write(OUT/'evaluation.json',dict(results=results,primary_confirmed=primary,count=40,goal_population=413,goal_achieved=False,
        GPS_used_only_here=True,verification_sha256=sha(OUT/'cohort_verification.json')))
    with (OUT/'position_comparison.csv').open('w') as handle:
        w=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    print(results,flush=True);print('Primary confirmed',primary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('verify-pilot','verify-cohort','evaluate'),required=True)
    args=parser.parse_args()
    evaluate() if args.stage=='evaluate' else verify('pilot' if args.stage=='verify-pilot' else 'cohort')
