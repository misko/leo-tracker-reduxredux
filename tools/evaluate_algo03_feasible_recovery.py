"""Post-fit GPS reporting; inference tools never import this module."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_algo03_feasible_recovery import OUT,SOURCE
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read,write


def main():
    cases=read(SOURCE/'protocol.json')['cases'];rows=[]
    for case in cases:
        old=read(SOURCE/(case+'_position.json'))
        trial_path=OUT/(case+'.json');trial=read(trial_path) if trial_path.exists() else None
        baseline=old['baseline_policy_arms']
        for method,previous in old['results'].items():
            current=trial['results'][method] if trial else previous
            for arm in ('c0','fitted_c'):
                rows.append(dict(case=case,method=method,arm=arm,
                    baseline_error_km=position_error(baseline[arm]['endpoint_latlon']),
                    unconstrained_error_km=position_error(previous['policy_arms'][arm]['endpoint_latlon']),
                    constrained_error_km=position_error(current['policy_arms'][arm]['endpoint_latlon']),
                    constrained_recovery_accepted=current.get('linear_paired_valid',False) if not current.get('unchanged') else False,
                    new_curved_points=current.get('new_curved_points',0)))
    summary={}
    for method in ('unassociated_winners','additional_native_peaks'):
        summary[method]={}
        for arm in ('c0','fitted_c'):
            selected=[r for r in rows if r['method']==method and r['arm']==arm]
            summary[method][arm]={k:[float(np.mean([r[k] for r in selected])),float(np.median([r[k] for r in selected]))]
                for k in ('baseline_error_km','unconstrained_error_km','constrained_error_km')}
    write(OUT/'cohort_evaluation.json',dict(rows=rows,summary=summary,
        exact_frozen_ALGO02_error_metric=True,GPS_used_only_for_postfit_reporting=True,
        negative_or_mixed_result_not_promoted=True))
    fig,axes=plt.subplots(1,2,figsize=(12,4.3),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        selected=[r for r in rows if r['method']=='additional_native_peaks' and r['arm']==arm]
        y=np.arange(len(selected))
        ax.scatter(y,[r['baseline_error_km'] for r in selected],s=35,label='Frozen ALGO02',color='black')
        ax.scatter(y,[r['unconstrained_error_km'] for r in selected],s=35,label='Curved recovery',marker='s',color='tab:blue')
        ax.scatter(y,[r['constrained_error_km'] for r in selected],s=40,label='Constrained recovery',marker='x',color='tab:orange')
        ax.axhline(.5,ls='--',color='grey',lw=1)
        ax.set_xticks(y,[r['case'].split('-')[1] for r in selected],rotation=90)
        ax.set_title(arm);ax.set_ylabel('Position error (km)');ax.set_xlabel('DS23 development scan')
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Unchanged-gate recovery: two feasible rescues; small, mixed position effect')
    fig.savefig(OUT/'position_effects.png',dpi=160);plt.close(fig)
    print(summary)


if __name__=='__main__':
    main()
