"""Template-predicted bias of three-bin magnitude-parabola CFO interpolation."""

from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.starlink.templates import qin_edge_pilot_frame,OFDM_SYMBOL_DURATION_S

OUT=ROOT/'reports/2026_10_19_native_fft_bias'


def response_curve(fs,edge,step=500.):
    template=qin_edge_pilot_frame(fs,edge);t=np.arange(len(template))/fs
    symbols=np.floor(t/OFDM_SYMBOL_DURATION_S).astype(int)
    use=(symbols>=2)&(symbols<302)&(symbols%2==0);times=t[use]
    energy=abs(template[use])**2;energy=energy/energy.sum()
    delta=np.linspace(-step/2,step/2,1001);scores=[]
    for offset in (-step,0,step):
        frequency=delta-offset;power=[]
        for begin in range(0,len(delta),64):
            phase=np.exp(2j*np.pi*frequency[begin:begin+64,None]*times[None])
            power.extend(abs(phase@energy))
        scores.append(np.array(power))
    left,middle,right=scores;curve=left-2*middle+right
    measured=.5*(left-right)/curve*step
    if np.any(np.diff(measured)<=0):raise ValueError('CFO response is not invertible')
    return dict(actual_offset_hz=delta,reported_offset_hz=measured,step_hz=step)


def debias(cfo,response):
    f=np.asarray(cfo,float);step=response['step_hz'];center=np.floor(f/step+.5)*step
    return center+np.interp(f-center,response['reported_offset_hz'],response['actual_offset_hz'])


def run():
    OUT.mkdir(parents=True,exist_ok=True);source=ROOT/'reports/2026_10_19_native_cfo_time_reference/result.json'
    native=read(source);records=[];curves={}
    for fs in (2500000,10000000):
        for edge in ('lower','upper'):
            curve=response_curve(fs,edge);curves[f'{fs}/{edge}']=curve
            for r in native['summaries']:
                if r['sample_rate_hz']!=fs or r['edge']!=edge:continue
                truth=r['CFO_hz'];measured=truth+r['zero_chirp_error_hz']
                # Near-DC/fallback behavior is outside this local interpolation model.
                eligible=abs(measured)>1000 and abs(measured)<399000
                corrected=float(debias(measured,curve)) if eligible else measured
                records.append(dict(sample_rate_hz=fs,edge=edge,truth_CFO_hz=truth,epoch_fraction=r['epoch_fraction'],
                    eligible=eligible,original_error_hz=r['zero_chirp_error_hz'],corrected_error_hz=corrected-truth))
    summaries=[]
    for fs in (2500000,10000000):
        for edge in ('lower','upper'):
            selected=[r for r in records if r['sample_rate_hz']==fs and r['edge']==edge and r['eligible']]
            summaries.append(dict(sample_rate_hz=fs,edge=edge,eligible=len(selected),
                original_RMS_hz=float(np.sqrt(np.mean([r['original_error_hz']**2 for r in selected]))),
                corrected_RMS_hz=float(np.sqrt(np.mean([r['corrected_error_hz']**2 for r in selected]))),
                maximum_corrected_error_hz=float(max(abs(r['corrected_error_hz']) for r in selected))))
    write(OUT/'result.json',dict(records=records,summaries=summaries,response_curves=curves,
        source_sha256=sha(Path(__file__)),native_test_sha256=sha(source),
        response_built_from_published_template_power_and_known_interpolator_only=True,
        native_measurements_were_not_used_to_fit_the_response=True,
        excluded_near_DC_or_boundary_cases_are_not_claimed_corrected=True,
        actual_capture_binary_identity_and_noise_multipath_applicability_not_qualified=True))
    print(summaries,flush=True)


if __name__=='__main__':run()
