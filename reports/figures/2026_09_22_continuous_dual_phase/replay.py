"""Saved fixed-tuning dual-RX phase replay; no RF collection."""
import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import fftconvolve, firwin
import report_glrt_phase_segment_comparison as legacy
from leo.storage import RecordingStore, PinnedLocalRoot
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment, apply_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from leo.analysis.starlink.templates import FRAME_RATE_HZ

SESSION = 'cap-20260823T144200-34e2144863ce'
RUN = 'capture-da59c914adfe41278262fe4b5d297de0'
START, DURATION = 49.8, .5

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    _, paths = legacy.load_path_evidence(Path('/srv/bulk/leo'), SESSION, RUN)
    tracks = legacy.select_strongest_phase_capable_tracks(legacy.deduplicate_glrt_tracks(paths), 2)
    assert tracks[0].scope.startswith('sha256:933253')
    assert tracks[1].scope.startswith('sha256:058270')
    store = RecordingStore.open_pinned(PinnedLocalRoot(Path('/srv/bulk/leo')))
    try:
        bundle = store.inspect(SESSION)
        reader = store.reader(bundle, 'stream-0', verify=True)
        fs = reader.sample_rate_hz
        raw = reader.read(round(START*fs), round(DURATION*fs), receiver_ids=(0,1))
    finally:
        store.close()
    iq = (raw[:,:,0].astype(float)+1j*raw[:,:,1].astype(float))/32768
    glrt=[]
    for rx, track in enumerate(tracks):
        epochs=legacy._local_epoch_by_probe_start(track)
        from leo.analysis.starlink.kalman_tracking import canonical_digest
        canonical={x.observation_id:x for x in track.evidence.dealiased_bank.observations}
        source_ids={s for oid in track.track.observation_ids for s in canonical[oid].source_observation_ids}
        for detection in track.evidence.pilot_scan['detections']:
            sample=detection['sample_start']
            time=sample/fs
            if not START <= time <= START+DURATION or sample not in epochs:
                continue
            candidates=[c for c in detection['candidates'] if canonical_digest(dict(sample_start=sample,candidate_rank=c['rank'],method='glrt64')) in source_ids]
            if not candidates:
                continue
            expected=float(np.polyval(track.track.absolute_coefficients_hz,time-track.track.reference_time_s))
            scores=[(c,next(s for s in c['scores'] if s['method']=='glrt64')) for c in candidates]
            candidate,score=min(scores,key=lambda pair:abs(pair[1]['tracking_cfo_hz']-expected))
            glrt.append(dict(rx=rx,time_s=time,candidate_rank=candidate['rank'],local_epoch_sample=candidate['local_epoch_sample'],frame_anchor_s=time+candidate['local_epoch_sample']/fs,**score))
    seed = float(np.polyval(tracks[1].track.absolute_coefficients_hz, START-tracks[1].track.reference_time_s)
                 -np.polyval(tracks[0].track.absolute_coefficients_hz, START-tracks[0].track.reference_time_s))
    print('IQ loaded',iq.shape,'GLRT points',len(glrt),'seed',seed,flush=True)
    fit=estimate_broadband_alignment(iq, fs, receiver_cfo_seed_hz=seed,cfo_search_half_width_hz=200000)
    model=fit.model
    tracking=frequency_held_out_tracking(iq,fs,model)
    aligned=apply_broadband_alignment(iq,fs,model)
    n=np.arange(-32,33)
    delay=np.sinc(n+model.fractional_delay_samples)*np.hanning(65);delay/=delay.sum()
    aligned[:,1]=fftconvolve(aligned[:,1],delay,mode='same')
    lo=max(-fs/2,-fs/2-model.relative_cfo_hz)+30000
    hi=min(fs/2,fs/2-model.relative_cfo_hz)-30000
    taps=firwin(513,(hi-lo)/2,fs=fs)*np.exp(2j*np.pi*(hi+lo)/2*(np.arange(513)-256)/fs)
    aligned=np.column_stack([fftconvolve(aligned[:,rx],taps,mode='same') for rx in (0,1)])
    windows=[]
    for start in range(round(.002*fs),len(iq)-round(.004*fs),round(.001*fs)):
        a,b=aligned[start:start+round(.002*fs)].T
        z=np.vdot(a,b);rho=abs(z)/np.sqrt(np.vdot(a,a).real*np.vdot(b,b).real)
        windows.append(dict(time_s=START+(start+(len(a)-1)/2)/fs,phase_deg=float(np.angle(z,deg=True)),coherence=float(rho)))
    document=dict(session=SESSION,run=RUN,stream='stream-0',start_s=START,duration_s=DURATION,sample_rate_hz=fs,
        samples_per_rx=len(iq),iq_slice_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
        source_products={x.scope:x.evidence.source_digests for x in tracks},glrt=glrt,windows=windows,
        model={k:v for k,v in asdict(model).items() if k not in ('channel_transfer','frequency_hz')},
        training=asdict(fit.training),held_out=asdict(fit.held_out),tracking=tracking,common_filter_hz=[lo,hi],
        sign='arg(RX1*conj(RX0)); rolling phase after fitted CFO/drift and delay correction',
        selection='Previously reported strongest shared 500 ms zoom; selected before this phase replay')
    (args.output/'results.json').write_text(json.dumps(document,indent=2,allow_nan=False)+'\n')
    fig,axes=plt.subplots(5,1,figsize=(12,14),sharex=True,constrained_layout=True)
    for rx,color in [(0,'tab:blue'),(1,'tab:orange')]:
        g=[r for r in glrt if r['rx']==rx]
        axes[0].plot([r['time_s'] for r in g],[r['exact_score'] for r in g],'o-',color=color,label=f'RX{rx} GLRT64 exact score')
        axes[0].plot([r['time_s'] for r in g],[r['control_score'] for r in g],':',color=color,label=f'RX{rx} control')
        axes[1].plot([r['time_s'] for r in g],[r['tracking_cfo_hz']-g[0]['tracking_cfo_hz'] for r in g],'o-',color=color,label=f"RX{rx} CFO minus {g[0]['tracking_cfo_hz']:.1f} Hz")
        anchor0=g[0]['frame_anchor_s']
        axes[4].plot([r['time_s'] for r in g],[((r['frame_anchor_s']-anchor0+.5/FRAME_RATE_HZ)%(1/FRAME_RATE_HZ)-.5/FRAME_RATE_HZ)*1e6 for r in g],'o-',color=color,label=f'RX{rx} timing vs its first anchor (wrapped)')
        axes[2].vlines([r['frame_anchor_s'] for r in g],-180+rx*15,-167+rx*15,color=color,label=f'RX{rx} detected frame-timing anchors')
    axes[0].set_ylabel('GLRT score');axes[1].set_ylabel('CFO change (Hz)')
    axes[2].scatter([r['time_s'] for r in windows],[r['phase_deg'] for r in windows],s=7,c='black',label='Common-band phase, 2 ms windows')
    tr=tracking['rows']
    t=[START+r['center_sample']/fs for r in tr]
    axes[2].scatter(t,np.rad2deg([r['training_band_phase_rad'] for r in tr]),s=8,label='A-band phase (channel-relative)',color='tab:green')
    axes[2].scatter(t,np.rad2deg([np.angle(np.exp(1j*(r['training_band_phase_rad']+r['held_band_residual_phase_rad']))) for r in tr]),s=8,label='B-band phase (channel-relative)',color='tab:purple')
    axes[2].set_ylabel('RX1 − RX0 phase (degrees)');axes[2].set_ylim(-185,185)
    axes[3].plot([r['time_s'] for r in windows],[r['coherence'] for r in windows],label='Rolling amplitude coherence',color='black')
    axes[3].plot(t,[r['held_band_coherence'] for r in tr],label='B-band amplitude coherence',color='tab:purple')
    axes[3].set_ylabel('Coherence');axes[4].set_ylabel('Frame timing change (µs)');axes[4].set_xlabel('Time from recording start (s)')
    for ax in axes:
        for idx,edge in enumerate([49.80736,49.9122176,50.0170752,50.1219328,50.2267904]):
            ax.axvline(edge,color='red',ls=':',alpha=.5,label='Refill boundary; continuity unknown' if idx==0 else None)
        ax.axvline(START+DURATION/2,color='gray',ls='--',label='Training / held-out boundary')
        ax.grid(alpha=.2);ax.legend(fontsize=8,loc='best');ax.set_xlim(START,START+DURATION)
    fig.suptitle(f'{SESSION} · stream-0 · PRE-FIX; RF continuity unknown\nFixed tuning; 500 ms stored IQ time; full-recording host duty 63.21%',fontsize=13)
    fig.savefig(args.output/'phase-and-glrt.png',dpi=170)
    zoom_start,zoom_stop=49.85,49.865
    zoom,za=plt.subplots(2,1,figsize=(12,6),sharex=True,constrained_layout=True)
    zw=[r for r in windows if zoom_start <= r['time_s'] <= zoom_stop]
    za[0].plot([r['time_s'] for r in zw],[r['phase_deg'] for r in zw],'k.-',label='Broadband phase, 2 ms windows / 1 ms stride')
    frame_predictions=[]
    for rx,color in [(0,'tab:blue'),(1,'tab:orange')]:
        anchor=min((r for r in glrt if r['rx']==rx),key=lambda r:abs(r['time_s']-zoom_start))['frame_anchor_s']
        times=[anchor+k/FRAME_RATE_HZ for k in range(-20,21) if zoom_start <= anchor+k/FRAME_RATE_HZ <= zoom_stop]
        frame_predictions.append(dict(rx=rx,anchor_s=anchor,predicted_boundaries_s=times))
        za[1].vlines(times,rx-.3,rx+.3,color=color,linestyle='--',label=f'RX{rx} nominal-period extrapolation')
        za[1].plot([anchor],[rx],'o',color=color,label=f'RX{rx} saved GLRT timing anchor')
        for tframe in times:
            za[0].axvline(tframe,color=color,alpha=.3,ls='--')
    za[0].set_ylabel('RX1 − RX0 phase (degrees)');za[1].set_yticks([0,1],['RX0','RX1'])
    za[1].set_xlabel('Time from recording start (s)')
    for ax in za:
        ax.set_xlim(zoom_start,zoom_stop);ax.grid(alpha=.2);ax.legend(fontsize=8)
    zoom.suptitle('Frame timing zoom: dots are saved timing anchors; dashed lines are predictions\nNominal 750 frames/s; phase windows are wider than one frame')
    zoom.savefig(args.output/'frame-boundary-zoom.png',dpi=170)
    document['frame_timing']=dict(frame_rate_hz=FRAME_RATE_HZ,zoom_predictions=frame_predictions,
        caveat='Integer-sample GLRT timing hypotheses, not independently verified starts for every frame. Timing jumps prevent a global frame comb. No absolute frame IDs.')
    document['continuity_correction']=dict(status='Pre-fix; RF continuity unknown; time axis is stored sample time',host_capture_span_s=94.921095577,host_duty_percent=63.210395576743,refill_boundaries_s=[49.80736,49.9122176,50.0170752,50.1219328,50.2267904])
    (args.output/'results.json').write_text(json.dumps(document,indent=2,allow_nan=False)+'\n')
    print('DONE',document['model'],tracking['tracked'],tracking['wrong_time'],flush=True)

if __name__=='__main__':
    main()
