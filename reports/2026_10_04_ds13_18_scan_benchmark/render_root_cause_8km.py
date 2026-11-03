"""Render independent 8 km diagnostic searches with explicit convergence flags."""
import argparse
import copy
import csv
import json
from pathlib import Path
import numpy as np
from root_cause import LABELS,ARMS
from render_root_cause import table,write_csv


def reconcile_best(summary):
    """A final fixed-roof transfer can beat every position-search endpoint."""
    summary=copy.deepcopy(summary)
    for arm in ARMS:
        r=summary['arms'][arm];previous=r['best']
        best=min([previous,*r['records']],key=lambda item:item['objective'])
        joint=[item for item in r['records'] if item['success'] and not item['fixed_location']]
        stationary=any(abs(item['objective']-best['objective'])<1e-6 and np.linalg.norm(np.asarray(item['point_km'])-best['point_km'])<1e-3 for item in joint)
        r.update(best=best,radius_m=float(1000*np.linalg.norm(best['point_km'])),
            best_is_joint_stationary=bool(stationary),boundary=bool(np.linalg.norm(best['point_km'])>=7.999),
            best_minus_roof_nll=best['objective']-r['roof']['objective'],
            best_minus_original_2km_nll=r['best_minus_original_2km_nll']+best['objective']-previous['objective'],
            reconciled_lower_fixed_site=best['objective']<previous['objective']-1e-7,
            distinct_competing_minima=[dict(point_km=item['point_km'],objective=item['objective']) for item in joint if np.linalg.norm(np.asarray(item['point_km'])-best['point_km'])>.1 and abs(item['objective']-best['objective'])<1.])
    return summary


def audit(summary):
    expected_starts=summary['common_starts_km']
    for arm in ARMS:
        records=summary['arms'][arm]['records']
        names=[r['stage'] for r in records]
        if len(names)!=len(set(names)):raise ValueError('duplicate stages')
        if len(records)!=29+len(expected_starts)+(4 if 'polish_signature' in summary else 0):raise ValueError('missing stages')
        for record in records:
            if np.linalg.norm(record['point_km'])>8.00001:raise ValueError('outside disk')
        for i in range(24):
            first=next(r for r in records if r['stage']==f'probe-{i:02d}')
            second=next(r for r in summary['arms'][ARMS[1]]['records'] if r['stage']==f'probe-{i:02d}')
            if first['point_km']!=second['point_km']:raise ValueError('unmatched probe geometry')
        if arm=='zero-c' and any(r['coefficient']!=0. for r in records):raise ValueError('zero-c changed')


def run(source,output,polished=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    output.mkdir(parents=True,exist_ok=True)
    summaries={}
    for label in LABELS:
        path=source/label/'summary.json'
        if polished is not None and (polished/label/'summary.json').exists():path=polished/label/'summary.json'
        if path.exists():
            summary=json.loads(path.read_text());audit(summary);summaries[label]=reconcile_best(summary)
    rows=[]
    for label,summary in summaries.items():
        for arm in ARMS:
            r=summary['arms'][arm]
            rows.append(dict(scan=label,arm=arm,old_2km_error_m=r['original_2km_error_m'],
                radius8_error_m=r['radius_m'],east_m=1000*r['best']['point_km'][0],north_m=1000*r['best']['point_km'][1],
                joint_stationary=r['best_is_joint_stationary'],boundary8=r['boundary'],status=r['best']['status'],
                kkt_residual=r['best']['kkt_residual'],roof_converged=r['roof']['success'],
                delta_nll_vs_2km=r['best_minus_original_2km_nll'],delta_nll_vs_roof=r['best_minus_roof_nll'],
                competing_minima=len(r['distinct_competing_minima']),calibration_warning=r['calibration_warning'],
                lower_fixed_site_found=r['reconciled_lower_fixed_site'],
                classification='calibration warning' if r['calibration_warning'] else '8 km boundary' if r['boundary'] else 'interior stationary solution' if r['best_is_joint_stationary'] else 'unconverged best found'))
    if not rows:raise ValueError('no completed searches')
    write_csv(output/'minimum-comparison.csv',rows)
    (output/'best-evidence.json').write_text(json.dumps({label:{arm:{key:r[key] for key in ('best','roof','best_is_joint_stationary','reconciled_lower_fixed_site','best_minus_roof_nll')} for arm,r in s['arms'].items()} for label,s in summaries.items()},indent=2))
    fig,ax=plt.subplots(figsize=(15,6));colors={'fitted-c':'#0072b2','zero-c':'#d55e00'}
    for arm,offset in [('fitted-c',-.15),('zero-c',.15)]:
        for i,label in enumerate(LABELS):
            if label not in summaries:continue
            r=summaries[label]['arms'][arm];x=i+offset
            ax.plot([x,x],[r['original_2km_error_m'],r['radius_m']],color=colors[arm],alpha=.45)
            ax.scatter(x,r['original_2km_error_m'],marker='_',color='#555',s=100)
            ax.scatter(x,r['radius_m'],marker='^' if r['boundary'] else ('o' if r['best_is_joint_stationary'] else 'x'),color=colors[arm],s=65)
        ax.scatter([],[],color=colors[arm],label=arm)
    ax.axhline(2000,ls=':',color='#777',label='Old 2 km boundary');ax.axhline(8000,ls='--',color='#777',label='New 8 km boundary')
    ax.set(xticks=range(len(LABELS)),xticklabels=LABELS,ylabel='Best-found distance from known roof (m)',ylim=(-200,8400))
    ax.grid(alpha=.15);ax.legend(ncol=4,fontsize=9)
    ax.set_title('Independent 8 km position searches · same observations and priors\nGray tick = old result; circle = joint stationary; × = unconverged; triangle = new boundary')
    if 'N16' in summaries and summaries['N16']['arms']['zero-c']['reconciled_lower_fixed_site']:
        ax.annotate('Fixed roof point;\nnot a localization',xy=(LABELS.index('N16')+.15,0),
            xytext=(LABELS.index('N16')-1.7,900),fontsize=8,color='#555',
            arrowprops=dict(arrowstyle='->',color='#777'))
    fig.tight_layout();fig.savefig(output/'minimum-comparison.png',dpi=150);plt.close(fig)
    for arm in ARMS:
        fig,axes=plt.subplots(6,3,figsize=(15,24),sharex=True,sharey=True)
        for ax,label in zip(axes.flat,LABELS):
            if label not in summaries:ax.set_title(label+' · pending');continue
            r=summaries[label]['arms'][arm];records=r['records']
            points=np.array([x['point_km'] for x in records]);delta=np.array([x['objective']-r['roof']['objective'] for x in records])
            limit=max(1.,float(np.max(abs(delta))))
            ax.scatter(points[:,0],points[:,1],c=delta,cmap='RdBu_r',norm=TwoSlopeNorm(0,-limit,limit),s=18,edgecolors='#888',linewidths=.3)
            for radius,style in [(2.,':'),(8.,'-')]:ax.add_patch(plt.Circle((0,0),radius,fill=False,ls=style,color='#777',lw=.7))
            ax.scatter(0,0,c='k',marker='+',s=70)
            best=r['best'];ax.scatter(*best['point_km'],marker='*' if r['best_is_joint_stationary'] else 'x',c='#222',s=90)
            ax.set_title(f"{label} · {r['radius_m']:.0f} m · {'boundary' if r['boundary'] else 'stationary' if r['best_is_joint_stationary'] else 'not converged'}\nΔNLL vs roof {r['best_minus_roof_nll']:+.2f}",fontsize=10)
            ax.set(xlim=(-8.7,8.7),ylim=(-8.7,8.7),aspect='equal');ax.grid(alpha=.15)
        for ax in axes[-1]:ax.set_xlabel('East of roof (km)')
        for ax in axes[:,0]:ax.set_ylabel('North of roof (km)')
        fig.suptitle(f'8 km search · {arm}\nBlue = lower score than roof; red = higher; color range is separate for each scan',fontsize=15)
        fig.tight_layout(rect=(0,0,1,.97));fig.savefig(output/f'score-maps-{arm}.png',dpi=125);plt.close(fig)
    columns=[('scan','Scan'),('arm','RF arm'),('old_2km_error_m','Old distance m'),('radius8_error_m','8 km search distance m'),('classification','Classification'),('kkt_residual','KKT'),('delta_nll_vs_2km','ΔNLL vs old'),('delta_nll_vs_roof','ΔNLL vs roof'),('competing_minima','Competing minima')]
    report='''<!doctype html><meta charset="utf-8"><title>8 km position audit</title><style>body{font:16px system-ui;max-width:1500px;margin:40px auto;padding:20px}img{width:100%}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:right}table{border-collapse:collapse;font-size:13px}p{max-width:1100px}</style>
    <h1>Does the minimum lie beyond the 2 km search boundary?</h1>
    <p>Each scan is independent. Same frozen alternatives-selected windows, satellite bank, nonlinear receiver correction, Gaussian timing priors, and RF reference as the 2 km study. Only the horizontal search disk was enlarged. Paired fitted-c/c=0 arms use identical probe and multistart coordinates and maximum budgets.</p>
    <p>24 fixed-position probes: eight on the 4 km ring, eight on the 8 km boundary, eight reproducible area samples between 2 and 8 km. Up to five common local-search starts, including the roof and prior 2 km solutions, plus two nuisance-transfer/restart sweeps. Short fixed-position fits need not converge. Color plots show evaluated scores, not interpolated converged profile surfaces.</p>
    <p>Selected nonconverged scans receive one bounded convergence retry (maximum 150 s per RF arm, same settings): 30 s roof, two 45 s position searches, 30 s cross-basin roof transfer. No data, priors or calibration model are changed.</p>
    <p>Best-found means the lowest saved score across every evaluated point, including the final fixed-roof transfer. A converged position-search endpoint is not accepted as best if a fixed-site fit has a lower score. Such cases remain unresolved; a fixed roof point is not a recovered location. <a href="best-evidence.json">Audited best-fit evidence</a></p>
    <p>A joint-stationary interior solution is a local minimum candidate, not a global certificate. An 8 km boundary result leaves the unrestricted minimum unresolved. A time-limit or failed-descent result is not a minimum. Scan B additionally has a saved calibration convergence warning. Original 2 km satellite-removal diagnostics remain separate; they have not been repeated at 8 km.</p>
    <p><a href="minimum-comparison.csv">All numerical results</a> · <a href="../report.html">Satellite influence audit</a></p><img src="minimum-comparison.png">'''
    report+=table(rows,columns)+'<h2>Fitted c</h2><img src="score-maps-fitted-c.png"><h2>c = 0</h2><img src="score-maps-zero-c.png">'
    (output/'report.html').write_text(report)
    print(f'Rendered {len(summaries)}/18 independent scans')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--polished',type=Path)
    a=p.parse_args();run(a.source,a.output,a.polished)
