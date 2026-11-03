"""Compare position accuracy separately from pre-RF predictive-density gains."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_skew_phase_position import OUT,QUALIFICATION,ARMS
from probe_ds23_channel_calibration import prior_case
from probe_algo03_frame_peak_recovery import SOURCE
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read,write


def main():
    protocol=read(OUT/'protocol.json');execution=read(OUT/'execution.json')
    assert execution['all_terminal']
    failures={r['case']:r for r in execution['results'] if 'error' in r}
    rows=[];max_feedback=0.;max_null=0.
    for case in protocol['cases']:
        d=read(OUT/(case+'.json')) if (OUT/(case+'.json')).exists() else None
        baseline=read(SOURCE/case/'algo02_result.json')['policy_arms']
        shifted=prior_case(case)['policy_arms']
        selection=read(QUALIFICATION/(case+'.json'))['selection']
        if d and d.get('qualified'):
            max_null=max(max_null,*map(abs,d['null_RF_differences']))
            for r in d['results']['skew'].values():max_feedback=max(max_feedback,r['linear_calibration_max_difference'])
        for arm in ARMS:
            variants=dict(original=baseline[arm],location=shifted[arm],
                scalar=d['scalar_policy_arms'][arm] if d else baseline[arm],
                skew=d['skew_policy_arms'][arm] if d else baseline[arm])
            rows.append(dict(case=case,cohort=case in protocol['cohort'],arm=arm,
                **{name+'_error_km':position_error(r['endpoint_latlon']) for name,r in variants.items()},
                qualified=selection['qualified'],kappa=selection['kappa'],
                scalar_accepted=bool(d and d.get('qualified') and d['paired_valid']['scalar']),
                skew_accepted=bool(d and d.get('qualified') and d['paired_valid']['skew']),
                RF_skew_vs_scalar_gain=variants['scalar']['negative_twice_elbo']-variants['skew']['negative_twice_elbo'],
                RMS_original_hz=variants['original']['RMS_hz'],RMS_skew_hz=variants['skew']['RMS_hz']))
    cohort_label='cohort'+str(len(protocol['cohort']))
    diagnostic_label='diagnostics'+str(len(protocol['diagnostic_cases']))
    all_label='all'+str(len(protocol['cases']))
    summary={}
    for group in (cohort_label,diagnostic_label,all_label):
        if group==diagnostic_label and not protocol['diagnostic_cases']:continue
        summary[group]={}
        for arm in ARMS:
            chosen=[r for r in rows if r['arm']==arm and
                    (group==all_label or r['cohort']==(group==cohort_label))]
            summary[group][arm]={}
            for method in ('original','location','scalar','skew'):
                values=np.array([r[method+'_error_km'] for r in chosen])
                summary[group][arm][method]=dict(count=len(values),mean_km=float(values.mean()),
                    median_km=float(np.median(values)),maximum_km=float(values.max()),below_half_km=int(sum(values<=.5)))
    write(OUT/'evaluation.json',dict(summary=summary,failures=failures,
        maximum_null_RF_difference=max_null,maximum_predictive_calibration_update=max_feedback,
        development_set_not_a_position_generalization_proof=True,
        better_historical_TLE_density_is_not_better_position_accuracy=True))
    with (OUT/'positions.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    styles=dict(original=('Original ALGO02','#777777','--'),location=('Signed location prior','#bc7438',':'),
                scalar=('Symmetric, matched optimizer','#397ba2','-'),skew=('Asymmetric, matched optimizer','#823f8b','-'))
    for ax,arm in zip(axes,ARMS,strict=True):
        chosen=[r for r in rows if r['arm']==arm and r['cohort']]
        for method,(label,color,line) in styles.items():
            values=np.sort([r[method+'_error_km'] for r in chosen]);s=summary[cohort_label][arm][method]
            ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/len(values)],where='post',color=color,ls=line,
                label=f'{label}: {s["mean_km"]:.3f}/{s["median_km"]:.3f} km')
        ax.axvline(.5,color='green',lw=.8,ls=':')
        ax.set(xlabel='Position error (km)',ylabel='Fraction of all '+str(len(chosen))+' recordings',title=arm,ylim=(0,1.02))
        ax.grid(alpha=.15);ax.legend(fontsize=8,loc='lower right')
    fig.suptitle(str(len(protocol['cohort']))+' matched DS23 recordings · legend gives mean/median\n'
                 'Same phase variance and mode; asymmetric tails qualified solely on earlier TLE updates',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'position_error_distribution.png',dpi=180,bbox_inches='tight');plt.close(fig)
    if not protocol['diagnostic_cases']:
        print(summary,flush=True)
        return
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    diagnostics=[r for r in rows if not r['cohort']]
    for ax,arm in zip(axes,ARMS,strict=True):
        chosen=[r for r in diagnostics if r['arm']==arm];x=np.arange(len(chosen))
        for j,method in enumerate(('original','location','skew')):
            label,color,line=styles[method]
            ax.bar(x+(j-1)*.24,[r[method+'_error_km'] for r in chosen],.24,color=color,label=label)
        ax.set_xticks(x,[r['case'].replace('DS23-','') for r in chosen]);ax.set_ylabel('Position error (km)')
        ax.set_title(arm);ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('Four adaptive regressions selected for explicit diagnosis\nNot an independent validation subset',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'adaptive_regression_diagnostics.png',dpi=180,bbox_inches='tight');plt.close(fig)
    print(summary,flush=True)


if __name__=='__main__':main()
