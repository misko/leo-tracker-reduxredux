"""Local evaluation only; GPS errors never return to the inference worker."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_gate_retention_cohort import OUT,SOURCE,ARMS
from run_algo01_ds23_sample import read,write
from report_algo02_ds23 import position_error


def aggregates(rows):
    result={}
    for group in ('development','additional','combined'):
        result[group]={}
        for arm in ARMS:
            selected=[r for r in rows if r['arm']==arm and (group=='combined' or r['cohort']==group)]
            result[group][arm]={}
            baseline=np.asarray([r['baseline_error_km'] for r in selected])
            for method in ('baseline','fine_only','growth_policy'):
                values=np.asarray([r[method+'_error_km'] for r in selected])
                result[group][arm][method]=dict(count=len(values),mean_km=float(values.mean()),median_km=float(np.median(values)),
                    maximum_km=float(values.max()),below_half_km=int(sum(values<=.5)),
                    improved=int(sum(values<baseline-1e-8)),regressed=int(sum(values>baseline+1e-8)))
    return result


def main():
    protocol=read(OUT/'protocol.json');execution=read(OUT/'execution.json');failures={r['case']:r for r in execution['receipts'] if 'error' in r}
    rows=[]
    for case in protocol['cases']:
        path=OUT/(case+'.json');document=read(path) if path.exists() else None
        old=read(SOURCE/case/'algo02_result.json')['policy_arms']
        for arm in ARMS:
            fine=document['fine_arms'] if document and document['fine_accepted'] else old
            growth=document['policy_arms'] if document else old
            rows.append(dict(case=case,cohort='development' if case in protocol['development'] else 'additional',arm=arm,
                execution_failed=case in failures,baseline_error_km=position_error(old[arm]['endpoint_latlon']),
                fine_only_error_km=position_error(fine[arm]['endpoint_latlon']),growth_policy_error_km=position_error(growth[arm]['endpoint_latlon']),
                fine_accepted=bool(document and document['fine_accepted']),growth_accepted=bool(document and document['growth_receipt']['paired_valid']),
                offered_curved_points=0 if document is None else int(sum(document['offered_mask'])-sum(document['original_mask'])),
                retained_curved_points=growth[arm]['active_points'],baseline_curved_points=old[arm]['active_points'],
                fine_same_mask_c0_gain=None if document is None else document['fine_same_mask_c0_gain']))
    with (OUT/'evaluation.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=aggregates(rows)
    positive=all(summary[group][arm]['growth_policy'][metric]<summary[group][arm]['baseline'][metric]
        for group in ('additional','combined') for arm in ARMS for metric in ('mean_km','median_km')) and not failures
    result=dict(summary=summary,failures=failures,rows=rows,positive_transfer_criterion_pass=positive,
        target_mean_and_median_half_km_on_full_DS23_not_proven=True,
        evaluation_coordinates_only_in_reporter=True,additional_recordings_previously_exposed=True,
        negative_results_remain_local_no_publication=True)
    write(OUT/'evaluation.json',result)
    fig,axes=plt.subplots(1,2,figsize=(13,6));colors=dict(development='#267caa',additional='#ce6c32')
    for ax,arm in zip(axes,ARMS,strict=True):
        chosen=[r for r in rows if r['arm']==arm]
        limit=max(max(r['baseline_error_km'],r['growth_policy_error_km']) for r in chosen)*1.07
        ax.plot([0,limit],[0,limit],color='gray',ls='--');ax.axhline(.5,color='green',lw=.8,alpha=.6)
        for group in colors:
            data=[r for r in chosen if r['cohort']==group]
            ax.scatter([r['baseline_error_km'] for r in data],[r['growth_policy_error_km'] for r in data],
                color=colors[group],marker='o' if group=='development' else 'D',s=32,label=group,alpha=.8)
        for r in chosen:
            if abs(r['growth_policy_error_km']-r['baseline_error_km'])>.2:
                ax.annotate(r['case'].replace('DS23-',''),(r['baseline_error_km'],r['growth_policy_error_km']),fontsize=8)
        ax.set_xlabel('Original ALGO02 position error (km)');ax.set_ylabel('Gate-retention policy error (km)');ax.set_title(arm);ax.grid(alpha=.15);ax.legend()
    fig.suptitle('DS23 · 40 matched recordings · fixed receiver covariance and RF-only curve re-entry\n'
        'All failures retain the original position; lower RF loss or more points does not imply lower position error',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.91));fig.savefig(OUT/'position_transfer.png',dpi=180,bbox_inches='tight');plt.close(fig)
    print('Positive transfer criterion:',positive,'failures',len(failures),flush=True)
    for group in summary:
        for arm in ARMS:
            a,b=summary[group][arm]['baseline'],summary[group][arm]['growth_policy']
            print(group,arm,'mean',a['mean_km'],'->',b['mean_km'],'median',a['median_km'],'->',b['median_km'],flush=True)


if __name__=='__main__':main()
