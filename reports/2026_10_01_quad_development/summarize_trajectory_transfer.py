"""Complete-block transfer summaries with explicit failed-control coverage."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok
from check_receiver_curvature import save
HERE=Path(__file__).resolve().parent


def aggregate(folds):
    valid=[r for r in folds if r['policy_vs_robust'] is not None];selected=[r for r in valid if r['mixture_selected']]
    def mean(rows,key):return sum(r[key] for r in rows)/sum(r['held_points'] for r in rows) if rows else None
    return dict(folds=len(folds),held_points=sum(r['held_points'] for r in folds),valid_robust_folds=len(valid),valid_robust_points=sum(r['held_points'] for r in valid),
        failed_robust_folds=len(folds)-len(valid),mixture_selected=sum(r['mixture_selected'] for r in folds),
        gain_vs_gaussian=mean(folds,'selected_gain'),double_penalty_gain=mean(folds,'double_penalty_gain'),
        gain_vs_robust=mean(valid,'policy_vs_robust'),selected_gain_vs_robust=mean(selected,'policy_vs_robust'))


def main():
    inputs={};scans=[];raw=[]
    selection=sealed(HERE/'selection.json')
    units=[r['unit_id'] for r in selection['captures'] if r['block_id'] in ('DS9-B02','DS10-B02','DS11-B02')]
    for unit in units:
        root=HERE/'trajectory-transfer-v1'/unit
        def read(name):
            p=root/name;d=sealed(p);inputs[str(p)]=digest(p);return d
        result=read('result.json');launch=read('launch.json');assert process_ok(launch)
        sources=read('sources.json');verify_sources(sources['source_sha256']);verify_sources(sources['inputs'])
        raw.append(result)
        for sigma in (100.,300.):
            for split in ('alternating','forward'):
                folds=[f for t in result['tracks'] for f in t['folds'] if f['sigma_hz']==sigma and f['split']==split]
                scans.append(dict(unit=unit,tracks=len(result['tracks']),sigma_hz=sigma,split=split,**aggregate(folds)))
    rows=[]
    for dataset in ('DS9','DS10','DS11'):
        for sigma in (100.,300.):
            for split in ('alternating','forward'):
                folds=[f for d in raw if d['unit'].split('-')[0]==dataset for t in d['tracks'] for f in t['folds'] if f['sigma_hz']==sigma and f['split']==split]
                local=[r for r in scans if r['unit'].split('-')[0]==dataset and r['sigma_hz']==sigma and r['split']==split]
                row=dict(dataset=dataset,sigma_hz=sigma,split=split,tracks=sum(r['tracks'] for r in local),improving_scans=sum(r['gain_vs_robust'] is not None and r['gain_vs_robust']>0 for r in local),**aggregate(folds))
                row['gate']=row['failed_robust_folds']==0 and row['gain_vs_robust'] is not None and row['gain_vs_robust']>0 and row['improving_scans']>=3
                rows.append(row)
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,split in zip(axes,('alternating','forward')):
        local=[r for r in scans if r['sigma_hz']==100 and r['split']==split]
        ax.bar(np.arange(len(local)),[r['gain_vs_robust'] for r in local],color=['C'+str(('DS9','DS10','DS11').index(r['unit'].split('-')[0])) for r in local])
        ax.set_xticks(np.arange(len(local)),[r['unit'] for r in local],rotation=65,ha='right');ax.axhline(0,color='black',linewidth=.8)
        ax.set_title(split+' folds');ax.set_ylabel('Policy minus robust control (nats/held point)');ax.grid(axis='y',alpha=.2)
    fig.suptitle('B02 block transfer: forward extrapolation fails; failed-control folds excluded and counted')
    fig.tight_layout();fig.savefig(HERE/'trajectory-transfer-summary-v1.png',dpi=160);plt.close(fig)
    save(HERE/'trajectory-transfer-summary-v1.json',dict(rows=rows,scans=scans,primary_gate=all(r['gate'] for r in rows if r['sigma_hz']==100),
        inputs=inputs,sources={str(Path(__file__).resolve()):digest(__file__)},qualification='Development block radio-prediction transfer. Robust comparisons condition on converged controls; coverage explicitly reported.'))
    print(rows)


if __name__=='__main__':main()
