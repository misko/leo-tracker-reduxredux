"""Frozen-baseline cohort results with explicit failures and matched RF summaries.

Association methods are compared on the original passing-window denominator.
Position results use the alternatives method, independent per scan. Paired
accuracy summaries use exactly the scans eligible in BOTH RF arms; descriptive
all-result distances retain failed fits and must not be called validated errors.
"""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean,median
import numpy as np

from cohort import digest
from position_evidence import eligible
from render_position_summary import case_path
from render_positions import validate
from render_pilot import validate_comparison

HERE=Path(__file__).resolve().parent
ARMS=('fitted-c','zero-c')
METHODS=('greedy','replacement','alternatives')


def method_gains(rows):
    """Matched-count differences, not evidence of correct satellite identities."""
    lookup={(r['scan'],r['arm'],r['method']):r for r in rows}
    if len(lookup)!=len(rows):raise ValueError('duplicate method evidence')
    result=[]
    for scan,arm in dict.fromkeys((r['scan'],r['arm']) for r in rows):
        if any((scan,arm,m) not in lookup for m in METHODS):raise ValueError('missing method evidence')
        group=[lookup[scan,arm,m] for m in METHODS]
        if len({r['denominator'] for r in group})!=1:raise ValueError('unmatched method denominator')
        for before,after in zip(group,group[1:]):
            result.append(dict(scan=scan,split=after['split'],arm=arm,
                comparison=f"{after['method']} minus {before['method']}",
                denominator=after['denominator'],
                assigned_change=after['assigned']-before['assigned'],
                satellites_change=after['satellites']-before['satellites'],
                objective_change=after['objective']-before['objective']))
    return result


def plot_method_gains(rows,output):
    import matplotlib.pyplot as plt
    labels=list(dict.fromkeys(r['scan'] for r in rows));x=np.arange(len(labels))
    fig,axes=plt.subplots(3,2,figsize=(15,10),sharex=True)
    for column,arm in enumerate(ARMS):
        for comparison,offset,color in (('replacement minus greedy',-.18,'#0072b2'),
                                        ('alternatives minus replacement',.18,'#d55e00')):
            use=[next(r for r in rows if (r['scan'],r['arm'],r['comparison'])==(n,arm,comparison)) for n in labels]
            for ax,key,ylabel in zip(axes[:,column],('assigned_change','satellites_change','objective_change'),
                                    ('Change in assigned windows','Change in satellites','Change in penalized score')):
                ax.bar(x+offset,[r[key] for r in use],width=.36,color=color,label=comparison)
                ax.axhline(0,color='#555555',lw=.7);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
                ax.set(ylabel=ylabel,xticks=x,xticklabels=labels)
                ax.tick_params(axis='x',labelbottom=True,labelrotation=60)
        axes[0,column].set_title(arm);axes[0,column].legend(fontsize=8)
    fig.suptitle('What replacement and alternative candidates change · all 18 scans',fontsize=16)
    fig.text(.5,.018,'Score = assigned windows − 10 × satellites (higher is better). All methods use the same passing-window denominator.\nA positive score change can include fewer assigned windows if enough satellites are removed. These are association-fit gains, not verified identities or localization gains.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.09,1,.94));fig.savefig(output/'method-gains.png',dpi=150);plt.close(fig)


def aggregate(rows):
    result=[]
    for split in ('reference','development','validation','locked_test'):
        use=[r for r in rows if r['split']==split and r['method']=='alternatives']
        labels=sorted({r['scan'] for r in use})
        lookup={(r['scan'],r['arm']):r for r in use}
        if len(lookup)!=len(use):raise ValueError('duplicate scan/arm evidence')
        if any((n,a) not in lookup for n in labels for a in ARMS):raise ValueError('unmatched RF evidence')
        common=[n for n in labels if all(lookup[n,a].get('position_eligible') is True for a in ARMS)]
        for arm in ARMS:
            arm_rows=[lookup[n,arm] for n in labels]
            if not arm_rows:continue
            completed=[r for r in arm_rows if r.get('position_error_m') is not None]
            distances=[lookup[n,arm]['position_error_m'] for n in common]
            result.append(dict(split=split,arm=arm,association_scans=len(arm_rows),
                equal_scan_mean_coverage=mean(r['coverage'] for r in arm_rows),
                scans_at_least_90_percent=sum(r['coverage']>=.9 for r in arm_rows),
                equal_scan_mean_satellites=mean(r['satellites'] for r in arm_rows),
                position_scans=len(completed),position_ineligible=sum(not r['position_eligible'] for r in completed),
                position_boundaries=sum(r['boundary'] for r in completed),
                common_eligible_scans=common,
                paired_eligible_median_error_m=median(distances) if distances else None,
                paired_eligible_p90_error_m=float(np.percentile(distances,90)) if distances else None,
                descriptive_all_result_median_distance_m=median(r['position_error_m'] for r in completed) if completed else None))
    return result


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def render(inputs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cohort_path=HERE/'cohort-v2.json';cohort=json.loads(cohort_path.read_text())
    sources={str(cohort_path):digest(cohort_path.read_bytes())};verified={};rows=[]
    for scan in cohort['scans']:
        if scan['split']=='locked_test':
            if not (HERE/'final-settings.json').exists():continue
            from freeze_final_settings import read_freeze
            read_freeze(HERE)
        directory=inputs/scan['label']/'seed-timing-v6'
        metrics_path=HERE/f'pilot-{scan["label"]}-seeded/pilot-metrics.json'
        if not metrics_path.exists():continue
        metrics=json.loads(metrics_path.read_text())
        if metrics['session_id']!=scan['session_id']:raise ValueError('scan binding mismatch')
        for source,expected in metrics['sources'].items():
            if source not in verified:verified[source]=digest(Path(source).read_bytes())
            if verified[source]!=expected:raise ValueError('stale association evidence')
        sources[str(metrics_path)]=digest(metrics_path.read_bytes())
        selection_path=directory/'selection-p10-g600-t1.json';selection=json.loads(selection_path.read_text())
        sources[str(selection_path)]=digest(selection_path.read_bytes())
        position_path=case_path(directory,'support',1.)
        position=validate(json.loads(position_path.read_text())) if position_path.exists() else None
        if position:
            for source,expected in position['signature']['inputs']['sources'].items():
                if source not in verified:verified[source]=digest(Path(source).read_bytes())
                if verified[source]!=expected:raise ValueError('stale position evidence')
            sources[str(position_path)]=digest(position_path.read_bytes())
        for arm in ARMS:
            for method in METHODS:
                search=selection['arms'][arm][method];final=search['final'];validate_comparison(final)
                residual=np.asarray([r['residual_hz'] for r in final['assignments']])
                p=position['arms'][arm] if position and method=='alternatives' else None
                rows.append(dict(scan=scan['label'],session_id=scan['session_id'],split=scan['split'],arm=arm,method=method,
                    **{k:final[k] for k in ('assigned','unassigned','denominator','coverage','satellites','objective')},
                    assigned_native_rms_hz=float(np.sqrt(np.mean(residual**2))) if len(residual) else None,
                    support300_fraction=float(np.sum(abs(residual)<=300)/final['denominator']),
                    association_search_elapsed_s=search['elapsed_s'],
                    calibration_warning=bool(selection.get('calibration_warnings')),
                    position_error_m=p['radius_m'] if p else None,
                    position_eligible=eligible(p,position['signature']['inputs']) if p else None,
                    best_fit_status=p['best_found']['status'] if p else None,
                    best_kkt_residual=p['best_found']['kkt_residual'] if p else None,
                    roof_fit_status=p['roof']['status'] if p else None,
                    roof_kkt_residual=p['roof']['kkt_residual'] if p else None,
                    converged_saved_fits=sum(r['success'] for r in p['records']) if p else None,
                    saved_fits=len(p['records']) if p else None,
                    boundary=p['boundary'] if p else None,ambiguous=p['ambiguous'] if p else None,
                    position_fit_wall_sum_s=sum(r['elapsed_s'] for r in p['records']) if p else None))
    output=HERE/'leaderboard';output.mkdir(exist_ok=True)
    if not rows:return
    summary=aggregate(rows);gains=method_gains(rows)
    (output/'summary.json').write_text(json.dumps(dict(scope=__doc__,sources=sources,rows=rows,aggregate=summary,method_gains=gains),indent=2))
    write_csv(output/'per-scan.csv',rows);write_csv(output/'by-split.csv',summary)
    write_csv(output/'method-gains.csv',gains);plot_method_gains(gains,output)
    labels=list(dict.fromkeys(r['scan'] for r in rows));x=np.arange(len(labels))
    fig,axes=plt.subplots(2,2,figsize=(15,9),sharex=True)
    for arm,offset,color in (('fitted-c',-.15,'#0072b2'),('zero-c',.15,'#d55e00')):
        use=[next(r for r in rows if (r['scan'],r['arm'],r['method'])==(n,arm,'alternatives')) for n in labels]
        for ax,key,title,scale in zip(axes.ravel(),('coverage','assigned_native_rms_hz','position_error_m','position_fit_wall_sum_s'),
                    ('Associated passing windows (%)','Assigned residual RMS (Hz, native RF)','Best-found position distance (m)','Sum of saved position-fit wall time (min)'),(100,1,1,1/60)):
            values=[r[key]*scale if r[key] is not None else np.nan for r in use]
            ax.plot(x+offset,values,'o-',color=color,label=arm,ms=5)
            if key=='position_error_m':
                for i,r in enumerate(use):
                    if r['position_error_m'] is not None and not r['position_eligible']:
                        ax.plot(i+offset,r['position_error_m'],'kx',ms=11,zorder=4)
                ax.axhline(2000,color='#777777',ls=':');ax.set_ylim(-50,2130)
            ax.set(title=title,xticks=x,xticklabels=labels);ax.tick_params(axis='x',labelbottom=True,labelrotation=60)
            ax.grid(alpha=.15);ax.legend(fontsize=8)
    axes[0,0].set_ylim(0,100)
    fig.suptitle('Frozen baseline · independent scans · greedy/replacement with alternatives',fontsize=16)
    fig.text(.5,.015,'Cross = ineligible position fit (nonstationary, boundary, or calibration warning). Gaps = pending. No global-minimum claim.\nAssigned-residual RMS uses each arm’s own selected windows; position arms share fixed observations. Timing excludes refinement/discovery and is not campaign elapsed time.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.1,1,.94));fig.savefig(output/'overview.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);a=p.parse_args();render(a.inputs)
