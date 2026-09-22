"""Fit the frozen adaptive cohort using A-band-only curve selection."""
import json,sys
from pathlib import Path
from dataclasses import replace
import numpy as np
from scipy.interpolate import UnivariateSpline
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).parent.parent
sys.path.insert(0,str(ROOT/'2026_09_22_dynamic_channel_phase'))
from experiment import normalize_response
from report_broadband_alignment import frozen_edge_evidence,serializable
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

VISITS=(376,453,486,513,537,564,588,614,638,668,697,724)
SESSION='scan-hop-e46d3aba244cf641'
def wrap(x):return np.angle(np.exp(1j*x))

def select_fit(time,phase):
    """Offline descriptive fit: choose complexity with A-only interleaved CV."""
    x=np.asarray(time);x=(x-x[0])/(x[-1]-x[0]);y=np.unwrap(phase)
    sigma=max(.04,float(np.median(abs(np.diff(y,2)))/.6745/np.sqrt(6)))
    candidates=['linear','quadratic','cubic','spline_0','spline_1','spline_4','spline_16']
    def fit(name,train,predict):
        if name in candidates[:3]:return np.polyval(np.polyfit(x[train],y[train],candidates.index(name)+1),predict)
        factor=float(name.split('_')[1]);return UnivariateSpline(x[train],y[train],s=len(train)*sigma*sigma*factor,ext=0)(predict)
    errors={}
    for name in candidates:
        residual=[]
        for fold in range(3):
            test=np.arange(1,len(x)-1)[np.arange(1,len(x)-1)%3==fold];train=np.setdiff1d(np.arange(len(x)),test)
            residual.extend(wrap(fit(name,train,x[test])-y[test]))
        errors[name]=float(np.sqrt(np.mean(np.asarray(residual)**2)))
    best=next(name for name in candidates if errors[name]<=min(errors.values())+1e-9);curves={name:fit(name,np.arange(len(x)),x) for name in candidates}
    return best,curves,errors,sigma

def main():
    out=Path('/tmp/adaptive-phase-fit');out.mkdir(exist_ok=True)
    evidence=frozen_edge_evidence('e46d3aba244cf641');by={r['visit_index']:r for r in evidence['visits']}
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);rows=[]
    with AdaptiveHopAnalysisInputStore(store).source(SESSION) as source:
        assert source.input_manifest_sha256==evidence['input_manifest_sha256']
        fs=source.receipt.plan.geometry.sample_rate_hz;n=4096;freq=np.fft.fftshift(np.fft.fftfreq(n,1/fs));win=np.hanning(n)
        for index in VISITS:
            iq=source.read_visit(index)
            try:
                fit=estimate_broadband_alignment(iq,fs,receiver_cfo_seed_hz=by[index]['train_peak']['frequency_hz'],cfo_search_half_width_hz=2000)
                m=fit.model;left=[];right=[]
                for start in range(0,len(iq)//2-n+1,n):
                    dt=(np.arange(start,start+n)-m.reference_sample)/fs
                    rotation=np.exp(-2j*np.pi*(m.relative_cfo_hz*dt+.5*m.relative_cfo_rate_hz_s*dt**2))
                    left.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,0]*win)))
                    right.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,1]*rotation*win)))
                eligible=abs(freq)<fs/2-40000
                for sample in [0,len(iq)-1]:eligible&=abs(freq+m.relative_cfo_hz+m.relative_cfo_rate_hz_s*(sample-m.reference_sample)/fs)<fs/2-40000
                ids,h,history=normalize_response(np.array(left),np.array(right),freq,np.searchsorted(freq,m.frequency_hz),m.channel_transfer,eligible)
                updated=replace(m,frequency_hz=tuple(freq[ids]),channel_transfer=tuple(h))
                allphase=frequency_held_out_tracking(iq,fs,updated,training_fraction=0)
                held=frequency_held_out_tracking(iq,fs,updated)
                tt=np.array([r['center_sample']/fs for r in allphase['rows']]);a=np.array([r['training_band_phase_rad'] for r in allphase['rows']])
                best,curves,errors,sigma=select_fit(tt,a)
                ht=np.array([r['center_sample']/fs for r in held['rows']]);ha=np.array([r['training_band_phase_rad'] for r in held['rows']]);hb=np.array([r['held_band_residual_phase_rad'] for r in held['rows']])
                # Interpolation is of fitted unwrapped curves, never wrapped degrees.
                validations={}
                for name,curve in curves.items():
                    prediction=np.interp(ht,tt,curve);residual=wrap(ha+hb-prediction)
                    validations[name]=dict(held_B_phase_rms_deg=float(np.degrees(np.sqrt(np.mean(residual**2)))),held_B_phase_mean_deg=float(np.degrees(np.angle(np.mean(np.exp(1j*residual))))),held_B_phase_resultant=float(abs(np.mean(np.exp(1j*residual)))))
                good=held['tracked']['coherence']>max(.05,3*held['wrong_time']['coherence']) and validations[best]['held_B_phase_resultant']>.8 and np.degrees(errors[best])<30
                rows.append(dict(visit=index,status='supported' if good else 'unqualified',model=serializable(m),updated_frequency_hz=freq[ids].tolist(),updated_transfer=[[z.real,z.imag] for z in h],training_response_history=history,full_time_series=allphase['rows'],held_out=held,A_cv_rms_deg={k:float(np.degrees(v)) for k,v in errors.items()},selected_model=best,time_s=tt.tolist(),fitted_phase_rad={k:v.tolist() for k,v in curves.items()},validation=validations,sigma_proxy_rad=sigma,wrapped_native_fit_deg=np.degrees(wrap(curves[best]+m.phase_rad)).tolist()))
                print(index,rows[-1]['status'],best,validations[best],flush=True)
            except ValueError as exc:
                rows.append(dict(visit=index,status='abstained',reason=str(exc)));print(index,'abstained',exc,flush=True)
    document=dict(session=SESSION,input_manifest_sha256=evidence['input_manifest_sha256'],selection='All 12 previously frozen visits; no phase-based reselection',rows=rows,qualification='Held B tracked coherence > max(0.05, 3*wrong-time), selected B phase resultant >0.8, A CV RMS <30 degrees; heuristic not calibrated false-positive probability')
    (out/'results.json').write_text(json.dumps(serializable(document),indent=2)+'\n')
    fig,axes=plt.subplots(4,3,figsize=(15,13),sharex=True,sharey=True,constrained_layout=True)
    for ax,row in zip(axes.flat,rows):
        if row['status']=='abstained':ax.text(.5,.5,row['reason'],transform=ax.transAxes,ha='center',wrap=True);continue
        model=row['model'];tt=np.array(row['time_s'])*1000
        ap=np.array([r['training_band_phase_rad'] for r in row['full_time_series']])+model['phase_rad']
        ax.scatter(tt,np.degrees(wrap(ap)),s=5,c='green',alpha=.6,label='A-band phase')
        hr=row['held_out']['rows'];bt=np.array([r['center_sample']/fs*1000 for r in hr]);bp=np.array([r['training_band_phase_rad']+r['held_band_residual_phase_rad'] for r in hr])+model['phase_rad']
        ax.scatter(bt,np.degrees(wrap(bp)),s=6,c='purple',marker='x',label='Held B-band phase')
        y=np.array(row['wrapped_native_fit_deg']);y[np.r_[False,abs(np.diff(y))>180]]=np.nan
        ax.plot(tt,y,c='black' if row['status']=='supported' else 'gray',ls='-' if row['status']=='supported' else ':',lw=1.4,label='A-selected fitted curve');ax.axvline(60,c='gray',ls='--')
        ax.set_title(f"Visit {row['visit']} · {row['selected_model']} · {row['status']}\nB RMS {row['validation'][row['selected_model']]['held_B_phase_rms_deg']:.1f}°")
        ax.set_ylim(-185,185);ax.set_xlim(0,120);ax.grid(alpha=.2)
    for ax in axes[-1]:ax.set_xlabel('Time within dwell (ms)')
    for ax in axes[:,0]:ax.set_ylabel('Wrapped residual phase (°)')
    axes[0,0].legend(fontsize=7);fig.suptitle('Adaptive shared-track phase fits · independent intercept per dwell\nResponse normalized on first 60 ms; curve chosen using A only; B validates last 60 ms')
    fig.savefig(out/'adaptive-phase-fits.png',dpi=160)
    row=next(r for r in rows if r['visit']==588)
    tt=np.array(row['time_s'])*1000; offset=row['model']['phase_rad']
    fig,axes=plt.subplots(2,1,figsize=(11,8),constrained_layout=True)
    observed=np.unwrap([r['training_band_phase_rad'] for r in row['full_time_series']])+offset
    axes[0].scatter(tt,np.degrees(observed),s=12,c='green',label='Measured A-band phase')
    for name in ['linear','quadratic','cubic',row['selected_model']]:
        axes[0].plot(tt,np.degrees(np.array(row['fitted_phase_rad'][name])+offset),label=name)
    hr=row['held_out']['rows']; ht=np.array([r['center_sample']/fs*1000 for r in hr])
    bp=np.array([r['training_band_phase_rad']+r['held_band_residual_phase_rad'] for r in hr])+offset
    for name in ['linear','quadratic','cubic',row['selected_model']]:
        prediction=np.interp(ht,tt,np.array(row['fitted_phase_rad'][name])+offset)
        rms=row['validation'][name]['held_B_phase_rms_deg']
        axes[1].plot(ht,np.degrees(wrap(bp-prediction)),label=f'{name}: {rms:.1f}° RMS')
    axes[0].axvline(60,c='gray',ls='--');axes[1].axhline(0,c='gray',lw=.7)
    axes[0].set_ylabel('Unwrapped residual phase (°)');axes[1].set_ylabel('Held B minus fitted phase (°)')
    for ax in axes:ax.set_xlabel('Time within dwell (ms)');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Adaptive visit 588 · fit complexity selected with A-band data only\nHeld B-band discrepancy checks the curve; it is not a geometric-phase error bar')
    fig.savefig(out/'visit-588-fit-comparison.png',dpi=160)

if __name__=='__main__':main()
