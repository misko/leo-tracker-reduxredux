"""Additive satellite/RX contributions to the conditional roof-score gradient.

These are derivatives of the soft mixture likelihood, not hard-assignment SSE.
At a converged nuisance fit the envelope theorem identifies the local profile
gradient. This does not establish causal attribution or prove an identity wrong.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from cohort import digest
from position_direct import coordinate_jacobian
from position_search import prepare


def components(jacobian,prediction_gradient,probability,receiver,numbers,coordinate_derivative):
    result=[]
    for column,number in enumerate(numbers):
        for rx in (0,1):
            weights=np.zeros_like(prediction_gradient)
            mask=receiver==rx
            weights[mask,column]=-prediction_gradient[mask,column]
            physical=jacobian.transpose_multiply(weights.ravel())
            local=coordinate_derivative.T@physical[:2]
            result.append(dict(catalog_number=int(number),receiver=rx,
                               east_per_100m=float(local[0]/10),north_per_100m=float(local[1]/10),
                               strength_per_100m=float(np.linalg.norm(local)/10),
                               effective_window_support=float(np.sum(probability[mask,column]))))
    return result


def run(directory,output,roof_checkpoints=False,summary_path=None,permit_calibration_warning=False):
    data,meta=prepare(directory,'alternatives','support',1.,permit_calibration_warning=permit_calibration_warning)
    from rf_calibration_diagnostic import CalibrationObjective
    root=directory/'position-direct-v1/alternatives-support-100'
    if summary_path is not None and roof_checkpoints:
        raise ValueError('choose a summary or initial roof checkpoints, not both')
    summary_path=summary_path or root/'summary.json'
    summary=json.loads(summary_path.read_text()) if not roof_checkpoints else None
    rows=[]
    sources={}
    statuses={}
    for arm in ('fitted-c','zero-c'):
        source=summary_path if summary else root/f'{arm}-roof.json'
        saved=json.loads(source.read_text())
        if saved['signature']['inputs']!=meta:
            raise ValueError('gradient inputs differ from position fit')
        sources[str(source)]=digest(source.read_bytes())
        record=saved['arms'][arm]['roof'] if summary else saved['result']
        objective=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,8.)
        objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
        objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
        objective.base.deadline=float('inf')
        vector=np.asarray(record['vector'])
        value,gradient=objective.evaluate(vector)
        if abs(value-record['objective'])>1e-6:
            raise ValueError('gradient objective reconstruction mismatch')
        likelihood=objective.likelihood.last_result
        _,_,jacobian=objective.base.predict(vector[:objective.size],with_jacobian=True)
        cj=coordinate_jacobian([0.,0.])
        contributions=components(jacobian,likelihood['prediction_gradient'],likelihood['row_association_probability'],
                                 data.receiver,data.numbers,cj)
        total=np.sum([[r['east_per_100m'],r['north_per_100m']] for r in contributions],axis=0)
        expected=cj.T@gradient[:2]/10
        if not np.allclose(total,expected,atol=1e-7,rtol=1e-7):
            raise ValueError('satellite contributions do not sum to total gradient')
        statuses[arm]=dict(roof_converged=record['success'],gradient_per_100m=total.tolist(),
                           calibration_warnings=meta.get('calibration_warnings',[]),
                           additive_error=float(np.max(abs(total-expected))))
        rows.extend(dict(arm=arm,roof_converged=record['success'],**r) for r in contributions)
    output.mkdir(parents=True,exist_ok=True)
    with (output/'satellite-gradients.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    (output/'satellite-gradients.json').write_text(json.dumps(dict(scope=__doc__,sources=sources,statuses=statuses,rows=rows),indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(13,9))
    for ax,arm in zip(axes,('fitted-c','zero-c')):
        use=sorted([r for r in rows if r['arm']==arm],key=lambda r:r['strength_per_100m'],reverse=True)[:20]
        yy=np.arange(len(use))
        ax.barh(yy-.18,[r['east_per_100m'] for r in use],height=.35,color='#0072b2',label='East derivative')
        ax.barh(yy+.18,[r['north_per_100m'] for r in use],height=.35,color='#d55e00',label='North derivative')
        ax.set(yticks=yy,yticklabels=[f'{r["catalog_number"]} / RX{r["receiver"]}' for r in use],
               xlabel='Score derivative per 100 m',title=f'{arm} · roof converged: {statuses[arm]["roof_converged"]}')
        ax.invert_yaxis();ax.axvline(0,color='#555555',lw=.7);ax.grid(axis='x',alpha=.15);ax.legend(fontsize=8)
    warning=' · CALIBRATION WARNING' if meta.get('calibration_warnings') else ''
    fig.suptitle(f'{directory.parent.name} · strongest satellite/RX gradient contributions{warning}',fontsize=15)
    fig.text(.5,.018,'Top 20 shown; CSV contains every satellite/RX component. Components sum to the full soft-likelihood position derivative.\nPositive north derivative favors movement south. Conditional roof associations; not causal attribution or proof of wrong identity.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.94));fig.savefig(output/'satellite-gradients.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--roof-checkpoints',action='store_true',help='Audit saved initial roof fits before a full search finishes')
    p.add_argument('--summary',type=Path,help='Explicit completed direct/Fisher search summary')
    p.add_argument('--permit-calibration-warning',action='store_true',help='Explicitly display failed-calibration diagnostic evidence')
    a=p.parse_args();run(a.directory,a.output,a.roof_checkpoints,a.summary,a.permit_calibration_warning)
