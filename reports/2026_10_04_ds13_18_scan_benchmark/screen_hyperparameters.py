"""Development-only association screening on frozen calibration/orbit pools.

This stage varies satellite penalty and residual gate, not nuisance priors.
Coverage at different gates is not directly equivalent evidence: report common
300/600 Hz support and RMS separately. Timing-prior and curvature-filter
experiments remain separate stages; this is not the final model leaderboard.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from cohort import digest
from select_associations import run as select

HERE=Path(__file__).resolve().parent
CONFIGS=((10.,600.),(5.,600.),(20.,600.),(10.,300.),(10.,900.))


def metrics(result):
    errors=np.asarray([r['residual_hz'] for r in result['assignments']])
    denominator=result['denominator']
    if len(errors)!=result['assigned'] or result['assigned']+result['unassigned']!=denominator:
        raise ValueError('window accounting mismatch')
    return dict(coverage=result['coverage'],windows=result['assigned'],denominator=denominator,
                satellites=result['satellites'],reference_score_p10=result['assigned']-10*result['satellites'],
                rms_hz=float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
                support_300_fraction=float(np.sum(abs(errors)<=300)/denominator),
                support_600_fraction=float(np.sum(abs(errors)<=600)/denominator))


def run(inputs,labels,variant='seed-timing-v6'):
    cohort_path=HERE/'cohort-v2.json'
    cohort=json.loads(cohort_path.read_text())
    splits={r['label']:r['split'] for r in cohort['scans']}
    if not labels or any(splits.get(label)!='development' for label in labels):
        raise ValueError('screening accepts development scans only')
    if len(set(labels))!=len(labels) or len(labels)>2:
        raise ValueError('bounded screening: one or two distinct development scans')
    rows=[]
    sources={str(cohort_path):digest(cohort_path.read_bytes()),str(Path(__file__)):digest(Path(__file__).read_bytes())}
    for label in labels:
        directory=inputs/label/variant
        for penalty,gate in CONFIGS:
            path=select(directory,penalty=penalty,gate=gate)
            record=json.loads(path.read_text())
            sources[str(path)]=digest(path.read_bytes())
            for arm,methods in record['arms'].items():
                for method,method_result in methods.items():
                    rows.append(dict(scan=label,arm=arm,method=method,penalty=penalty,gate_hz=gate,
                                     calibration_warnings=record.get('calibration_warnings',[]),
                                     **metrics(method_result['final'])))
    folder=HERE/'hyperparameter-screen'
    folder.mkdir(exist_ok=True)
    (folder/f'{"-".join(labels)}.json').write_text(json.dumps(dict(scope=__doc__,sources=sources,rows=rows),indent=2))
    render(folder)


def render(folder):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    records={}
    for path in sorted(folder.glob('*.json')):
        if path.name=='aggregate.json':
            continue
        document=json.loads(path.read_text())
        for source,expected in document['sources'].items():
            if digest(Path(source).read_bytes())!=expected:
                raise ValueError('stale hyperparameter input')
        for row in document['rows']:
            key=tuple(row[k] for k in ('scan','arm','method','penalty','gate_hz'))
            if key in records and records[key]!=row:
                raise ValueError('conflicting screen result')
            records[key]=row
    rows=list(records.values())
    scans=sorted({r['scan'] for r in rows})
    fig,axes=plt.subplots(2,3,figsize=(15,8))
    labels=[f'p={p:g}\n±{g:g} Hz' for p,g in CONFIGS]
    aggregates=[]
    for arm,axs in zip(('fitted-c','zero-c'),axes):
        for method,color in (('greedy','#0072b2'),('replacement','#e69f00'),('alternatives','#009e73')):
            values=[]
            for penalty,gate in CONFIGS:
                group=[r for r in rows if (r['arm'],r['method'],r['penalty'],r['gate_hz'])==(arm,method,penalty,gate)]
                if {r['scan'] for r in group}!=set(scans):
                    raise ValueError('incomplete matched screening grid')
                value=dict(arm=arm,method=method,penalty=penalty,gate_hz=gate,
                           **{k:float(np.mean([r[k] for r in group])) for k in ('coverage','support_300_fraction','rms_hz','satellites','reference_score_p10')})
                aggregates.append(value)
                values.append(value)
            for ax,key,scale in zip(axs,('coverage','support_300_fraction','satellites'),(100,100,1)):
                ax.plot(range(len(CONFIGS)),[v[key]*scale for v in values],'o-',color=color,label=method)
                ax.set_xticks(range(len(CONFIGS)),labels)
                ax.grid(alpha=.15)
        for ax,title in zip(axs,('Assigned windows (%)','Assigned windows within 300 Hz (%)','Selected satellites')):
            ax.set_title(f'{arm} · {title}')
        axs[0].legend(fontsize=8)
    fig.suptitle(f'Development association screening · {len(scans)} scans · equal weight per scan\nFrozen calibration and candidate pools; not a localization ranking',fontsize=15)
    fig.text(.5,.02,'Changing tolerance changes what “explained” means. Middle column uses a common 300 Hz diagnostic.\nSatellite timing-prior fitting and curvature exclusions are not varied in this screen. Locked-test scans excluded.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.10,1,.92))
    fig.savefig(folder/'association-screen.png',dpi=150)
    plt.close(fig)
    (folder/'aggregate.json').write_text(json.dumps(dict(scans=scans,rows=aggregates,scope=__doc__),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',type=Path)
    p.add_argument('--labels',nargs='+',required=True)
    a=p.parse_args()
    run(a.inputs,a.labels)
