"""Optimistic full-DS23 limit for the frozen multi-owner reentry rules.

Eligibility reads no positions. Only the final report-side bound replaces
eligible scans' errors by zero; this is not an estimator or achieved accuracy.
"""

from collections import defaultdict
from pathlib import Path
import statistics
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_algo01_ds23_sample import ROOT,read,write,sha
from run_ds23_combined_recovery_full import OUT as SOURCE

OUT=ROOT/'reports/2026_10_21_ds23_catalogue_reentry'


def main():
    protocol=read(SOURCE/'protocol.json');rows=[]
    for case in protocol['available_cases']:
        root=Path(protocol['input_roots'][case]);old=read(root/case/'algo02_result.json')
        node=read(root/case/'result.json')['final_node'];tracks={t['key']:t for t in read(root/case/'tracks.json')}
        active=[r for r in node['seed']['rows'] if r['active_curvature']];mask=np.array(old['mask'],bool)
        cursor=0;groups=defaultdict(list)
        for r in active:
            t=tracks[r['component']];n=len(t['times']);use=mask[cursor:cursor+n];cursor+=n
            if use.any() or n<12 or np.ptp(t['times'])<10:continue
            groups[r['candidate_index']].append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=n))
        if cursor!=len(mask):raise ValueError('original active-row mask layout differs')
        candidates=[dict(candidate_index=int(j),points=sum(r['points'] for r in g),curves=g)
            for j,g in groups.items() if len({(r['receiver'],r['channel']) for r in g})>=2]
        rows.append(dict(case=case,eligible_upper_bound=bool(candidates),groups=candidates))
    # Existing report errors enter only after every error-independent eligibility
    # decision is complete. Ignoring occupied predictive IDs makes this a
    # deliberately optimistic superset of the actual rule's eligible scans.
    evaluation=read(SOURCE/'evaluation.json');eligible={r['case'] for r in rows if r['eligible_upper_bound']}
    bounds={}
    for arm in ['c0','fitted_c']:
        baseline=[r for r in evaluation['all_rows'] if r['method']=='signed_prior' and r['arm']==arm and r.get('position_error_km_report_only') is not None]
        actual=[r['position_error_km_report_only'] for r in baseline]
        best=[0. if r['case'] in eligible else r['position_error_km_report_only'] for r in baseline]
        bounds[arm]=dict(available=len(actual),eligible_upper_bound=len(eligible),
            baseline_mean_km=statistics.mean(actual),baseline_median_km=statistics.median(actual),
            optimistic_best_mean_km=statistics.mean(best),optimistic_best_median_km=statistics.median(best),
            optimistic_below_half_km=sum(v<=.5 for v in best))
    write(OUT/'full_DS23_eligibility_ceiling.json',dict(rows=rows,bounds=bounds,
        original_causal_available_cases=len(rows),eligible_ignores_already_associated_predictive_owners=True,
        scan_eligibility_does_not_read_error=True,zero_error_replacement_is_only_a_report_side_bound=True,
        not_achieved_accuracy=True,source_sha256=sha(Path(__file__))))
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained',sharey=True)
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        b=bounds[arm];xx=np.arange(2)
        ax.bar(xx-.18,[b['baseline_mean_km'],b['baseline_median_km']],.36,color='tab:blue',label='Current signed incumbent')
        ax.bar(xx+.18,[b['optimistic_best_mean_km'],b['optimistic_best_median_km']],.36,
            color='white',edgecolor='tab:orange',hatch='//',label='Optimistic zero error on eligible scans')
        ax.axhline(.5,color='seagreen',ls='--',label='Goal')
        ax.set_xticks(xx,['Mean','Median']);ax.set(title=arm,ylabel='Position error (km)',ylim=(0,1.7));ax.grid(axis='y',alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle('Capability limit of this specific two-new-owner reentry rule\n181 eligible /410 available scans; hatched bars are optimistic bounds, NOT achieved accuracy')
    fig.savefig(OUT/'eligibility_ceiling.png',dpi=170);plt.close(fig)
    print(bounds,flush=True)


if __name__=='__main__':main()
