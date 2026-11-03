"""Report position accuracy only after independent joint likelihood auditing."""

import argparse
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_joint_relative_position import OUT,VARIANTS
from run_algo01_ds23_sample import read,write


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,default=OUT)
    args=parser.parse_args();out=args.directory
    assert read(out/'independent_numerical_audit.json')['all_passed']
    records=read(out/'execution.json')['rows'];protocol=read(out/'protocol.json');cases=protocol['cases'];variants=protocol['variants']
    from report_algo02_ds23 import position_error
    rows=[]
    for r in records:
        for arm,a in r['arms'].items():
            original=r['original_incumbent'][arm]
            rows.append(dict(case=r['case'],variant=r['variant'],arm=arm,accepted=r['accepted'],
                original_error_km=position_error(original['endpoint_latlon']),
                raw_error_km=position_error(a['endpoint_latlon']),
                policy_error_km=position_error(r['policy_arms'][arm]['endpoint_latlon']),
                original_GLRT_RMS_hz=original['RMS_hz'],retained_GLRT_RMS_hz=a['RMS_hz'],
                retained_curved_points=a['active_points'],retained_predictive_points=a['predictive_points'],
                relative_points=sum(g['points'] for g in a['relative_gates']),
                relative_RMS_hz=(float(np.sqrt(sum(g['points']*g['RMS_hz']**2 for g in a['relative_gates'])/sum(g['points'] for g in a['relative_gates']))) if a['relative_gates'] and all(g['RMS_hz'] is not None for g in a['relative_gates']) else None),
                failed_curved=[g['component'] for g in a['gates']['tracks'] if not g['compatible']],
                failed_predictive=[g['component'] for g in a['linear_gates'] if not g['compatible']],
                failed_relative=[g['group'] for g in a['relative_gates'] if not g['compatible']],
                phase_change_s=a['final_phase_change_s']))
    statistics={}
    for variant,_,_ in variants:
        statistics[variant]={}
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if r['variant']==variant and r['arm']==arm]
            old=np.array([r['original_error_km'] for r in selected]);new=np.array([r['policy_error_km'] for r in selected])
            statistics[variant][arm]=dict(count=len(new),accepted=sum(r['accepted'] for r in selected),
                original_mean_km=float(old.mean()),original_median_km=float(np.median(old)),
                policy_mean_km=float(new.mean()),policy_median_km=float(np.median(new)),
                improved=int(np.sum(new<old-1e-6)),worsened=int(np.sum(new>old+1e-6)))
    write(out/'evaluation.json',dict(rows=rows,statistics=statistics,report_only_GPS=True,
        independent_audit_completed_before_error_evaluation=True,all_failed_gates_use_original_incumbent=True,
        development_only_no_generalization_or_full_DS23_claim=True))
    with (out/'positions.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,3,figsize=(15,4.7),layout='constrained')
    colors=['#777777','#168b91','#c18c35']
    for i,case in enumerate(cases):
        original=next(r for r in rows if r['case']==case and r['arm']=='fitted_c')
        axes[0].scatter(i,original['original_error_km'],c='black',s=70,marker='*',label='Unquarantined incumbent' if i==0 else None)
        for j,(variant,_,_) in enumerate(variants):
            r=next(r for r in rows if r['case']==case and r['variant']==variant and r['arm']=='fitted_c')
            for ax,key in zip(axes,['raw_error_km','retained_GLRT_RMS_hz','relative_RMS_hz'],strict=True):
                if r[key] is not None:ax.scatter(i+(j-1)*.14,r[key],color=colors[j],s=45,
                    marker='o' if r['accepted'] else 'x',label=variant if i==0 and ax is axes[0] else None)
    for ax,label in zip(axes,['Position error (km)','Retained GLRT RMS (Hz)','Relative-curve RMS (Hz)'],strict=True):
        ax.set_xticks(range(len(cases)),[c.split('-')[1] for c in cases]);ax.set(xlabel='DS23 development scan',ylabel=label);ax.grid(alpha=.2)
    axes[0].axhline(.5,color='seagreen',ls='--',lw=1);axes[0].legend(fontsize=7)
    fig.suptitle('IQ-disjoint GLRT + full relative curves · matched quarantine control\nRaw development endpoints; circles pass paired gates, crosses reject; frequency fit is not position accuracy')
    fig.savefig(out/'development_comparison.png',dpi=165);plt.close(fig)
    for r in rows:
        if r['arm']=='fitted_c':print(r,flush=True)


if __name__=='__main__':main()
