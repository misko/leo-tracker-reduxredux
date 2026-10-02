"""Plot finite-support corrections against the predeclared expansion gate."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok
HERE=Path(__file__).resolve().parent


def main():
    inputs={};rows=[];fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    for unit in UNITS:
        root=HERE/'support-effect-v1'/unit
        def read(name):
            p=root/name;d=sealed(p);inputs[str(p)]=digest(p);return d
        result=read('result.json');launch=read('launch.json');assert process_ok(launch)
        sources=read('sources.json');verify_sources(sources['source_sha256']);verify_sources(sources['inputs'])
        tracks=result['tracks']
        for ax,values in zip(axes,([abs(v) for r in tracks for v in r['correction_hz']],[r['whitened_correction_norm'] for r in tracks])):
            values=np.sort(values);ax.plot(values,np.arange(1,len(values)+1)/len(values),label=unit.split('-')[0]);ax.set_xscale('log');ax.grid(alpha=.2)
        rows.append(dict(unit=unit,signal_tracks=len(tracks),samples=sum(r['samples'] for r in tracks),
            maximum_correction_hz=result['maximum_correction_hz'],maximum_whitened_norm=result['maximum_whitened_norm'],
            maximum_step_difference_hz=max(r['step_difference_hz'] for r in tracks),
            maximum_prediction_parity_hz=max(r['point_prediction_parity_hz'] for r in tracks),
            all_steps_stable=result['all_steps_stable'],expansion_gate=result['expansion_gate'],seconds=launch['elapsed_seconds']))
    axes[0].set_xlabel('Absolute sample correction (Hz)');axes[0].set_ylabel('Fraction of samples');axes[0].legend()
    axes[1].set_xlabel('Whitened track correction norm');axes[1].set_ylabel('Fraction of tracks')
    axes[1].axvline(.01,color='black',linestyle='--',label='Expansion gate 0.01');axes[1].legend()
    fig.suptitle('Finite-support moment correction is far below the model noise scale')
    fig.tight_layout();fig.savefig(HERE/'support-effect-summary-v1.png',dpi=160);plt.close(fig)
    save(HERE/'support-effect-summary-v1.json',dict(rows=rows,inputs=inputs,sources={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Fixed-state cubic moment approximation; no refits, exact detector weighting, or geography.'))
    print(rows)


if __name__=='__main__':main()
