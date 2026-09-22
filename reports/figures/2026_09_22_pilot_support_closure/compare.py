"""Compare pilot and broadband phase using identical frame-time support."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor

def wrap(x):return np.angle(np.exp(1j*x))
def main():
    root=Path(__file__).parent.parent
    p=json.loads((Path(__file__).parent/'pilot-results.json').read_text())
    d=json.loads((root/'2026_09_22_postfix_phase_diagnosis/diagnosis.json').read_text())
    s=d['series']['1250'];t=np.array(s['time_s']);phi=np.array(s['unwrapped_rad']);m=p['model'];fs=2500000
    def carrier(times):
        dt=np.asarray(times)-31.8-m['reference_sample']/fs
        return 2*np.pi*(m['relative_cfo_hz']*dt+.5*m['relative_cfo_rate_hz_s']*dt**2)
    rows=[];summaries=[];excluded=[]
    for name in ['pilot_branch_lifted','pilot_common_authority','pilot_shared_residual','pilot_refined_authority']:
        for weighting in ['pilot_amplitude','uniform']:
            series=[]
            for r in p['pilots']:
                if r['method']!=name:continue
                o=r['observation'];center=r['time_s'];origin=center-o['center_sample']/fs
                ft=origin+np.array(o['receivers'][0]['frame_starts'])/fs
                if min(ft)<min(t) or max(ft)>max(t):
                    excluded.append(dict(method=name,weighting=weighting,time_s=center,reason='Pilot frame lies outside valid filtered broadband window centers'));continue
                z=[np.array([complex(v['real'],v['imag']) for v in rx['frame_phasors']]) for rx in o['receivers']]
                weights=np.sqrt(abs(z[0])*abs(z[1])) if weighting=='pilot_amplitude' else np.ones(len(ft))
                basef=m['relative_cfo_hz']+m['relative_cfo_rate_hz_s']*(center-31.8-m['reference_sample']/fs)
                values=np.exp(1j*(np.interp(ft,t,phi)+carrier(ft)-carrier(center)-2*np.pi*basef*(ft-center)))
                freq,expected,resultant=fit_linear_phasor(values,ft,weights,center)
                measured=np.radians(r['phase_deg']);difference=wrap(measured-expected)
                series.append(dict(method=name,weighting=weighting,time_s=center,pilot_phase_rad=measured,broadband_support_phase_rad=expected,difference_rad=float(difference),broadband_residual_frequency_hz=freq,pilot_residual_frequency_hz=o['relative_frequency_hz']-basef,broadband_resultant=resultant,pilot_resultant=o['resultant_length'],frame_count=len(ft),frame_times_s=ft.tolist()))
            training=[v for v in series if v['time_s']<32.3]
            offset=float(np.angle(np.mean(np.exp(1j*np.array([v['difference_rad'] for v in training])))))
            for v in series:v['offset_corrected_difference_deg']=float(np.degrees(wrap(v['difference_rad']-offset)))
            held=[v for v in series if v['time_s']>=32.3];errors=np.array([v['offset_corrected_difference_deg'] for v in held])
            summaries.append(dict(method=name,weighting=weighting,training_offset_deg=float(np.degrees(offset)),held_count=len(held),held_rms_deg=float(np.sqrt(np.mean(errors**2))),held_max_absolute_deg=float(max(abs(errors))),held_mean_deg=float(np.mean(errors))))
            rows.extend(series)
    out=Path('/tmp/pilot-support-closure');out.mkdir(exist_ok=True)
    (out/'results.json').write_text(json.dumps(dict(summaries=summaries,rows=rows,excluded=excluded),indent=2)+'\n')
    fig,axes=plt.subplots(3,1,figsize=(12,10),sharex=True,constrained_layout=True)
    for name,color in [('pilot_branch_lifted','tab:red'),('pilot_common_authority','tab:orange'),('pilot_shared_residual','tab:blue'),('pilot_refined_authority','tab:green')]:
        rr=[v for v in rows if v['method']==name and v['weighting']=='pilot_amplitude']
        tt=[v['time_s'] for v in rr]
        axes[0].plot(tt,[v['offset_corrected_difference_deg'] for v in rr],'o',ms=3,color=color,label=name)
        if name=='pilot_refined_authority':
            axes[1].plot(tt,[v['broadband_residual_frequency_hz'] for v in rr],'.-',label='Broadband, same frame support')
            axes[1].plot(tt,[v['pilot_residual_frequency_hz'] for v in rr],'.-',label='Pilot, refined shared frequency reference')
            axes[2].plot(tt,[v['offset_corrected_difference_deg'] for v in rr],'o-',label='Matched pilot amplitude weights')
    rr=[v for v in rows if v['method']=='pilot_refined_authority' and v['weighting']=='uniform']
    axes[2].plot([v['time_s'] for v in rr],[v['offset_corrected_difference_deg'] for v in rr],'.-',label='Uniform frame weights control')
    for ax in axes:ax.axvline(32.3,c='gray',ls='--');ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[0].set_ylabel('Pilot − broadband phase (°)');axes[1].set_ylabel('Residual frequency (Hz)');axes[2].set_ylabel('Corrected phase difference (°)');axes[2].set_xlabel('Elapsed device sample time (s)')
    fig.suptitle('Same-support phase closure: independent frequency fits, training-only constant offset')
    fig.savefig(out/'same-support-phase-closure.png',dpi=160)
    print(json.dumps(summaries,indent=2))
if __name__=='__main__':main()
