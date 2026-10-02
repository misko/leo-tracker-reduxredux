"""Summarize every predeclared quality/residual pilot, retaining failed gates."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from check_shared_scale import UNITS
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok
from check_receiver_curvature import save

HERE=Path(__file__).resolve().parent


def main():
    inputs={};rows=[]
    fig,axes=plt.subplots(1,3,figsize=(12,3.8),sharex=True,sharey=True)
    for ax,unit in zip(axes,UNITS):
        root=HERE/'quality-residual-v1'/unit
        def read(name):
            path=root/name;data=sealed(path);inputs[str(path)]=digest(path);return data
        result=read('result.json');launch=read('launch.json');assert process_ok(launch)
        sources=read('sources.json');verify_sources(sources['source_sha256']);verify_sources(sources['inputs'])
        tracks=result['signal_tracks']
        ax.scatter([r['median_margin'] for r in tracks],[r['energy_per_dimension'] for r in tracks],s=22,alpha=.7)
        ax.set_yscale('log');ax.axvline(.5,color='grey',linestyle='--',linewidth=1)
        ax.set_title(unit.split('-')[0]+f"  rank correlation {result['summary']['spearman']:+.3f}")
        ax.set_xlabel('Median margin of retained observations');ax.grid(alpha=.2)
        rows.append(dict(unit=unit,signal_tracks=len(tracks),background_tracks=len(result['background_tracks']),
                         retained_observations=result['retained_observations'],seconds=launch['elapsed_seconds'],**result['summary']))
    axes[0].set_ylabel('Residual contrast energy / dimension (log scale)')
    fig.suptitle('Higher detector margin does not predict smaller fitted residuals in these pilots')
    fig.tight_layout();fig.savefig(HERE/'quality-residual-summary-v1.png',dpi=160);plt.close(fig)
    save(HERE/'quality-residual-summary-v1.json',dict(rows=rows,all_dataset_gate=all(r['directional_gate'] for r in rows),
        inputs=inputs,sources={str(Path(__file__).resolve()):digest(__file__)},
        qualification='In-sample fixed-state descriptive diagnostic; no independent validation, weighting change, or geographic improvement.'))
    print(rows)


if __name__=='__main__':main()
