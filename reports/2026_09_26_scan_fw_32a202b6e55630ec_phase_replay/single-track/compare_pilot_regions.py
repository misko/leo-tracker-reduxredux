"""Matched-time pilot and physically overlapping broadband phase comparison."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audit_offsets import load
from leo.analysis.qam.pilot import _KnownPilotDemodulator, _complete_frame_starts, _fit_phase_slope_frame, fractional_take
from leo.analysis.starlink.templates import edge_frequencies_hz, qin_edge_pilot_symbols, CONTROL_SYMBOL_ROLL, OFDM_SYMBOL_DURATION_S
from leo.contracts.states import StarlinkEdge

HERE=Path(__file__).resolve().parent
RATE=10_000_000

def masks(frequency, delta, center):
    tones=edge_frequencies_hz('upper')
    half_spacing=(tones[1]-tones[0])/2
    low,high=center+tones.min()-half_spacing,center+tones.max()+half_spacing
    common=(abs(frequency)<RATE/2-40000)&(abs(frequency+delta)<RATE/2-40000)
    pilot=common&(frequency>=low)&(frequency<=high)
    nonpilot=common&((frequency<low-50000)|(frequency>high+50000))
    return {'broadband':common,'pilot_band':pilot,'outside_pilot':nonpilot},(float(low),float(high))

def cross(left,right):
    p=np.vdot(left,right)
    den=np.sqrt(np.vdot(left,left).real*np.vdot(right,right).real)
    return float(np.angle(p,deg=True)),float(abs(p)/max(den,1e-30))

def main():
    selection=json.loads((HERE/'selection.json').read_text())
    candidates={(int(r['visit_index']),int(r['receiver_id'])):r for r in selection['candidate_rows']}
    inventory={int(r['visit_index']):r for r in csv.DictReader((HERE.parent/'acquisition/visit-inventory.csv').open())}
    ids=selection['visit_indices']
    starts=np.array([(int(inventory[i]['valid_start_counter'])-selection['origin_device_counter'])/RATE for i in ids])
    delta=np.array([float(candidates[i,1]['tracking_absolute_baseband_cfo_hz'])-float(candidates[i,0]['tracking_absolute_baseband_cfo_hz']) for i in ids])
    cycles=np.r_[0,np.cumsum(delta[:-1]*np.diff(starts))]
    exact=qin_edge_pilot_symbols('upper');control=qin_edge_pilot_symbols('upper',symbol_roll=CONTROL_SYMBOL_ROLL)
    symbol_time=(np.arange(300)+2.5)*OFDM_SYMBOL_DURATION_S
    centered=symbol_time-symbol_time.mean()
    rows=[];geometry=[];cache=[]
    spectra=[]
    for k,index in enumerate(ids):
        iq=load(index)
        iq[:,1]*=np.exp(-2j*np.pi*(cycles[k]+delta[k]*np.arange(len(iq))/RATE))
        candidate=candidates[index,0]
        center=float(candidate['tracking_absolute_baseband_cfo_hz'])
        fraction=float(candidate['fractional_epoch_offset_samples'])
        frame_starts=_complete_frame_starts(len(iq),RATE,int(candidate['integer_epoch_sample']),fractional_epoch_offset_samples=fraction)
        demod=[_KnownPilotDemodulator(iq[:,rx],RATE,StarlinkEdge.UPPER,center) for rx in (0,1)]
        for frame in frame_starts:
            pilot=[d.frame(frame,fractional_epoch_offset_samples=fraction) for d in demod]
            # One shared residual fit: it cannot fit away RX1-minus-RX0 phase.
            fit=_fit_phase_slope_frame(pilot[0]*np.conj(exact),pilot[0]*np.conj(control),centered,maximum_residual_cfo_hz=2000.)
            shared=np.exp(-2j*np.pi*fit.residual_cfo_hz*centered)[:,None]
            channel=[np.mean(p*np.conj(exact)*shared,axis=0) for p in pilot]
            null=[np.mean(p*np.conj(control)*shared,axis=0) for p in pilot]
            phase,coherence=cross(*channel)
            sample0=int(round(2*OFDM_SYMBOL_DURATION_S*RATE))
            sample1=int(round(302*OFDM_SYMBOL_DURATION_S*RATE))
            positions=frame+fraction+np.arange(sample0,sample1)
            samples=np.column_stack([fractional_take(iq[:,rx],positions) for rx in (0,1)])
            n=len(samples);frequency=np.fft.fftfreq(n,1/RATE)
            transforms=np.fft.fft(samples*np.hanning(n)[:,None],axis=0)
            region,bounds=masks(frequency,delta[k],center)
            row=dict(visit_index=index,time_s=float(starts[k]+positions.mean()/RATE),held_after_20ms=bool(positions[0]>=200000),qin_phase_deg=phase,qin_tone_coherence=coherence,
                     rx0_exact_control_power_ratio=float(np.sum(abs(channel[0])**2)/max(np.sum(abs(null[0])**2),1e-30)),rx1_exact_control_power_ratio=float(np.sum(abs(channel[1])**2)/max(np.sum(abs(null[1])**2),1e-30)))
            for name,mask in region.items():
                row[name+'_phase_deg'],row[name+'_coherence']=cross(transforms[mask,0],transforms[mask,1])
            row['unmasked_phase_deg'],row['unmasked_coherence']=cross(transforms[:,0],transforms[:,1])
            cache.append(dict(h0=channel[0],h1=channel[1],control0=null[0],control1=null[1],
                frame_visit_index=index,frame_time_s=row['time_s'],frame_time_in_dwell_s=float(positions.mean()/RATE),
                support_start_s=float(positions[0]/RATE),support_end_s=float((positions[-1]+1)/RATE),
                correction_cycles=float(cycles[k]+delta[k]*positions.mean()/RATE),shared_residual_hz=float(fit.residual_cfo_hz)))
            rows.append(row)
            if k==0:spectra.append(abs(transforms)**2)
        geometry.append(dict(visit_index=index,rx0_center_hz=center,rx1_center_hz=center+delta[k],delta_hz=float(delta[k]),pilot_rx0_bounds_hz=bounds,pilot_rx1_bounds_hz=[b+delta[k] for b in bounds],common_bounds_hz=[max(-RATE/2+40000,-RATE/2+40000-delta[k]),min(RATE/2-40000,RATE/2-40000-delta[k])]))
        print(f'visit {index}: {len(frame_starts)} frames',flush=True)
    with (HERE/'pilot-region-comparison.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    directory=HERE/'improvements';directory.mkdir(exist_ok=True)
    arrays={key:np.asarray([r[key] for r in cache]) for key in cache[0]}
    arrays['products']=np.conj(arrays['h0'])*arrays['h1']
    arrays['weights']=abs(arrays['products'])
    arrays['valid']=np.isfinite(arrays['products'])
    arrays['training']=arrays['support_end_s']<=.02
    arrays['held']=arrays['support_start_s']>=.02
    arrays['tone_frequency_hz']=edge_frequencies_hz('upper')
    np.savez_compressed(directory/'pilot-cache.npz',**arrays)
    (directory/'pilot-cache.json').write_text(json.dumps(dict(
        schema='single-track-pilot-cache/v1',visit_indices=ids,dwell_start_s=starts.tolist(),delta_f_hz=delta.tolist(),
        sample_rate_hz=RATE,tone_frequency_hz=arrays['tone_frequency_hz'].tolist(),
        description='Same per-dwell GLRT correction integrated over device time; h0/h1 are actual 300-symbol Qin per-tone channels. Residual frequency selected from RX0 each frame and applied equally to both; no differential phase fit or response normalization. Products=conj(h0)*h1; weights=abs(products), not independent precision. Times absolute relative to start of visit259 or dwell-local as named. Support bounds include symbol sample region, with common fractional interpolation; training/held split uses full nominal symbol support. Crossing frames excluded from frozen train/held validation. Fractional interpolation guard should additionally be checked by validation.',
        frame_count=len(cache)),indent=2)+'\n')
    summaries=[]
    for index in ids:
        subset=[r for r in rows if r['visit_index']==index and r['held_after_20ms']]
        item=dict(visit_index=index,held_frames=len(subset))
        for name in ('broadband','pilot_band','outside_pilot','qin'):
            metric='qin_tone_coherence' if name=='qin' else name+'_coherence'
            item[name+'_median_coherence']=float(np.median([r[metric] for r in subset]))
        for name in ('broadband','pilot_band','outside_pilot'):
            difference=np.radians([r['qin_phase_deg']-r[name+'_phase_deg'] for r in subset])
            item['qin_minus_'+name+'_R']=float(abs(np.mean(np.exp(1j*difference))))
        summaries.append(item)
    (HERE/'pilot-region-summary.json').write_text(json.dumps(dict(frame_count=len(rows),geometry=geometry,held_per_dwell=summaries),indent=2)+'\n')
    fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True,constrained_layout=True)
    t=[r['time_s'] for r in rows]
    names=('broadband','pilot_band','outside_pilot','qin')
    titles=('Broadband · physical RX0/RX1 overlap only','Pilot spectral band · eight-tone footprint (1.875 MHz)','Outside pilot band · 50 kHz exclusion guard','Known Qin pilots only · 300 symbols × 8 tones')
    for ax,name,title in zip(axes,names,titles):
        ax.scatter(t,[r[name+'_phase_deg'] for r in rows],s=9,color='#287c9d')
        ax.set(title=title,ylabel='RX1 − RX0 (deg)',ylim=(-185,185),yticks=[-180,-90,0,90,180])
        for k,start in enumerate(starts):
            ax.axvline(start,color='gray',alpha=.3)
            ax.axvspan(start,start+.02,color='#74a9cf',alpha=.15)
    axes[-1].set_xlabel('Seconds from visit 259 start · same matched-frame times')
    fig.suptitle('Pilot-only versus broadband phase · visits 259–263',fontsize=15)
    fig.supxlabel('Same integrated per-dwell GLRT correction and phase origin. No response normalization or per-region phase fit.',fontsize=9)
    for ext in ('png','svg'):fig.savefig(HERE/f'pilot-region-comparison.{ext}',dpi=170)
    plt.close(fig)
    spectrum=np.mean(spectra,axis=0)
    order=np.argsort(frequency)
    fig,ax=plt.subplots(figsize=(11,4),constrained_layout=True)
    for rx in (0,1):ax.plot(frequency[order]/1e6,10*np.log10(np.maximum(spectrum[order,rx],1e-30)),lw=.65,label=f'RX{rx}'+(' shifted into RX0 coordinates' if rx else ''))
    g=geometry[0]
    ax.axvspan(*[b/1e6 for b in g['pilot_rx0_bounds_hz']],color='#e6ad48',alpha=.25,label='Pilot footprint')
    ax.axvspan(g['common_bounds_hz'][1]/1e6,5,color='gray',alpha=.25,label='Excluded: outside physical overlap')
    ax.set(xlabel='Baseband frequency in RX0 coordinates (MHz)',ylabel='Mean FFT power (dB, arbitrary)',title='Offset and region audit · visit 259')
    ax.legend(fontsize=8)
    fig.savefig(HERE/'pilot-region-spectrum.png',dpi=170)
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()
