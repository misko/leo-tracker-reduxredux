"""Position/coverage tradeoffs for the frozen validation shortlist.

Development pilots and validation outcomes remain separately labelled. Missing
and failed runs are not scored as zero error. Raw NLL values across different
observation selections are deliberately not used to rank configurations.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from cohort import digest
from position_evidence import eligible,joint_stationary_at_best
from render_positions import validate

HERE=Path(__file__).resolve().parent


def render(inputs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    protocol_path=HERE/'validation-shortlist.json';protocol=json.loads(protocol_path.read_text())
    cohort_path=HERE/'cohort-v2.json';cohort=json.loads(cohort_path.read_text())
    if digest(cohort_path.read_bytes())!=protocol['cohort_sha256']:raise ValueError('cohort changed')
    sources={str(protocol_path):digest(protocol_path.read_bytes())};verified={};rows=[]
    for scan in cohort['scans']:
        if scan['split'] not in ('development','validation'):continue
        directory=inputs/scan['label']/'seed-timing-v6'
        for config in protocol['configurations']:
            selection=directory/config['selection']
            path=directory/'position-fisher-v2'/selection.stem/'alternatives-support-100/summary.json'
            if not path.exists():continue
            case=validate(json.loads(path.read_text()));meta=case['signature']['inputs']
            for source,expected in meta['sources'].items():
                if source not in verified:verified[source]=digest(Path(source).read_bytes())
                if verified[source]!=expected:raise ValueError('finalist position inputs changed')
            sources[str(path)]=digest(path.read_bytes())
            association=json.loads(selection.read_text())
            for arm,result in case['arms'].items():
                assigned=association['arms'][arm]['alternatives']['final']
                errors=np.asarray([r['residual_hz'] for r in assigned['assignments']])
                rows.append(dict(scan=scan['label'],split=scan['split'],configuration=config['name'],arm=arm,
                    error_m=result['radius_m'],eligible=eligible(result,meta),
                    joint_stationary=joint_stationary_at_best(result),boundary=result['boundary'],
                    roof_converged=result['roof']['success'],position_windows=meta['retained_windows'],
                    association_coverage=assigned['coverage'],satellites=assigned['satellites'],
                    association_support300=float(np.sum(abs(errors)<=300)/assigned['denominator'])))
    output=HERE/'finalist-comparison';output.mkdir(exist_ok=True)
    if not rows:return
    (output/'summary.json').write_text(json.dumps(dict(scope=__doc__,sources=sources,rows=rows),indent=2))
    with (output/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    labels=[s['label'] for s in cohort['scans'] if len({r['configuration'] for r in rows if r['scan']==s['label']})>1]
    if not labels:return
    columns=min(3,len(labels));height=int(np.ceil(len(labels)/columns))
    fig,axes=plt.subplots(height,columns,figsize=(5*columns,4*height),squeeze=False,sharey=True)
    for ax,label in zip(axes.ravel(),labels):
        for arm,color in (('fitted-c','#0072b2'),('zero-c','#d55e00')):
            values=[]
            for index,config in enumerate(protocol['configurations']):
                row=next((r for r in rows if (r['scan'],r['configuration'],r['arm'])==(label,config['name'],arm)),None)
                values.append(row['error_m'] if row else np.nan)
                if row:
                    ax.plot(index,row['error_m'],'^' if row['boundary'] else 'o',color=color)
                    if not row['eligible']:ax.plot(index,row['error_m'],'kx',ms=11)
            ax.plot(range(4),values,color=color,label=arm)
        split=next(r['split'] for r in rows if r['scan']==label)
        ax.set(title=f'{label} · {split}',xticks=range(4),xticklabels=['Baseline\n600 Hz','Tight\n300 Hz','Wide\n900 Hz','Curvature\n1.1'],
               ylabel='Best-found distance from roof (m)',ylim=(-50,2100))
        ax.grid(alpha=.15);ax.axhline(2000,color='#777777',ls=':');ax.legend(fontsize=8)
    for ax in axes.ravel()[len(labels):]:ax.axis('off')
    fig.suptitle('Frozen shortlist · independent position comparison',fontsize=15)
    fig.text(.5,.015,'Gaps = not yet completed. Cross = ineligible numerical/calibration result, not a successful zero-error estimate.\nTriangle = 2 km boundary. Both RF arms share observations within each configuration; configurations may retain different windows.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.12,1,.91));fig.savefig(output/'position-comparison.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);a=p.parse_args();render(a.inputs)
