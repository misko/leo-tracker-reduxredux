"""Report the original ALGO02 population after isolated timeout recovery.

This is not the later signed-prior algorithm and never replaces its benchmark.
Missing scans remain explicit; geographic truth is reporting only.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read, write, sha
from run_algo02_ds23 import DEFAULT_RUN
from verify_ds23_recovered_positions import OUT, RUNS


def main():
    replay=read(OUT/'independent_recovery_evaluation.json')
    if not replay['all_verified']:raise ValueError('recovery replay required')
    rows=[];missing=[]
    for member in read(DEFAULT_RUN/'sample.json')['selected']:
        case=member['dataset_label'];root=RUNS.get(case,DEFAULT_RUN)
        path=root/case/'algo02_result.json'
        if not path.exists() or read(path)['status']!='accepted':
            missing.append(case);continue
        result=read(path)
        rows.append(dict(case=case,recovered=case in RUNS,format=member['recording_format'],
            error_km={arm:position_error(r['endpoint_latlon']) for arm,r in result['policy_arms'].items()},
            result_sha256=sha(path)))
    metrics={}
    for arm in ('c0','fitted_c'):
        error=np.array([r['error_km'][arm] for r in rows])
        metrics[arm]=dict(available=len(error),mean_km=float(error.mean()),median_km=float(np.median(error)),
            p90_km=float(np.quantile(error,.9)),maximum_km=float(error.max()),below_half_km=int(sum(error<=.5)))
    write(OUT/'availability_summary.json',dict(original_ALGO02_metrics=metrics,rows=rows,
        population=len(rows)+len(missing),unavailable=missing,
        signed_prior_algorithm_not_evaluated_here=True,
        full_goal_not_achieved=True,GPS_used_only_for_reporting=True))
    selected=[r for r in replay['rows']]
    figure,axes=plt.subplots(1,2,figsize=(12,5),gridspec_kw={'width_ratios':[2,1]})
    for arm,shift,color in (('c0',-.17,'#5384b0'),('fitted_c',.17,'#bd6e8e')):
        bars=axes[0].bar(np.arange(len(selected))+shift,
            [r['arms'][arm]['position_error_km_report_only'] for r in selected],width=.32,color=color,label=arm)
        axes[0].bar_label(bars,fmt='%.2f',fontsize=8,padding=2)
    axes[0].set_xticks(np.arange(len(selected)),[r['case'].replace('DS23-','') for r in selected])
    axes[0].set(xlabel='Recovered scan',ylabel='Position error (km; evaluation only)',ylim=(0,4.3))
    axes[0].axhline(.5,color='black',lw=.8,ls='--',label='0.5 km target');axes[0].legend(fontsize=8)
    counts=axes[1].bar(['Original','With recovery'],[404,len(rows)],color=['#8297a2','#4b957e'])
    axes[1].bar_label(counts,padding=4)
    axes[1].set(ylabel='Available original-ALGO02 results',ylim=(0,435))
    axes[1].axhline(413,color='black',lw=.8,ls='--')
    for ax in axes:ax.grid(axis='y',alpha=.15)
    figure.suptitle('DS23 · six original-ALGO02 timeout recoveries independently replayed\n'
        'Availability improvement; no localization algorithm change · missing scans stay in the denominator')
    figure.tight_layout(rect=(0,0,1,.89));figure.savefig(OUT/'recovered_position_errors.png',dpi=175);plt.close(figure)
    print(metrics,'unavailable',missing,flush=True)


if __name__=='__main__':
    main()
