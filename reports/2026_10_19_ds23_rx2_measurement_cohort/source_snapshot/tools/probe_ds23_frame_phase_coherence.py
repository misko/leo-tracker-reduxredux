"""Test frame coherence without assuming transmitter phase continuity."""

from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from local_pilot_refinement import PilotWorkspace
from remeasure_ds23_rx2_cohort import OUT
from run_algo01_ds23_sample import ROOT, read, write, sha


def coherence(times, coefficient, energy):
    t, a, w = np.asarray(times), np.asarray(coefficient), np.asarray(energy)
    if t.ndim!=1 or a.shape!=t.shape or w.shape!=t.shape or len(t)<4 or np.any(w<=0) or not all(np.isfinite(x).all() for x in (t,a,w)):
        raise ValueError('finite supported complex frame gains and positive energies required')
    frequencies=np.linspace(-375.,375.,1501)
    rotation=np.exp(-2j*np.pi*frequencies[:,None]*(t-t.mean()))
    normalized=abs(rotation@(w*a))**2/(sum(w)*sum(w*abs(a)**2))
    k=int(np.argmax(normalized));delta=float(frequencies[k])
    phase_weights=w*abs(a)**2
    phasor=np.divide(a,abs(a),out=np.zeros_like(a),where=abs(a)>0)
    phase_only=abs(rotation@(phase_weights*phasor))**2/sum(phase_weights)**2
    j=int(np.argmax(phase_only));phase_delta=float(frequencies[j])
    adjusted=phasor*np.exp(-2j*np.pi*phase_delta*(t-t.mean()))
    center=np.angle(np.sum(phase_weights*adjusted))
    phase=np.angle(adjusted*np.exp(-1j*center))
    return dict(coherent_fraction=float(normalized[k]), frequency_correction_hz=delta,
        phase_only_fraction=float(phase_only[j]),phase_frequency_correction_hz=phase_delta,
        effective_frames=float(sum(phase_weights)**2/sum(phase_weights**2)),
        residual_phase_rad=phase, frame_time_s=t,
        phase_RMS_rad=float(np.sqrt(np.sum(w*abs(a)**2*phase**2)/np.sum(w*abs(a)**2))))


def run():
    source=ROOT/'reports/2026_10_19_ds23_fast_pilot_estimator/benchmark.json'
    saved=read(source);panels={};rows=[]
    rng=np.random.default_rng(2026101904)
    try:
        for row in saved['rows']:
            entry=row['entry'];point=entry['point'];name=entry['panel']
            if name not in panels:panels[name]=np.load(ROOT/name,allow_pickle=False)
            z=panels[name];metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz']
            values=z[point['window_key']][:,point['receiver_offset']]
            y=values[:,0].astype(float)+1j*values[:,1].astype(float)
            epoch=point['peak']['integer_epoch_sample']+point['peak']['fractional_epoch_offset_samples']
            workspace=PilotWorkspace(y,fs,point['edge'],epoch)
            fit=row['results']['continuous']['result']
            details=workspace.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],details=True)
            times=np.array([workspace.t[workspace.frames[k]].mean() for k in details['frames']])
            gains=details['coefficients'][:,0];energies=details['energies'][:,0]
            actual=coherence(times,gains,energies)
            # Fixed random-phase surrogate preserves amplitude/energy support.
            controls=[coherence(times,abs(gains)*np.exp(1j*rng.uniform(-np.pi,np.pi,len(gains))),energies)['phase_only_fraction'] for _ in range(8)]
            rows.append(dict(case=entry['case'],receiver=entry['receiver'],band=entry['band'],
                observation_id=point['observation_id'],frames=len(times),**actual,
                random_phase_control_fractions=controls))
    finally:
        for panel in panels.values():panel.close()
    write(OUT/'frame_phase_coherence.json',dict(rows=rows,source_sha256=sha(Path(__file__)),
        benchmark_sha256=sha(source),no_GPS_or_orbit_model_used=True,
        no_coherent_CFO_applied=True,frame_rate_alias_750Hz_not_resolved=True,
        controls_are_phase_surrogates_not_independent_measurements=True))
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    for rx in (1,2):
        rr=[r for r in rows if r['receiver']==rx]
        axes[0].hist([r['phase_only_fraction'] for r in rr],bins=np.linspace(0,1,21),alpha=.5,label=f'RX{rx}')
    control=[x for r in rows for x in r['random_phase_control_fractions']]
    axes[0].hist(control,bins=np.linspace(0,1,21),weights=np.ones(len(control))/8,histtype='step',color='black',label='Random phase / 8')
    axes[0].set(xlabel='Best energy-weighted phase coherence',ylabel='Probes',title='Free frame amplitudes; 750 Hz interval searched')
    axes[0].legend()
    selected=sorted(rows,key=lambda r:r['phase_only_fraction'])
    for r in (selected[0],selected[len(selected)//2],selected[-1]):
        axes[1].plot(np.array(r['frame_time_s'])*1000,r['residual_phase_rad'],'.-',label=f"RX{r['receiver']} · coherence {r['phase_only_fraction']:.2f}")
    axes[1].set(xlabel='Time in probe (ms)',ylabel='Residual frame phase (rad)',title='Lowest, median and highest coherence')
    axes[1].legend(fontsize=8)
    fig.savefig(OUT/'frame_phase_coherence.png',dpi=160);plt.close(fig)
    print('probes',len(rows),'median phase fraction',np.median([r['phase_only_fraction'] for r in rows]),'above .9',sum(r['phase_only_fraction']>.9 for r in rows),'control median',np.median(control),flush=True)


if __name__=='__main__':run()
