"""Render strictly from saved prototype outputs."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prototype import ROOT, INPUT
from algo06_science.common import read, write


def main():
    results=[]
    for case in ('DS26-0309','DS26-0070'):
        for path in sorted((ROOT/case).glob('scale*-*.json')):
            row=read(path)
            results.append(dict(case=case,path=str(path),**row))
    columns=['case','selected_family','arm','SD_scale','covariance_scale','objective','rms_hz',
        'evaluation_error_m','fully_qualified','phase_closed','optimizer_success','all_gates_pass',
        'mixture_phase_interior','native_ids_preserved','active_points','seconds','failed_gate_count',
        'lost_count','added_count','reassigned_count','phase_rounds','minimum_exact_failed_slack',
        'quadratic','logvolume','gamma_cost','normalization_constant','objective_gain_vs_scale1']
    table=[]
    for row in results:
        baseline=next(r for r in results if r['case']==row['case'] and r['arm']==row['arm'] and r['SD_scale']==1)
        item={k:row.get(k) for k in columns}
        item.update(row['decomposition'])
        item.update(failed_gate_count=len(row['failed_gates']),lost_count=len(row['lost_ids']),
            added_count=len(row['added_ids']),reassigned_count=len(row['reassigned_ids']),phase_rounds=len(row['history']),
            minimum_exact_failed_slack=min((min(x['failed'].values()) for x in row['exact'] if x['failed']),default=None),
            objective_gain_vs_scale1=baseline['objective']-row['objective'])
        table.append(item)
    with (ROOT/'candidate_fits.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(table)
    write(ROOT/'summary.json',dict(rows=table,selection='Grid sensitivity only; no scale selected by GPS',
        conclusion='No cell establishes identity uniqueness or independent prediction; see parent predictive experiment.'))
    fig,axes=plt.subplots(2,3,figsize=(12,7),constrained_layout=True)
    for i,case in enumerate(('DS26-0309','DS26-0070')):
        for arm,marker in [('c0','o'),('fitted_c','s')]:
            rr=sorted((r for r in table if r['case']==case and r['arm']==arm),key=lambda r:r['SD_scale'])
            xx=[r['SD_scale'] for r in rr]
            axes[i,0].plot(xx,[r['objective_gain_vs_scale1'] for r in rr],marker=marker,label=arm)
            axes[i,1].plot(xx,[r['evaluation_error_m']/1000 for r in rr],marker=marker,label=arm)
            axes[i,2].plot(xx,[r['rms_hz'] for r in rr],marker=marker,label=arm)
            for r in rr:
                axes[i,1].annotate('pass' if r['fully_qualified'] else 'fail',(r['SD_scale'],r['evaluation_error_m']/1000),
                    xytext=(2,5 if arm=='c0' else -12),textcoords='offset points',fontsize=8)
        for j in range(3):
            axes[i,j].set_xlabel('Physical orbital prior SD multiplier');axes[i,j].set_xticks([1,2,4]);axes[i,j].grid(alpha=.3)
        axes[i,0].set_ylabel(case+'\n-2 ELBO gain vs 1×');axes[i,1].set_ylabel('Post-fit evaluation error (km)')
        axes[i,2].set_ylabel('Conditional per-point RMS (Hz)');axes[i,0].legend()
    fig.suptitle('Fixed observations, identities, receiver priors, common starts and budgets; pass = original full qualification')
    fig.savefig(ROOT/'comparison.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for i,case in enumerate(('DS26-0309','DS26-0070')):
        family=read(ROOT/case/'plan.json')['selected_family']
        for j,arm in enumerate(('c0','fitted_c')):
            ax=axes[i,j]
            for scale,color in [(1,'C0'),(2,'C1'),(4,'C3')]:
                matches=[r for r in results if r['case']==case and r['arm']==arm and r['SD_scale']==scale]
                if not matches:continue
                tracks=[t for t in matches[0]['tracks'] if t['norad']==family]
                for k,t in enumerate(tracks):
                    ax.scatter(t['times_s'],t['residual_hz'],s=5,alpha=.5,color=color,label=f'{scale}× SD' if k==0 else None)
            ax.axhline(0,color='black',lw=.8);ax.set_title(f'{case}, {family}, {arm}')
            ax.set_xlabel('Scan time (s)');ax.set_ylabel('Conditional native residual (Hz)');ax.legend();ax.grid(alpha=.25)
    fig.suptitle('All selected-family native points retained; conditional residual alone does not establish identity')
    fig.savefig(ROOT/'family-residuals.png',dpi=170);plt.close(fig)
    source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}
    write(ROOT/'run_manifest.json',dict(revision='d8d7033f9f654279463fa054cd2020be0bfd273e',
        source_sha256=source,protocol=read(ROOT/'protocol.json'),
        input_root=str(INPUT),numeric_python='/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python',
        environment=dict(PYTHONPATH='src:tools:reports/2026_11_02_family_reliability/family',OPENBLAS_NUM_THREADS=1,OMP_NUM_THREADS=1,MKL_NUM_THREADS=1),
        cases={c:read(ROOT/c/'plan.json') for c in ('DS26-0309','DS26-0070')},
        fits_complete=len(results),expected_fits=12))


if __name__=='__main__':main()
