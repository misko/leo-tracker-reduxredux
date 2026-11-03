"""Independent causal-feature and model replay; no geographic evaluation."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_tle_state_filter import pack,filter_histories
from ds23_phase_score_filter import filter_with_mean
from prepare_ds23_tle_state_filter import extract
from probe_ds23_tle_state_filter import OUT as JOINT,qualify as joint_qualify,baseline_cost
from ds23_causal_phase_location import fit_location
from probe_ds23_phase_score_filter import OUT as PHASE,prepare,qualify as phase_qualify
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha


def verify_case(case):
    history_path=SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path=history_path.with_name(case+'_forecast.json');elements_path=SOURCE/case/'nominal_elements.json'
    history,forecast=read(history_path),read(forecast_path)
    features=extract(history,forecast,read(elements_path));checks=[];strata=[]
    for kind,directory,function in (('joint',JOINT,joint_qualify),('phase',PHASE,phase_qualify)):
        path=directory/(case+'_filter.json');saved=read(path);feature_path=directory/(case+'_features.json')
        if (sha(history_path)!=saved['history_sha256'] or sha(forecast_path)!=saved['forecast_sha256'] or
                sha(elements_path)!=saved['elements_sha256'] or sha(feature_path)!=saved['features_sha256']):
            raise ValueError('causal input binding changed')
        if read(feature_path)!=features:
            raise ValueError('independent feature extraction did not replay')
        recomputed=function(features,forecast,saved['baseline_model'],saved['baseline_bias_enabled'])
        if recomputed!=saved['selection']:
            raise ValueError('historical optimization or qualification did not replay exactly')
        checks.append(dict(kind=kind,qualified=recomputed['qualified'],result_sha256=sha(path),
            original_target_replay_max_error_s=recomputed['original_forecast_target_replay_max_error_s']))
        data=pack(features['series']);parameters=recomputed['prefix_model']['parameters']
        predicted=filter_histories(data,parameters) if kind=='joint' else filter_with_mean(data,parameters)
        boundary=forecast['temporal_split_boundary_ns'];prefix=forecast['prefix_distribution']
        training=[r for s in features['series'] for r in s['baseline_transitions'] if r and
                  r['validation_time_ns']<=boundary and r['norad']%5!=0]
        bias=fit_location(training,prefix) if saved['baseline_bias_enabled'] else None
        baseline,_=baseline_cost(data,features,prefix,bias)
        # Diagnostic strata only: neither these labels nor their scores select
        # a training subset or an RF policy. Reference ages are known in advance.
        future=data['score_eligible'] & (data['publication']>forecast['temporal_split_boundary_ns'])
        transport=np.array([r['maximum_phase_transport_discrepancy_s'] for r in features['series']])
        for label,mask in (
                ('reference_age_under_12h',future & (data['times']<12)),
                ('reference_age_12_to_24h',future & (data['times']>=12) & (data['times']<24)),
                ('reference_age_over_24h',future & (data['times']>=24)),
                ('small_full_history_transport_error_under_1ms',future & (transport[:,None]<.001)),
                ('large_full_history_transport_error_over_10ms',future & (transport[:,None]>.01))):
            if mask.sum():
                strata.append(dict(kind=kind,stratum=label,count=int(mask.sum()),
                    phase_prediction_cost=float(predicted['phase_cost'][mask].sum()),
                    gain_vs_baseline=float((baseline-predicted['phase_cost'])[mask].sum()),
                    mean_winsorized_phase_innovation=float(np.mean(np.clip(predicted['standardized'][mask],-3,3)))))
    return dict(case=case,checks=checks,strata=strata,no_GPS_used=True,
        candidate_histories=len(features['series']),rejected=features['rejected'])


def main():
    protocol=prepare();cases=protocol['development_cases']+protocol['confirmation_cases']
    receipts=[];errors=[]
    with ProcessPoolExecutor(max_workers=16) as pool:
        futures={pool.submit(verify_case,c):c for c in cases}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:errors.append(dict(case=futures[f],error=repr(exc)))
    verified=not errors and len(receipts)==40
    write(PHASE/'independent_verification.json',dict(qualified=verified,all_terminal=True,receipts=receipts,errors=errors,
        source_sha256=sha(ROOT/'tools/audit_ds23_tle_state_filters.py'),no_GPS_used=True))
    if not verified:raise ValueError('state-filter replay failures: '+repr(errors))
    rows=[];summary={}
    for kind,directory in (('joint',JOINT),('phase',PHASE)):
        qualified=[]
        for case in cases:
            result=read(directory/(case+'_filter.json'))['selection']
            if result['qualified']:qualified.append(case)
            for partition,v in result['validation'].items():
                d=v['phase_residual_diagnostics']
                rows.append(dict(case=case,kind=kind,partition=partition,qualified=result['qualified'],
                    count=v['count'],gain_vs_baseline=v['gain_vs_baseline'],gain_vs_measurement_off=v['gain_vs_measurement_off'],
                    gain_per_transition_vs_baseline=v['gain_vs_baseline']/v['count'],
                    gain_per_transition_vs_measurement_off=v['gain_vs_measurement_off']/v['count'],
                    residual_mean=d['winsorized_mean'],residual_adjacent_correlation=d['winsorized_adjacent_correlation'],
                    residual_diagnostics_pass=d['compatible']))
        summary[kind]=dict(qualified_count=len(qualified),qualified_cases=qualified,
            later_density_beats_baseline_count=sum(r['gain_vs_baseline']>0 for r in rows if r['kind']==kind and r['partition']=='future'),
            later_density_beats_measurement_off_count=sum(r['gain_vs_measurement_off']>0 for r in rows if r['kind']==kind and r['partition']=='future'))
    with (PHASE/'historical_validation.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    figure,axes=plt.subplots(2,2,figsize=(13,9))
    for row,kind in enumerate(('joint','phase')):
        for col,partition in enumerate(('future','disjoint_future')):
            ax=axes[row,col]
            for cohort,color in (('development','#3b78aa'),('confirmation','#c2793b')):
                subset=[r for r in rows if r['kind']==kind and r['partition']==partition and r['case'] in protocol[cohort+'_cases']]
                ax.scatter([r['gain_per_transition_vs_baseline'] for r in subset],
                    [r['gain_per_transition_vs_measurement_off'] for r in subset],color=color,label=cohort,alpha=.75)
            ax.axvline(0,color='black',lw=.8);ax.axhline(0,color='black',lw=.8);ax.grid(alpha=.15)
            ax.set(title=kind+' fit · '+partition,xlabel='Density gain / transition versus existing prior',
                ylabel='Density gain / transition versus measurement-off model');ax.legend(fontsize=8)
    figure.suptitle('DS23 · separating latent orbit state from TLE measurement noise\n'
        'Both gains must be positive and exceed fixed penalties; these are correlated revision proxies, not orbit truth')
    figure.tight_layout(rect=(0,0,1,.92));figure.savefig(PHASE/'historical_qualification.png',dpi=175);plt.close(figure)
    write(PHASE/'qualification_summary.json',dict(models=summary,count=40,all_jobs_terminal=True,
        independent_replay_count=40,independent_replay_errors=0,
        position_experiments_required=any(v['qualified_count'] for v in summary.values()),
        position_fits_performed=0,published_algorithm_unchanged=True,goal_achieved=False,goal_population=413,
        time_label_clarification='publication_utc_ns means local archive collection/availability time; provider publication time is unmeasured',
        no_post_scan_elements_or_collection_times_used=True,
        variance_decomposition_only_valid_under_assumed_state_and_measurement_model=True,
        independent_audit_sha256=sha(PHASE/'independent_verification.json')))
    print('Verified',len(receipts),'summary',summary,flush=True)


if __name__=='__main__':
    main()
