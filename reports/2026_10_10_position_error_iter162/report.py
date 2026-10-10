"""Postseal geographic evaluation of predeclared within-arm preferences."""
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
ARMS=('zero-c','fitted-c')
GEOGRAPHIC_TOLERANCE=1e-9


def stats(values):
    import numpy as np
    values=list(values)
    if not values:return dict(n=0,mean=None,median=None,p95=None,worst=None)
    if not all(math.isfinite(v) for v in values):raise ValueError('nonfinite geographic metric')
    return dict(n=len(values),mean=float(np.mean(values)),median=float(np.median(values)),
                p95=float(np.percentile(values,95)),worst=float(max(values)))


def summarize(cells, preferences, members):
    datasets={m['label']:m['dataset'] for m in members}
    errors={}; failures=[]
    for c in cells:
        if c.get('error_km') is None:
            failures.append(dict(label=c['label'],hypothesis=c['hypothesis'],arm=c['arm'],
                mode=c['mode'],status=c['status'],error=c.get('error'),evaluation_error=c.get('evaluation_error')))
            continue
        key=(c['label'],c['hypothesis']);value=c['error_km']
        if key in errors and abs(errors[key]-value)>GEOGRAPHIC_TOLERANCE:
            raise ValueError('fixed geometry has inconsistent geographic errors')
        errors[key]=value
    rows=[]
    for p in preferences:
        row=dict(p,dataset=datasets[p['label']],hypothesis_errors={h:errors.get((p['label'],h)) for h in ARMS},
                 selected_error_km=None,delta_vs_fitted_hypothesis_km=None,preference_accuracy=None)
        a,b=(row['hypothesis_errors'][h] for h in ARMS)
        if a is not None and b is not None:
            row['geographic_equal']=abs(a-b)<=GEOGRAPHIC_TOLERANCE
            if p['status']=='selected':
                chosen=row['hypothesis_errors'][p['selected_hypothesis']]
                row['selected_error_km']=chosen;row['delta_vs_fitted_hypothesis_km']=chosen-b
                if not row['geographic_equal']:row['preference_accuracy']=chosen==min(a,b)
        rows.append(row)
    aggregates=[]
    for dataset in ('DS16','DS17','DS18','pilot'):
        for arm in ARMS:
            group=[r for r in rows if r['arm']==arm and (dataset=='pilot' or r['dataset']==dataset)]
            paired=[r for r in group if r['selected_error_km'] is not None]
            delta=[r['delta_vs_fitted_hypothesis_km'] for r in paired]
            classified=[r for r in group if r['preference_accuracy'] is not None]
            aggregates.append(dict(dataset=dataset,arm=arm,members=len(group),
                resolved=sum(r['status']=='selected' for r in group),ties=sum(r['status']=='tie' for r in group),
                incomplete=sum(r['status']=='incomplete' for r in group),evaluable=len(paired),
                full_coverage=len(paired)==len(group),selected=stats(r['selected_error_km'] for r in paired),
                baseline_paired=stats(r['hypothesis_errors']['fitted-c'] for r in paired),
                hypothesis_errors={h:stats(r['hypothesis_errors'][h] for r in group if r['hypothesis_errors'][h] is not None) for h in ARMS},
                delta=stats(delta),improved=sum(d < -GEOGRAPHIC_TOLERANCE for d in delta),
                equal=sum(abs(d)<=GEOGRAPHIC_TOLERANCE for d in delta),
                regressed=sum(d>GEOGRAPHIC_TOLERANCE for d in delta),
                regression_labels=[r['label'] for r in paired if r['delta_vs_fitted_hypothesis_km']>GEOGRAPHIC_TOLERANCE],
                maximum_regression_km=max((d for d in delta if d>GEOGRAPHIC_TOLERANCE),default=0.),
                preference_correct=sum(r['preference_accuracy'] is True for r in classified),
                preference_denominator=len(classified),geographic_ties=sum(r.get('geographic_equal',False) for r in group)))
    return dict(rows=rows,aggregates=aggregates,failures=failures)


def plot(summary,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(2,2,figsize=(14,8),constrained_layout=True)
    for i,arm in enumerate(ARMS):
        rows=[r for r in summary['rows'] if r['arm']==arm];x=np.arange(len(rows))
        for h,color,offset in [('zero-c','#ba7834',-.17),('fitted-c','#5975a5',.17)]:
            axes[i,0].scatter(x+offset,[r['hypothesis_errors'][h] if r['hypothesis_errors'][h] is not None else np.nan for r in rows],
                color=color,label=h+' source position',s=25)
        axes[i,0].scatter(x,[r['selected_error_km'] if r['selected_error_km'] is not None else np.nan for r in rows],
            marker='x',s=65,color='black',label='held-score selection')
        axes[i,1].bar(x,[r.get('delta_nll',np.nan) for r in rows],color='#258e89')
        axes[i,1].axhline(0,color='black',lw=.8)
        axes[i,0].set_ylabel(arm+' calibration: error (km)')
        axes[i,1].set_ylabel('Held NLL: fitted-source − zero-source')
        for ax in axes[i]:
            ax.set_xticks(x,[r['label'] for r in rows],rotation=65,ha='right');ax.grid(alpha=.2)
        axes[i,0].legend(fontsize=8)
    axes[0,0].set_title('Same ordinary hypotheses; geographic evaluation only')
    axes[0,1].set_title('Within-arm preference; negative prefers fitted-source position')
    fig.savefig(path,dpi=160);plt.close(fig)


def markdown(summary):
    def f(v):return 'missing' if v is None else f'{v:.4f}'
    lines=['# Conditional geometry preference results','',
        '![Geometry preference and position error](comparison.png)','',
        'This consumed-data pilot keeps two ordinary full-data positions per scan fixed, fits nuisance '
        'parameters on each training fold and scores the opposite fold. Both c arms compare both positions. '
        'Scores are summed within each arm; no c-arm winner is chosen. Each scan contributes one geographic '
        'error per hypothesis, not one independent position observation per fit.', '',
        '| Dataset | Calibration arm | Resolved / members | Ties / incomplete | Evaluated | Selected mean | Median | p95 | Worst km | Paired fitted-source mean | Mean change km | Correct preference / evaluable non-ties | Geographic ties |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for a in summary['aggregates']:
        lines.append(f"| {a['dataset']} | {a['arm']} | {a['resolved']} / {a['members']} | {a['ties']} / {a['incomplete']} | {a['evaluable']} | "
            +' | '.join(f(a['selected'][k]) for k in ('mean','median','p95','worst'))
            +f" | {f(a['baseline_paired']['mean'])} | {f(a['delta']['mean'])} | {a['preference_correct']} / {a['preference_denominator']} | {a['geographic_ties']} |")
    lines+=['','| Member | Calibration arm | Status / selected source | Zero-source km | Fitted-source km | Held NLL difference | Change vs fitted-source km |',
        '|---|---|---|---:|---:|---:|---:|']
    for r in summary['rows']:
        lines.append(f"| {r['label']} | {r['arm']} | {r['status']} / {r['selected_hypothesis']} | "
            +f"{f(r['hypothesis_errors']['zero-c'])} | {f(r['hypothesis_errors']['fitted-c'])} | {f(r.get('delta_nll'))} | {f(r['delta_vs_fitted_hypothesis_km'])} |")
    lines+=['','## Coverage and limits','',
        f"Qualified fits: {summary['qualified']}/96; geographic evaluations: {summary['evaluated']}/96. "
        f"Total member worker time including reconstruction: {summary['worker_s']:.3f} seconds. "
        'Qualification, held scoring and reference-evaluation failures remain separate in SUMMARY.json and raw receipts. '
        'Ties and incomplete selections have no fallback. The table reports paired baseline means on the same '
        'evaluable selection subset; full hypothesis metrics, regression labels and maximum regression are in SUMMARY.json.', '',
        'The geographic equality tolerance is 1e-9 km; equal geographic hypotheses are neutral, excluded from '
        'binary preference accuracy and retained in coverage. The reference-free summed-NLL tie tolerance is 1e-6. '
        'The two positions and shared model definitions were obtained using full-data inference, including the held folds. '
        'This is conditional development sensitivity, not unbiased cross-validation or independent validation. '
        'The hypotheses may occupy one local region; no conclusion about distant-region discrimination follows.', '',
        'The official 193-member score, deployed B7 and closed reserved recordings are unchanged. '
        'No RF collection, reference-guided fitting, per-scan tuning, retry or fallback success was used. '
        'The 0.4 km standalone goal remains unmet. [Plan](PLAN.md), [frozen numerical protocol](protocol.json), '
        '[sealed preferences](PREFERENCES.json), [evaluation plan](EVALUATION_PLAN.md), '
        '[evaluation protocol](evaluation_protocol.json), [all results](SUMMARY.json), '
        '[raw receipts](raw-receipts.tar.gz).','']
    return '\n'.join(lines)


def main():
    import hashlib,tarfile
    import run,evaluation,preference
    freezer=run.module('freeze162_report',HERE/'freeze.py')
    plan=json.loads((HERE/'protocol.json').read_text());run.BASE.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan);collection=evaluation.collect(plan,digest,HERE/'results')
    selected=preference.preferences(collection['cells'],[m['label'] for m in plan['members']])
    if selected!=json.loads((HERE/'PREFERENCES.json').read_text()):raise ValueError('sealed preferences differ')
    evaluated=evaluation.evaluate(plan,digest,HERE/'results',json.loads((HERE/'evaluation_protocol.json').read_text()))
    summary=summarize(evaluated['rows'],selected,plan['members'])
    summary.update(protocol_sha256=digest,cells=evaluated['rows'],members=collection['members'],raw_sha256=collection['raw_sha256'],
        qualified=sum(c['status']=='qualified' for c in evaluated['rows']),evaluated=sum(c['error_km'] is not None for c in evaluated['rows']),
        worker_s=sum(m['elapsed_s'] for m in collection['members'].values()))
    (HERE/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    plot(summary,HERE/'comparison.png');(HERE/'README.md').write_text(markdown(summary))
    with tarfile.open(HERE/'raw-receipts.tar.gz','w:gz') as archive:
        for name in sorted(collection['raw_sha256']):archive.add(HERE/'results'/name,arcname=name)
    with tarfile.open(HERE/'raw-receipts.tar.gz','r:gz') as archive:
        actual={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers()}
    if actual!=collection['raw_sha256']:raise ValueError('archive differs')
    names=('README.md','SUMMARY.json','comparison.png','raw-receipts.tar.gz','protocol.json',
           'evaluation_protocol.json','PREFERENCES.json','report.py','evaluation.py')
    (HERE/'REPORT_INTEGRITY.json').write_text(json.dumps({n:evaluation.sha(HERE/n) for n in names},indent=2)+'\n')
    print(json.dumps(dict(qualified=summary['qualified'],evaluated=summary['evaluated'],aggregates=summary['aggregates'])))


if __name__=='__main__':main()
