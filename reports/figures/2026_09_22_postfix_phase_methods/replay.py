"""Bounded comparison of existing phase methods on verified saved dual IQ."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve, firwin
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import report_glrt_phase_segment_comparison as legacy
from report_broadband_alignment import serializable
from report_glrt_guided_broadband_phase import bootstrap_frequency
from leo.storage import RecordingStore, PinnedLocalRoot
from leo.contracts.states import StarlinkEdge
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment, apply_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from leo.analysis.starlink.glrt_guided_broadband_phase import GuidePoint, estimate_glrt_guided_broadband_phase
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed, extract_dual_receiver_phase
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace

FS=2500000
START=31.8
def wrap(x):return np.angle(np.exp(1j*np.asarray(x)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((Path(__file__).parent.parent/'2026_09_22_postfix_dual_selection/verification.json').read_text())
    store=RecordingStore.open_pinned(PinnedLocalRoot(Path('/srv/bulk/leo')))
    try:
        b=store.inspect(receipt['session']);raw=store.reader(b,'stream-1',verify=True).read(round(START*FS),FS,receiver_ids=(0,1))
    finally:store.close()
    assert hashlib.sha256(raw.tobytes()).hexdigest()==receipt['raw_slice_sha256']
    iq=(raw[:,:,0].astype(float)+1j*raw[:,:,1].astype(float))/32768
    _,paths=legacy.load_path_evidence(Path('/srv/bulk/leo'),receipt['session'],receipt['run'])
    tracks=legacy.deduplicate_glrt_tracks(paths)
    selected=[next(t for t in tracks if t.branch_id==branch) for branch in receipt['branches']]
    lookups=[{d['sample_start']:d for d in t.evidence.pilot_scan['detections']} for t in selected]
    by_rx=[{round(s['time_s']*FS):s for s in receipt['scores'] if s['rx']==rx} for rx in (0,1)]
    seed=np.median([by_rx[1][n]['tracking_cfo_hz']-by_rx[0][n]['tracking_cfo_hz'] for n in by_rx[0] if n-round(START*FS)<FS/2])
    print('Fit broadband',seed,flush=True)
    full_fit_failure=None
    try:
        fit=estimate_broadband_alignment(iq,FS,receiver_cfo_seed_hz=seed,cfo_search_half_width_hz=200000)
        fit_samples=len(iq)
    except ValueError as exc:
        full_fit_failure='Full second, ±200 kHz: '+str(exc);fit_samples=len(iq)
        try:
            fit=estimate_broadband_alignment(iq,FS,receiver_cfo_seed_hz=seed,cfo_search_half_width_hz=600000)
        except ValueError as short_exc:
            full_fit_failure+='; full second, ±600 kHz: '+str(short_exc);fit_samples=FS//10
            fit=estimate_broadband_alignment(iq[:fit_samples],FS,receiver_cfo_seed_hz=seed,cfo_search_half_width_hz=600000)
    m=fit.model
    def carrier(sample):
        dt=(np.asarray(sample)-m.reference_sample)/FS
        return 2*np.pi*(m.relative_cfo_hz*dt+.5*m.relative_cfo_rate_hz_s*dt**2)
    tracker=frequency_held_out_tracking(iq,FS,m,training_fraction=fit_samples/(2*len(iq)))
    guides=[];pilots=[];failures=[]
    for n in sorted(by_rx[0]):
        local=n-round(START*FS);chunk=iq[local:local+50000]
        candidates=[next(c for c in lookups[rx][n]['candidates'] if c['rank']==by_rx[rx][n]['candidate_rank']) for rx in (0,1)]
        estimates=[]
        for rx,c in enumerate(candidates):
            ws=_conditioned_correlation_workspace(chunk[:,rx],FS,c['local_epoch_sample'],c['acquired_cfo_hz'],edge=StarlinkEdge.UPPER,selected_symbols=np.arange(2,66),fractional_epoch_offset_samples=c.get('fractional_epoch_offset_samples') or 0)
            estimates.append(bootstrap_frequency(ws.select(np.arange(2,66)),c['acquired_cfo_hz'],seed=816+rx+local))
        guides.append(dict(sample=local+25000,relative_frequency_hz=estimates[1]['frequency_hz']-estimates[0]['frequency_hz'],sigma_hz=float(np.hypot(*(e['sigma_hz'] for e in estimates))),support_start=local,support_stop=local+50000,receivers=estimates))
        epoch_delta=((candidates[1]['local_epoch_sample']-candidates[0]['local_epoch_sample']+FS/1500)%(FS/750)-FS/1500)
        if abs(epoch_delta)>2:
            failures.append(dict(time_s=n/FS,reason='RX timing hypotheses differ by more than 2 samples',epoch_difference_samples=epoch_delta));continue
        seeds=tuple(ReceiverPhaseSeed(c['acquired_cfo_hz'],c['local_epoch_sample']+(c.get('fractional_epoch_offset_samples') or 0)) for c in candidates)
        for name,lift in [('pilot_principal',False),('pilot_branch_lifted',True)]:
            try:
                obs=extract_dual_receiver_phase(chunk,FS,StarlinkEdge.UPPER,candidates[0]['local_epoch_sample'],seeds,frame_radius=16,lift_frame_frequency_branch=lift)
                center=local+obs.center_sample
                pilots.append(dict(method=name,time_s=START+center/FS,phase_deg=float(np.degrees(wrap(obs.wrapped_phase_rad-carrier(center)))),observation=serializable(obs)))
            except ValueError as exc:failures.append(dict(time_s=n/FS,method=name,reason=str(exc)))
    print('Pilot results',len(pilots),'failures',len(failures),flush=True)
    guidepoints=[GuidePoint(g['sample'],g['relative_frequency_hz'],g['sigma_hz']) for g in guides if g['support_stop']<=fit_samples/2]
    guided={}
    for name,bias in [('absolute',False),('evolution',True)]:
        guided[name]=estimate_glrt_guided_broadband_phase(iq[:fit_samples],FS,guidepoints,broadband_cfo_seed_hz=m.relative_cfo_hz,cfo_search_half_width_hz=2000,fit_guide_bias=bias)
    aligned=apply_broadband_alignment(iq,FS,m)
    taps=np.sinc(np.arange(-32,33)+m.fractional_delay_samples)*np.hanning(65);taps/=taps.sum()
    aligned[:,1]=fftconvolve(aligned[:,1],taps,mode='same')
    lo=max(-FS/2,-FS/2-m.relative_cfo_hz)+30000;hi=min(FS/2,FS/2-m.relative_cfo_hz)-30000
    filt=firwin(513,(hi-lo)/2,fs=FS)*np.exp(2j*np.pi*(hi+lo)/2*(np.arange(513)-256)/FS)
    aligned=np.column_stack([fftconvolve(aligned[:,rx],filt,mode='same') for rx in (0,1)])
    windows=[]
    for start in range(5000,FS-10000,2500):
        x,y=aligned[start:start+5000].T;cross=np.conj(x)*y;z=cross.sum();rho=abs(z)/np.sqrt(np.vdot(x,x).real*np.vdot(y,y).real)
        delete=np.array([np.angle(z-cross[group].sum()) for group in np.array_split(np.arange(len(x)),10)])
        se=np.sqrt(.9*np.sum(wrap(delete-np.angle(z))**2))
        windows.append(dict(time_s=START+(start+2499.5)/FS,phase_deg=float(np.degrees(np.angle(z))),coherence=float(rho),normalized_prediction_error=float(np.sqrt(1-rho**2)),conditional_phase_se_deg=float(np.degrees(se))))
    doc=dict(selection=receipt,full_second_fit_failure=full_fit_failure,fit_samples=fit_samples,model=serializable(m),training=serializable(fit.training),held_out=serializable(fit.held_out),tracker=tracker,guided=serializable(guided),guides=guides,pilots=pilots,failures=failures,windows=windows,common_filter_hz=[lo,hi],phase_convention='RX1 minus RX0; subtract same unguided broadband carrier at each measurement time; native waveform/channel references remain distinct')
    (a.output/'results.json').write_text(json.dumps(serializable(doc),indent=2,allow_nan=False)+'\n')
    fig,axes=plt.subplots(5,1,figsize=(13,15),sharex=True,constrained_layout=True)
    for rx,color in [(0,'tab:blue'),(1,'tab:orange')]:
        g=[s for s in receipt['scores'] if s['rx']==rx]
        axes[0].plot([s['time_s'] for s in g],[s['exact_score'] for s in g],'o',ms=3,color=color,label=f'RX{rx} GLRT exact')
        axes[0].plot([s['time_s'] for s in g],[s['control_score'] for s in g],'.',color=color,alpha=.5,label=f'RX{rx} control')
    wt=np.array([r['time_s'] for r in windows]);wp=np.array([r['phase_deg'] for r in windows])
    axes[1].scatter(wt,wp,s=3,c='black',label='Broad common-band scalar ML / phase-grid maximum')
    times=np.linspace(START,START+1,1500);samples=(times-START)*FS
    axes[1].plot(times,np.full(len(times),np.degrees(m.phase_rad)),label='Frozen broadband intercept (native frequency reference)')
    for name,g in guided.items():
        gm=g.map_model;dt=(samples-gm.reference_sample)/FS
        prediction=gm.observed_phase_rad+2*np.pi*(gm.relative_cfo_hz*dt+.5*gm.relative_cfo_rate_hz_s*dt**2)-carrier(samples)
        wrapped=np.degrees(wrap(prediction));wrapped[np.r_[False,abs(np.diff(wrapped))>180]]=np.nan
        axes[1].plot(times,wrapped,label=f'GLRT-guided {name}, frozen model')
    for name,color in [('pilot_principal','tab:red'),('pilot_branch_lifted','tab:purple')]:
        rows=[r for r in pilots if r['method']==name]
        axes[2].errorbar([r['time_s'] for r in rows],[r['phase_deg'] for r in rows],yerr=[r['observation']['phase_standard_error_deg'] for r in rows],fmt='.',color=color,label=name,alpha=.7)
    tr=tracker['rows'];tt=[START+r['center_sample']/FS for r in tr]
    for name,color,key in [('A-band tracked phase','tab:green',False),('B-band independent check','tab:purple',True)]:
        pp=[m.phase_rad+r['training_band_phase_rad']+(r['held_band_residual_phase_rad'] if key else 0) for r in tr]
        axes[3].scatter(tt,np.degrees(wrap(pp)),s=4,color=color,label=name+' + fitted intercept')
    axes[3].scatter(wt,wp,s=2,c='black',alpha=.25,label='Scalar phase (different spectral weighting)')
    axes[4].plot(wt,[r['coherence'] for r in windows],c='black',label='Common-band amplitude coherence')
    axes[4].plot(tt,[r['held_band_coherence'] for r in tr],color='tab:purple',alpha=.6,label='B-band coherence')
    for r in pilots:
        if r['method']=='pilot_branch_lifted':axes[4].scatter(r['time_s'],r['observation']['resultant_length'],color='tab:red',s=10)
    axes[4].plot([],[],'.',color='tab:red',label='Pilot resultant (different statistic)')
    labels=['GLRT score','Residual phase (°)','Edge-pilot residual phase (°)','Tracked residual phase (°)','Coherence / resultant']
    for i,ax in enumerate(axes):
        ax.set_ylabel(labels[i]);ax.axvline(START+fit_samples/(2*FS),color='gray',ls='--');ax.legend(fontsize=8,loc='upper right');ax.grid(alpha=.2);ax.set_xlim(START,START+1)
        if i in (1,2,3):ax.set_ylim(-185,185)
    axes[-1].set_xlabel('Elapsed device sample time in verified gap-free dwell (s)')
    fig.suptitle('Post-fix .21 dual RX · 100% counter duty · all methods on the same 1 s IQ\nCommon carrier removed; phase-reference differences remain · dashed line = training/held-out split')
    fig.savefig(a.output/'phase-methods-vs-time.png',dpi=160)
    for ax in axes:ax.set_xlim(32.3,32.4)
    fig.savefig(a.output/'phase-methods-100ms-zoom.png',dpi=160)
    fig2,aa=plt.subplots(3,1,figsize=(13,10),sharex=True,constrained_layout=True)
    grid=np.linspace(-180,180,361)
    heat=np.array([r['coherence']*np.cos(np.radians(grid-r['phase_deg'])) for r in windows]).T
    im=aa[0].pcolormesh(wt,grid,heat,shading='auto',cmap='coolwarm',vmin=-.3,vmax=.3);fig2.colorbar(im,ax=aa[0],label='Signed coherence')
    aa[0].scatter(wt,wp,s=2,c='black');aa[0].set_ylabel('Candidate phase (°)')
    aa[1].plot(wt,[r['normalized_prediction_error'] for r in windows]);aa[1].set_ylabel('Minimum normalized error')
    aa[2].plot(wt,[r['conditional_phase_se_deg'] for r in windows]);aa[2].set_ylabel('Conditional phase SE (°)')
    for ax in aa:ax.axvline(START+fit_samples/(2*FS),c='gray',ls='--');ax.grid(alpha=.2)
    aa[-1].set_xlabel('Elapsed device sample time (s)');fig2.suptitle('Constant-phase enumeration in 2 ms windows, advanced every 1 ms')
    fig2.savefig(a.output/'phase-likelihood-vs-time.png',dpi=160)
    # Every sample in a prespecified 2 ms excerpt, with no point decimation.
    n=np.arange(round(.25*FS),round(.252*FS));fig3,ab=plt.subplots(2,1,figsize=(13,6),sharex=True,constrained_layout=True)
    for ax,values,label in zip(ab,[iq,aligned],['Raw IQ','Common-band, frequency/delay corrected IQ']):
        ax.scatter(START+n/FS,np.degrees(np.angle(values[n,1]*values[n,0].conj())),s=.4);ax.set_ylabel('RX1 − RX0 phase (°)');ax.set_title(label);ax.set_ylim(-180,180)
    ab[-1].set_xlabel('Elapsed device sample time (s)');fig3.suptitle('Every IQ sample in the fixed 32.050–32.052 s excerpt; 5,000 samples per RX')
    fig3.savefig(a.output/'per-sample-phase.png',dpi=160)
    print('DONE',serializable(fit.held_out),tracker['tracked'],tracker['wrong_time'],flush=True)

if __name__=='__main__':main()
