"""Use saved RF gain diagnostics only; no IQ reread, orbital or GPS input."""

from pathlib import Path
import numpy as np
from ds23_frame_phase_harmonics import phase_harmonics
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_frame_phase_harmonics'
SOURCE=ROOT/'reports/2026_10_19_ds23_rx2_measurement_cohort/frame_phase_coherence.json'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(source_sha256=sha(SOURCE),harmonics=[1,2,4,8],frequency_grid_hz=[-375,375,5],
        controls_per_probe=199,seed='20261020+row index',
        candidate_rule='fourth coherence >=.8, first coherence <.6, maximum-over-all-harmonics random-phase rank <=.01',
        unit_phase_weights=True,RF_carrier_phase_radians_not_orbit_phase_seconds=True,
        all_original_saved_phase_diagnostics_included=True,new_RF_collection=False,IQ_reread=False,
        source_code_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_frame_phase_harmonics.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('frame harmonic protocol changed')
    if not target.exists():write(target,protocol)
    source=read(SOURCE);rows=[]
    for k,row in enumerate(source['rows']):
        result=phase_harmonics(row['frame_time_s'],row['residual_phase_rad'],seed=20261020+k)
        rows.append(dict(case=row['case'],observation_id=row['observation_id'],receiver=row['receiver'],band=row['band'],
            frames=row['frames'],**result))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    first=[r['harmonics']['1']['coherence'] for r in rows]
    for h,color in [('2','#197c91'),('4','#c44c31'),('8','#5e3c99')]:
        axes[0].scatter(first,[r['harmonics'][h]['coherence'] for r in rows],alpha=.6,s=18,label=f'harmonic {h}',color=color)
    axes[0].plot([0,1],[0,1],'k--',lw=.7)
    axes[0].set(xlabel='First-harmonic coherence',ylabel='Higher-harmonic coherence',title='Finite-alphabet phase rotation screen');axes[0].legend()
    null=np.concatenate([r['random_phase_maximum_search_scores'] for r in rows])
    actual=[max(h['coherence'] for h in r['harmonics'].values()) for r in rows]
    axes[1].hist(null,bins=np.linspace(0,1,31),weights=np.full(len(null),1/199),histtype='step',label='Random-phase controls /199',color='black')
    axes[1].hist(actual,bins=np.linspace(0,1,31),alpha=.5,label='Saved frame gains',color='#197c91')
    axes[1].set(xlabel='Maximum coherence over all four harmonics',ylabel='Probes',title='Matched frequency/harmonic search');axes[1].legend()
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('96 saved RF gain sequences · no continuous-frame phase assumption\nSurrogate controls are specificity diagnostics, not independent clock or identity evidence')
    fig.tight_layout();fig.savefig(OUT/'frame_phase_harmonics.png',dpi=175);plt.close(fig)
    write(OUT/'evaluation.json',dict(rows=rows,candidates=sum(r['fourth_harmonic_rotation_candidate'] for r in rows),
        protocol_sha256=sha(target),real_DS23_accuracy_gain=False,
        no_CFO_or_position_updates_applied=True))
    print('FRAME_HARMONICS',len(rows),'probes; fourth-harmonic candidates',sum(r['fourth_harmonic_rotation_candidate'] for r in rows),flush=True)


if __name__=='__main__':main()
