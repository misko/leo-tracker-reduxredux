"""Readable full-population figures from independently audited position results."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_ds23_family_cavity_full import OUT
from run_algo01_ds23_sample import read,write,sha


def main():
    out=OUT/'position';audit=read(out/'independent_numerical_audit.json')
    assert audit['all_passed'] and audit['source_execution_sha256']==sha(out/'execution.json')
    evaluation=read(out/'evaluation.json');cases=read(OUT/'protocol.json')['cases'];rows=evaluation['rows']
    original=np.array([next(r for r in rows if r['case']==c)['original_error_km'] for c in cases])
    # Use one arm explicitly; original errors differ slightly between arms.
    original=np.array([next(r for r in rows if (r['case'],r['arm'])==(c,'fitted_c'))['original_error_km'] for c in cases])
    fig,axes=plt.subplots(2,2,figsize=(14,10),layout='constrained');x=np.arange(len(cases));policies=['equal_assignment_priors','incumbent_sticky_prior']
    colors=['#168b91','#8765b4'];labels=['Equal assignment priors','Incumbent preference']
    axes[0,0].plot(np.sort(original),np.arange(1,len(cases)+1)/len(cases),c='black',label='Original signed-prior incumbent')
    for policy,color,label in zip(policies,colors,labels,strict=True):
        selected=[next(r for r in rows if (r['case'],r['arm'],r['policy'])==(c,'fitted_c',policy)) for c in cases]
        error=np.array([r['policy_error_km'] for r in selected]);accepted=np.array([r['accepted'] for r in selected])
        axes[0,0].plot(np.sort(error),np.arange(1,len(error)+1)/len(error),c=color,label=label)
        axes[0,1].scatter(original[accepted],error[accepted],c=color,s=26,label=label)
        frequency=np.array([r['frequency_RMS_hz']-r['original_frequency_RMS_hz'] for r in selected])
        axes[1,1].scatter(frequency[accepted],(error-original)[accepted],c=color,s=26,label=label)
    accepted_rows=[r for r in rows if r['arm']=='fitted_c' and r['accepted']]
    limit=max(max(r['original_error_km'],r['policy_error_km']) for r in accepted_rows)*1.04
    axes[0,0].axvline(.5,c='seagreen',ls='--',lw=1,label='0.5 km goal');axes[0,0].set(xlabel='Position error (km)',ylabel='Empirical CDF')
    axes[0,0].set_xlim(0,5)
    axes[0,0].set_title(f'CDF zoom0–5km · all410cases counted · max {max(r["policy_error_km"] for r in rows if r["arm"]=="fitted_c"):.2f}km')
    axes[0,1].plot([0,limit],[0,limit],c='.5',ls='--',lw=.8);axes[0,1].set(xlabel='Original error (km)',ylabel='New error (km)',title='Accepted identity changes only')
    axes[0,1].set_xlim(0,limit);axes[0,1].set_ylim(0,limit)
    selected=[next(r for r in rows if (r['case'],r['arm'],r['policy'])==(c,'fitted_c',policies[0])) for c in cases]
    delta=np.array([r['policy_error_km']-r['original_error_km'] for r in selected]);changed=np.flatnonzero(abs(delta)>1e-6)
    ranked=sorted(changed,key=lambda k:abs(delta[k]),reverse=True)[:25];ranked=sorted(ranked,key=lambda k:delta[k])
    axes[1,0].barh(range(len(ranked)),delta[ranked],color=['#168b91' if delta[k]<0 else '#c45b47' for k in ranked])
    axes[1,0].set_yticks(range(len(ranked)),[cases[k] for k in ranked],fontsize=7);axes[1,0].invert_yaxis();axes[1,0].axvline(0,c='black',lw=.7)
    axes[1,0].set(xlabel='New minus original position error (km)',title='Largest25changes · retrospective display only')
    axes[1,1].axhline(0,c='.5',lw=.8);axes[1,1].axvline(0,c='.5',lw=.8)
    axes[1,1].set(xlabel='New minus original GLRT RMS (Hz)',ylabel='New minus original error (km)',title='Frequency fit and geographic accuracy are separate')
    for ax in axes.flat:ax.grid(alpha=.2)
    for ax in [axes[0,0],axes[0,1],axes[1,1]]:ax.legend(fontsize=7)
    fig.suptitle('Full DS23 · covariance-aware family replacement · fitted c\n410available scans; all failures/fallbacks included; identical original GLRT observations and priors')
    fig.savefig(out/'full_population_summary.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(16,5),layout='constrained')
    ax.scatter(x,original,c='black',marker='x',s=14,label='Original incumbent')
    for policy,color,label in zip(policies,colors,labels,strict=True):
        error=[next(r for r in rows if (r['case'],r['arm'],r['policy'])==(c,'fitted_c',policy))['policy_error_km'] for c in cases]
        ax.scatter(x,error,c=color,s=9,label=label)
    ticks=list(range(0,len(cases),20));ax.set_xticks(ticks,[cases[k].split('-')[1] for k in ticks],rotation=60,fontsize=8)
    ax.axhline(.5,c='seagreen',ls='--',lw=1);ax.set(xlabel='DS23 scan number',ylabel='Position error (km)',title='All410available DS23scans · unchanged and changed cases retained')
    ax.grid(alpha=.2);ax.legend(fontsize=8);fig.savefig(out/'all_scans_position_error.png',dpi=160);plt.close(fig)
    summary=[]
    for arm in ['c0','fitted_c']:
        base=evaluation['statistics'][policies[0]][arm]
        summary.append(dict(method='original_signed_prior',arm=arm,available=410,mean_km=base['original_mean_km'],median_km=base['original_median_km'],accepted_changes=0))
        for policy in policies:
            s=evaluation['statistics'][policy][arm]
            summary.append(dict(method=policy,arm=arm,available=410,mean_km=s['policy_mean_km'],median_km=s['policy_median_km'],accepted_changes=s['accepted']))
    write(out/'compact_summary.json',dict(rows=summary,all_410_cases_and_both_c_arms=True,source_evaluation_sha256=sha(out/'evaluation.json')))
    with (out/'compact_summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    print(summary,flush=True)


if __name__=='__main__':main()
