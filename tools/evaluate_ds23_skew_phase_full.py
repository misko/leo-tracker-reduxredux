"""Complete-population comparison of unchanged asymmetric phase inference."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error
from evaluate_ds23_causal_phase_location_full import aggregate,capture_format

OUT=ROOT/'reports/2026_10_20_ds23_skew_phase_full'
SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'
LOCATION=ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'
ARMS=('c0','fitted_c')
METHODS=('original','location','scalar','skew')


def main():
    protocol=read(OUT/'protocol.json');execution=read(OUT/'execution.json')
    if not execution['all_terminal'] or len(execution['results'])!=len(protocol['cases']):
        raise ValueError('full experiment must be terminal before geographic evaluation')
    for path,digest in protocol['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('frozen inference source changed')
    receipts={r['case']:r for r in execution['results']}
    if len(receipts)!=len(protocol['cases']):raise ValueError('duplicate execution receipt')
    location=read(LOCATION/'evaluation_audit.json')['evidence']
    rows=[];evidence={};failures=[];max_feedback=0.;max_null=0.
    for member in protocol['population']:
        case=member['dataset_label'];capture=capture_format(member['recording_format'])
        if case not in receipts:
            for arm in ARMS:rows.append(dict(case=case,arm=arm,format=capture,remaining=False,
                **{m+'_error_km':None for m in METHODS},qualified=False,accepted=False,kappa=0.,execution_failed=False,
                original_RMS_hz=None,skew_RMS_hz=None))
            continue
        receipt=receipts[case];old=read(SOURCE/case/'algo02_result.json');baseline=old['policy_arms']
        shifted=read(ROOT/location[case]['path'])['policy_arms']
        failed='error' in receipt
        if failed:
            failures.append(receipt);d=None;q=None
        else:
            d=read(ROOT/receipt['position']);q=read(ROOT/receipt['qualification'])
            if d['baseline_arms']!=baseline or d['GPS_used'] or d['future_TLE_used']:
                raise ValueError('baseline/causality mismatch')
            history=SOURCE/'causal_phase_history'/(case+'.json');forecast=history.with_name(case+'_forecast.json')
            if sha(history)!=q['history_sha256'] or sha(forecast)!=q['forecast_sha256']:
                raise ValueError('historical prior input changed')
            if d['qualified']:
                if d['original_mask']!=old['mask']:raise ValueError('original observations changed')
                max_null=max(max_null,*map(abs,d['null_RF_differences']))
                for method in ('scalar','skew'):
                    for r in d['results'][method].values():
                        max_feedback=max(max_feedback,r['linear_calibration_max_difference'])
                        if d['paired_valid'][method]:
                            assert r['skew_solver_qualified'] and r['final_phase_change_s']<=.01
                            assert all(g['compatible'] for g in r['gates']['tracks']+r['linear_gates'])
            evidence[case]=dict(position=receipt['position'],position_sha256=sha(ROOT/receipt['position']),
                qualification=receipt['qualification'],qualification_sha256=sha(ROOT/receipt['qualification']))
        for arm in ARMS:
            variants=dict(original=baseline[arm],location=shifted[arm],
                scalar=d['scalar_policy_arms'][arm] if d else baseline[arm],
                skew=d['skew_policy_arms'][arm] if d else baseline[arm])
            rows.append(dict(case=case,arm=arm,format=capture,remaining=case in protocol['additional_confirmation'],
                **{m+'_error_km':position_error(r['endpoint_latlon']) for m,r in variants.items()},
                qualified=bool(d and d['qualified']),accepted=bool(d and d['qualified'] and d['paired_valid']['skew']),
                kappa=q['selection']['kappa'] if q else 0.,execution_failed=failed,
                original_RMS_hz=baseline[arm]['RMS_hz'],skew_RMS_hz=variants['skew']['RMS_hz']))
    groups=dict(all=rows,remaining340=[r for r in rows if r['remaining']],
                fast=[r for r in rows if r['format']=='fast'],adaptive=[r for r in rows if r['format']=='adaptive'])
    summary={}
    for group,chosen in groups.items():
        summary[group]={}
        for method in METHODS:
            summary[group][method]=aggregate([dict(arm=r['arm'],baseline_error_km=r['original_error_km'],error_km=r[method+'_error_km']) for r in chosen])
    positive=all(summary[g]['skew'][a]['trial'][metric]<summary[g][reference][a]['trial'][metric]
        for g in ('all','remaining340') for reference in ('original','location','scalar')
        for a in ARMS for metric in ('mean_km','median_km')) and not failures
    goal=all(summary['all']['skew'][a]['unavailable']==0 and
             summary['all']['skew'][a]['trial']['mean_km']<=.5 and
             summary['all']['skew'][a]['trial']['median_km']<=.5 for a in ARMS)
    write(OUT/'evaluation.json',dict(summary=summary,failures=failures,
        positive_generalization_criterion_pass=bool(positive),goal_met=bool(goal),
        maximum_predictive_calibration_update=max_feedback,maximum_original_RF_replay_difference=max_null,
        GPS_only_in_reporter=True,all_unavailable_and_failed_trials_retained=True,
        controls_have_fixed_original_satellite_associations_not_new_cold_discovery=True))
    write(OUT/'evaluation_audit.json',dict(evidence=evidence,new_frozen_sources_match=True))
    with (OUT/'positions.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,ARMS,strict=True):
        chosen=[r for r in rows if r['arm']==arm and r['original_error_km'] is not None]
        for method in METHODS:
            values=np.sort([r[method+'_error_km'] for r in chosen]);s=summary['all'][method][arm]['trial']
            ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/413],where='post',
                label=f'{method}: {s["mean_km"]:.3f}/{s["median_km"]:.3f} km')
        ax.axvline(.5,color='gray',ls=':',lw=.8)
        ax.set(xlabel='Position error (km)',ylabel='Fraction of all 413 recordings',title=arm,ylim=(0,1.02))
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('Full DS23 asymmetric-prior confirmation · legend: mean/median\n'
                 'Original unavailable positions remain in the denominator; all accepted outliers are shown',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'position_error_distribution.png',dpi=180,bbox_inches='tight');plt.close(fig)
    print('Positive full comparison:',positive,'goal met:',goal,'failures:',len(failures),flush=True)
    for group in summary:
        for arm in ARMS:
            print(group,arm,{m:(summary[group][m][arm]['trial']['mean_km'],summary[group][m][arm]['trial']['median_km']) for m in METHODS},flush=True)


if __name__=='__main__':main()
