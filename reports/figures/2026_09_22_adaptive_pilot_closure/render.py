"""Render and audit the adaptive pilot/broadband comparison."""
import gzip
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
def wrap(x): return np.angle(np.exp(1j*x))
def main():
    document=json.loads(gzip.decompress((HERE/'results.json.gz').read_bytes()))
    injection=json.loads(gzip.decompress((HERE/'injected-588.json.gz').read_bytes()))
    baseline=next(r for r in document['visits'] if r['visit']==588)
    changed=injection['visits'][0];expected=injection['injected_phase_rad']
    assert len(baseline['rows'])==len(changed['rows'])
    errors=[]
    for a,b in zip(baseline['rows'],changed['rows']):
        assert (a['probe'],a['method'],a['weighting'])==(b['probe'],b['method'],b['weighting'])
        for key in ('pilot_phase_rad','broadband_phase_rad'):
            errors.append(float(wrap(b[key]-a[key]-expected)))
    max_error=float(np.degrees(max(abs(np.array(errors)))))
    assert max_error<.01, max_error
    fig,axes=plt.subplots(4,3,figsize=(14,12),sharex=True,sharey=True,constrained_layout=True)
    pooled=[];summaries=[]
    for ax,visit in zip(axes.flat,document['visits']):
        summary=next((s for s in visit['summaries'] if s['method']=='refined' and s['weighting']=='pilot_amplitude'),None)
        if summary is None:
            ax.text(.5,.5,'No later shared-pilot validation\nNo precision claim',transform=ax.transAxes,ha='center');ax.set_title(f"Visit {visit['visit']}")
        else:
            for method,color in [('shared_initial','tab:gray'),('refined','tab:blue')]:
                rows=[r for r in visit['rows'] if r['method']==method and r['weighting']=='pilot_amplitude']
                ax.plot([r['time_s']*1000 for r in rows],[r['offset_corrected_difference_deg'] for r in rows],'.-',color=color,label=method)
            ax.set_title(f"Visit {visit['visit']} · later RMS {summary['held_rms_deg']:.2f}°")
            pooled.extend(r['offset_corrected_difference_deg'] for r in rows if r['support_start_s']>=.06)
            summaries.append(dict(visit=visit['visit'],**summary))
        ax.axvline(60,c='gray',ls='--');ax.axhline(0,c='black',lw=.6);ax.set_ylim(-20,20);ax.grid(alpha=.2)
    axes.flat[1].legend(fontsize=8)
    for ax in axes[-1]:ax.set_xlabel('Time within dwell (ms)')
    for ax in axes[:,0]:ax.set_ylabel('Pilot − broadband residual (°)')
    fig.suptitle('Known-pilot versus broadband phase on the same frame times\nOne per-dwell reference offset fitted before 60 ms, frozen afterward; no later offset correction')
    fig.savefig(HERE/'adaptive-pilot-closure.png',dpi=150);plt.close(fig)
    rows=[r for r in baseline['rows'] if r['method']=='refined' and r['weighting']=='pilot_amplitude']
    summary=next(s for s in baseline['summaries'] if s['method']=='refined' and s['weighting']=='pilot_amplitude')
    t=[r['time_s']*1000 for r in rows];offset=np.radians(summary['training_offset_deg'])
    fig,axes=plt.subplots(3,1,figsize=(11,10),sharex=True,constrained_layout=True)
    axes[0].plot(np.array(baseline['scalar_time_s'])*1000,np.degrees(wrap(np.array(baseline['scalar_unwrapped_phase_rad']))),color='gray',alpha=.6,label='0.5 ms broadband phase')
    axes[0].plot(t,[np.degrees(wrap(r['pilot_phase_rad']-offset)) for r in rows],'o',label='Refined pilot, training offset applied')
    axes[0].plot(t,[np.degrees(r['broadband_phase_rad']) for r in rows],'x',ms=9,label='Broadband, same frame support')
    axes[1].plot(t,[r['pilot_residual_frequency_hz'] for r in rows],'o-',label='Pilot residual frequency')
    axes[1].plot(t,[r['broadband_residual_frequency_hz'] for r in rows],'x-',label='Broadband residual frequency')
    axes[2].plot(t,[r['offset_corrected_difference_deg'] for r in rows],'o-',label='Pilot − broadband')
    for ax in axes:ax.axvline(60,c='gray',ls='--');ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[0].set_ylabel('Wrapped residual phase (°)');axes[1].set_ylabel('Residual frequency (Hz)');axes[2].set_ylabel('Phase discrepancy (°)');axes[2].set_xlabel('Time within visit 588 (ms)')
    fig.suptitle('Adaptive visit 588 · phase and frequency from two estimator families\nShared coarse frequency branch; independently fitted local frequency; same frame support')
    fig.savefig(HERE/'visit-588-pilot-phase-frequency.png',dpi=160);plt.close(fig)
    audit=dict(pooled_held_probe_count=len(pooled),pooled_held_rms_deg=float(np.sqrt(np.mean(np.array(pooled)**2))),
               injection_phase_rad=expected,injection_max_phase_error_deg=max_error,summaries=summaries,
               limitations='Conditional inter-method discrepancy, not physical truth; only 3 later probes per validated dwell; shared IQ/coarse branch; source selection was phase-blind')
    (HERE/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
