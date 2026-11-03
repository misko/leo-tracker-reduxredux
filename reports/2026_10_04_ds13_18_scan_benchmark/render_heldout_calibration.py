"""Summarize conditional five-fold nuisance transfer, not identity validation.

Whole-scan bootstrap shapes supplied the candidate bank and initialization.
The receiver spline is learned on training rows only, shared across RF arms.
Nearest-orbit residuals are gated at 600 Hz, so report coverage beside RMS.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from cohort import digest

HERE=Path(__file__).resolve().parent


def summarize(folds,arm):
    if len(folds)!=5 or {f['fold'] for f in folds}!=set(range(5)):
        raise ValueError('five distinct folds required')
    seen=set();inside=0;count=0;sse=0.
    for fold in folds:
        original=fold['test_original_rows'];record=fold['arms'][arm]
        if len(set(original))!=len(original) or seen.intersection(original):raise ValueError('test rows overlap')
        seen.update(original)
        n=record['heldout_windows'];k=record['heldout_inside600'];rms=record['heldout_nearest_rms_inside600_hz']
        if n!=len(original) or not 0<=k<=n:raise ValueError('held-out denominator mismatch')
        if k and (rms is None or not np.isfinite(rms) or not 0<=rms<=600):raise ValueError('invalid gated RMS')
        inside+=k;count+=n;sse+=k*rms*rms if k else 0.
    return dict(heldout_windows=count,inside600=inside,coverage600=inside/count if count else None,
                gated_nearest_rms_hz=float(np.sqrt(sse/inside)) if inside else None,
                postfit_converged_folds=sum(f['arms'][arm]['success'] for f in folds),
                fully_converged_matched_folds=sum(f['converged'] for f in folds))


def render(inputs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cohort_path=HERE/'cohort-v2.json';cohort=json.loads(cohort_path.read_text())
    rows=[];sources={str(cohort_path):digest(cohort_path.read_bytes())};verified={}
    for scan in cohort['scans']:
        if scan['split']=='locked_test' and not (HERE/'final-settings.json').exists():continue
        directory=inputs/scan['label']/'seed-timing-v6'
        paths=[directory/f'calibration-v2/fold-{i}.json' for i in range(5)]
        if not all(p.exists() for p in paths):continue
        folds=[json.loads(p.read_text()) for p in paths]
        for path,fold in zip(paths,folds):
            sig=fold['signature']
            checks={**sig['observations'],**sig['implementation'],str(directory/'bootstrap.json'):sig['bootstrap_sha256']}
            for source,expected in checks.items():
                if source not in verified:verified[source]=digest(Path(source).read_bytes())
                if verified[source]!=expected:raise ValueError('calibration source changed')
            sources[str(path)]=digest(path.read_bytes())
        for arm in ('fitted-c','zero-c'):rows.append(dict(scan=scan['label'],split=scan['split'],arm=arm,**summarize(folds,arm)))
    output=HERE/'heldout-calibration';output.mkdir(exist_ok=True)
    if not rows:return
    (output/'summary.json').write_text(json.dumps(dict(scope=__doc__,sources=sources,rows=rows),indent=2))
    with (output/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    labels=list(dict.fromkeys(r['scan'] for r in rows));x=np.arange(len(labels))
    fig,axes=plt.subplots(1,3,figsize=(16,5))
    for arm,offset,color in (('fitted-c',-.18,'#0072b2'),('zero-c',.18,'#d55e00')):
        use=[next(r for r in rows if (r['scan'],r['arm'])==(label,arm)) for label in labels]
        for ax,key,title,scale in zip(axes,('coverage600','gated_nearest_rms_hz','postfit_converged_folds'),
                  ('Held-out support within 600 Hz (%)','RMS among supported windows (Hz)','Converged post-fit folds (of 5)'),(100,1,1)):
            ax.bar(x+offset,[r[key]*scale if r[key] is not None else np.nan for r in use],.34,color=color,label=arm)
            ax.set(title=title,xticks=x,xticklabels=labels);ax.tick_params(axis='x',labelrotation=60)
            ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    axes[0].set_ylim(0,100);axes[2].set_ylim(0,5.5);axes[0].legend()
    fig.suptitle('Conditional held-out nuisance transfer · five blocked folds per scan',fontsize=16)
    fig.text(.5,.02,'Not an independent identity test: bootstrap candidates and initialization used whole-scan shapes.\nGated RMS conditions on each arm’s own supported set; use coverage and convergence alongside it. Scans remain independent.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.13,1,.92));fig.savefig(output/'comparison.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);a=p.parse_args();render(a.inputs)
