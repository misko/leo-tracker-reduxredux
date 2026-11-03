"""Keep all nulls and failures in the nonlinear-channel calibration comparison."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_channel_calibration import OUT,ARMS
from run_algo01_ds23_sample import read,write
from report_algo02_ds23 import position_error


def main():
    protocol=read(OUT/'protocol.json');execution=read(OUT/'execution.json')
    assert execution['all_terminal']
    failures=[r for r in execution['results'] if 'error' in r]
    rows=[];max_null=0.;max_feedback=0.;selected={}
    for case in protocol['cases']:
        d=read(OUT/(case+'.json'));selected[case]=d['chosen_sigma_hz']
        max_null=max(max_null,*map(abs,d['original_RF_objective_replay_difference']))
        for factor in ('original','signed'):
            for arm in ARMS:
                baseline=d['baselines'][factor][arm];policy=d['policies'][factor][arm]
                rows.append(dict(case=case,cohort=case in protocol['cohort'],factor=factor,arm=arm,
                    method='RF_policy',sigma_hz=d['chosen_sigma_hz'][factor],paired_valid=True,
                    baseline_error_km=position_error(baseline['endpoint_latlon']),error_km=position_error(policy['endpoint_latlon']),
                    RF_gain=baseline['negative_twice_elbo']-policy['negative_twice_elbo']))
                for sigma in (100,300):
                    v=d['results'][factor+'_'+str(sigma)];r=v['arms'][arm]
                    max_feedback=max(max_feedback,r['linear_calibration_max_difference'])
                    rows.append(dict(case=case,cohort=case in protocol['cohort'],factor=factor,arm=arm,
                        method='fixed',sigma_hz=sigma,paired_valid=v['paired_valid'],
                        baseline_error_km=position_error(baseline['endpoint_latlon']),error_km=position_error(r['endpoint_latlon']),
                        RF_gain=baseline['negative_twice_elbo']-r['negative_twice_elbo']))
    with (OUT/'comparison.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    result={}
    for factor in ('original','signed'):
        result[factor]={}
        for arm in ARMS:
            r=[x for x in rows if x['cohort'] and x['method']=='RF_policy' and x['factor']==factor and x['arm']==arm]
            result[factor][arm]=dict(n=len(r),baseline_mean_km=float(np.mean([v['baseline_error_km'] for v in r])),
                policy_mean_km=float(np.mean([v['error_km'] for v in r])),
                baseline_median_km=float(np.median([v['baseline_error_km'] for v in r])),
                policy_median_km=float(np.median([v['error_km'] for v in r])),selected=sum(v['sigma_hz']>0 for v in r))
    write(OUT/'evaluation.json',dict(summary=result,failures=failures,selected=selected,
        maximum_null_RF_difference=max_null,maximum_predictive_calibration_update=max_feedback,
        publication_not_qualified_only_one_scan_selects_nonzero_modes=True))
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,factor in zip(axes,('original','signed'),strict=True):
        for sigma,color in ((100,'#327c9b'),(300,'#b67034')):
            chosen=[r for r in rows if r['method']=='fixed' and r['arm']=='c0' and r['factor']==factor and r['sigma_hz']==sigma]
            ax.scatter([r['RF_gain'] for r in chosen],[r['error_km']-r['baseline_error_km'] for r in chosen],
                c=color,marker='o',s=25,label=f'{sigma} Hz mode prior',alpha=.7)
            invalid=[r for r in chosen if not r['paired_valid']]
            ax.scatter([r['RF_gain'] for r in invalid],[r['error_km']-r['baseline_error_km'] for r in invalid],
                       marker='x',c='black',s=15)
        ax.axvline(2*np.log(2),color='gray',ls='--',lw=.8);ax.axhline(0,color='gray',lw=.8)
        ax.set(xlabel='RF bound gain (positive favors added modes)',ylabel='Change in position error (km)',title=factor+' phase mean')
        ax.grid(alpha=.15);ax.legend(fontsize=9)
    fig.suptitle('44 matched DS23 recordings · nonlinear channel calibration\n'
                 'Black crosses fail paired gates; only one recording selects a nonzero model',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'RF_gain_vs_position_change.png',dpi=180,bbox_inches='tight');plt.close(fig)
    print(result,flush=True);print('max RF null/linear feedback',max_null,max_feedback,flush=True)


if __name__=='__main__':main()
