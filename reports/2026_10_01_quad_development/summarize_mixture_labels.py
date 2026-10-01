"""Summarize all nine bounded coupled-label checks."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from check_mixture_labels import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE=Path(__file__).resolve().parent


def main():
    rows=[];inputs={}
    for unit in UNITS:
        directory=HERE/'mixture-label-check-v1'/unit
        launch=sealed(directory/'launch.json');assert process_ok(launch)
        frozen=sealed(directory/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
        r=sealed(directory/'result.json');assert r['proposed']==r['evaluated']+len(r['invalid'])
        for name in ('sources.json','result.json','launch.json'):inputs[str(directory/name)]=digest(directory/name)
        rows.append(r)
    fig,axes=plt.subplots(1,2,figsize=(11,4.6),constrained_layout=True)
    labels=[r['unit'].replace('-B01-','\n') for r in rows];x=np.arange(9)
    axes[0].bar(x,[r['maximum_gain'] for r in rows]);axes[0].axhline(0,color='gray',linewidth=.8)
    axes[0].set_ylabel('Largest proposed move log-score gain')
    axes[1].bar(x,[r['improving_tracks'] for r in rows]);axes[1].set_ylabel('Tracks with a gain > 1e-6')
    for ax in axes:ax.set_xticks(x,labels,fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Coupled mixture assignment check at fixed fitted states\nTwo alternative signals plus background; no position refits')
    figure=HERE/'mixture-label-summary-v1.png';fig.savefig(figure,dpi=160);plt.close(fig)
    save(HERE/'mixture-label-summary-v1.json',dict(rows=rows,evaluated_moves=sum(r['evaluated'] for r in rows),
        improving_moves=sum(r['improving_moves'] for r in rows),inputs=inputs,
        sources={str(Path(__file__).resolve()):digest(__file__)},figure_sha256=digest(figure)))
    for r in rows:print(r['unit'],r['track_count'],r['evaluated'],r['improving_moves'],r['improving_tracks'],r['maximum_gain'])
    print('reconstruction',max(e for r in rows for e in r['full_reconstruction_errors']))


if __name__=='__main__':main()
