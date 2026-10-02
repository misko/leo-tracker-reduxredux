"""Predictive summaries and fitted-on-training branch figures."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from trajectory_mixture import design
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from check_receiver_curvature import save
HERE=Path(__file__).resolve().parent


def main():
    paths=[HERE/n for n in ('trajectory-mixture-v1.json','trajectory-robust-control-v1.json','radio-segmentation-v1.json')]
    data,control,raw=[sealed(p) for p in paths]
    for d in (data,control):verify_sources(d['sources']);verify_sources(d['inputs'])
    rows=[]
    for scan in data['scans']:
        for sigma in (100.,300.):
            folds=[f for r in scan['tracks'] for f in r['folds'] if f['sigma_hz']==sigma]
            gains=[sum(f['selected_gain'] for f in r['folds'] if f['sigma_hz']==sigma)/r['samples'] for r in scan['tracks']]
            controls=[r for r in control['rows'] if r['unit']==scan['unit'] and r['sigma_hz']==sigma];assert all(r['model']['converged'] for r in controls)
            selected=[r for r in controls if r['mixture_selected']]
            row=dict(unit=scan['unit'],sigma_hz=sigma,tracks=len(scan['tracks']),folds=len(folds),
                mixture_selected=sum(f['mixture_selected'] for f in folds),fallback_folds=sum(f['model']['status']!='mixture' for f in folds),
                nonconverged_starts=sum(not r['converged'] for f in folds for r in f['model']['starts']),
                pooled_gain=sum(f['selected_gain'] for f in folds)/sum(f['held_points'] for f in folds),median_track_gain=float(np.median(gains)),
                improving_tracks=sum(v>0 for v in gains),worsening_tracks=sum(v<0 for v in gains),
                raw_mixture_gain=sum(f['raw_mixture_gain'] for f in folds)/sum(f['held_points'] for f in folds),
                double_penalty_gain=sum(f['double_penalty_gain'] for f in folds)/sum(f['held_points'] for f in folds),
                policy_vs_robust=sum(r['policy_minus_robust'] for r in controls)/sum(r['held_points'] for r in controls),
                selected_vs_robust=sum(r['policy_minus_robust'] for r in selected)/sum(r['held_points'] for r in selected))
            rows.append(row)
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    scan=next(s for s in data['scans'] if s['unit']=='DS10-B01-S1');track=next(r for r in scan['tracks'] if r['track_index']==16)
    source=next(r for s in raw['scans'] if s['unit']=='DS10-B01-S1' for r in s['tracks'] if r['track_index']==16)
    t=np.array(source['times_s']);y=np.array(source['frequencies_hz']);base=np.polyfit(t,y,2);grid=np.linspace(t.min(),t.max(),300)
    for ax,parity in zip(axes,(0,1)):
        fold=next(f for f in track['folds'] if f['sigma_hz']==100 and f['training_parity']==parity);m=fold['model'];train=np.arange(len(t))%2==parity
        ax.scatter(t[train],y[train]-np.polyval(base,t[train]),label='Training',marker='o');ax.scatter(t[~train],y[~train]-np.polyval(base,t[~train]),label='Held',marker='x')
        means=design(grid,m['center'],m['scale'])@np.array(m['beta'])+m['offset']
        for k in range(means.shape[1]):ax.plot(grid,means[:,k]-np.polyval(base,grid),label=f'Component {k+1}')
        ax.set_title(f'RX1: train parity {parity}');ax.set_xlabel('Seconds from track start');ax.set_ylabel('Hz minus full-track quadratic');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Training-only two-curve fit: withheld observations scored by full mixture density')
    fig.tight_layout();fig.savefig(HERE/'trajectory-mixture-v1.png',dpi=160);plt.close(fig)
    save(HERE/'trajectory-mixture-summary-v1.json',dict(rows=rows,primary_gate=all(r['pooled_gain']>0 and r['median_track_gain']>0 for r in rows if r['sigma_hz']==100),
        inputs={str(p):digest(p) for p in paths},sources={str(Path(__file__).resolve()):digest(__file__)},qualification='Within-track correlated predictive evidence, not geographic validation.'))
    print(rows)


if __name__=='__main__':main()
