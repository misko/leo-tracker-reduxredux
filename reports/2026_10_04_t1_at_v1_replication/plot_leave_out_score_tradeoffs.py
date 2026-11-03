"""Decompose saved same-full-model score changes, without another fit."""
import csv
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from characterize_leave_one_out import OUT,csv_file
from timing_model import INDIVIDUAL_SHIFT_SIGMA_S,GLOBAL_SHIFT_SIGMA_S


def timing_terms(record):
    common=record['vector'][6]
    delta=np.array(record['parameters'][6:])-common
    return .5*(delta/INDIVIDUAL_SHIFT_SIGMA_S)**2,.5*(common/GLOBAL_SHIFT_SIGMA_S)**2


def main():
    saved=json.loads((OUT/'role-diagnostics.json').read_text())
    with (OUT/'same-model-score-tradeoffs.csv').open() as f:tradeoffs=list(csv.DictReader(f))
    rows=[]
    for row in tradeoffs:
        scan,arm,n=row['scan'],row['arm'],int(row['satellite'])
        baseline=json.loads((OUT/scan/'baseline.json').read_text())
        base=baseline['arms'][arm]['best']
        other=saved['receipts'][scan]['deletions'][str(n)][arm]['full_model_at_deleted_position']['record']
        b,bglobal=timing_terms(base);a,aglobal=timing_terms(other)
        baseline_prior=saved['receipts'][scan]['baseline'][arm]['best']['prior']
        assert abs(sum(b)+bglobal-baseline_prior)<1e-7
        ix=baseline['retained_satellites'].index(n)
        prior=float(row['timing_prior_change'])
        assert abs(sum(a-b)+aglobal-bglobal-prior)<1e-7
        rows.append(dict(scan=scan,arm=arm,satellite=n,
                         own_individual_timing_at_full_best_s=base['parameters'][6+ix]-base['vector'][6],
                         own_individual_timing_at_deleted_location_s=other['parameters'][6+ix]-other['vector'][6],
                         own_prior_at_full_best=float(b[ix]),full_prior_at_full_best=float(sum(b)+bglobal),
                         own_prior_change=float(a[ix]-b[ix]),other_satellites_prior_change=float(sum(a-b)-(a[ix]-b[ix])),
                         common_timing_prior_change=float(aglobal-bglobal),total_prior_change=prior))
    csv_file('timing-prior-decomposition.csv',rows)
    targets=[('N15',59381),('N12',53045),('N12',66899),('N12',63283)]
    fig,axes=plt.subplots(1,2,figsize=(14,5.8),sharey=True)
    for ax,arm in zip(axes,('fitted-c','zero-c')):
        for i,(scan,n) in enumerate(targets):
            r=next(r for r in tradeoffs if r['scan']==scan and r['arm']==arm and int(r['satellite'])==n)
            for k,(field,color,label) in enumerate([
                ('removed_windows_nll_change','#D55E00','Removed track’s windows'),
                ('other_windows_nll_change','#0072B2','All other windows'),
                ('timing_prior_change','#009E73','Timing prior')]):
                value=float(r[field]);y=i+(k-1)*.22
                ax.barh(y,value,height=.19,color=color,label=label if i==0 else None)
                ax.annotate(f'{value:+.2f}',(value,y),xytext=(4 if value>=0 else -4,0),textcoords='offset points',
                            ha='left' if value>=0 else 'right',va='center',fontsize=9)
        ax.set_yticks(range(len(targets)),[f'{s} / {n}' for s,n in targets]);ax.set_ylim(len(targets)-.5,-.5)
        ax.axvline(0,color='.4',lw=.8);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
        ax.set_xlabel('Score change on moving to the leave-one-out location (NLL)')
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0');ax.margins(x=.22)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.91),ncol=3,frameon=False)
    fig.suptitle('What makes the full model prefer its biased location?',fontsize=18)
    fig.text(.5,.025,'All observations and all satellites are retained for this comparison; full-model nuisance terms refitted at both locations.\nPositive = worse score at the leave-one-out location. Negative = better. Components add to the total score difference. All nuisance profiles converged.',ha='center',fontsize=10)
    assert all(r['full_model_profile_converged']=='True' for r in tradeoffs)
    fig.subplots_adjust(top=.79,bottom=.19,left=.09,right=.98,wspace=.18)
    fig.savefig(OUT/'same-model-score-tradeoffs.png',dpi=170);plt.close(fig)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
