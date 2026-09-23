"""Controlled saved-IQ ablation: equal 1.6384 ms FFT duration at all rates.

Same selected dwells and numerical functions; no IQ resampling or new RF.
This changes FFT grouping/masks as well as averaging, not only SNR.
"""
import dataclasses
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base_replay', ROOT.parent/'2026_09_23_scan_1aa_phase_methods/replay_methods.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopVisitAnalysisV1, DualRx10mAdaptiveHopVisitAnalysisV2,
    Feature103VisitAnalysisV3, Feature104VisitAnalysisV4,
)


def run():
    captures=base.AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    results=[]
    started=time.monotonic()
    for entry in json.loads((ROOT/'selection.json').read_text()):
        if not entry['selected_visits']:
            continue
        sid=entry['session_id']
        original=ROOT.parent/'2026_09_23_scan_1aa_phase_methods' if sid=='scan-fw-1aa1d50103d97388' else ROOT/sid
        native=json.loads((original/'comparison.json').read_text())
        inv=json.loads((ROOT/sid/'inventory.json').read_text())
        with base.AdaptiveHopAnalysisInputStore(captures).source(sid) as source:
            assert source.input_manifest_sha256==inv['input_manifest_sha256']
            ordinals={v.event.visit_index:i for i,v in enumerate(source.visits)}
            for row in native['visits']:
                rate=row['sample_rate_hz'];n=int(4096*rate/2500000)
                result=dict(session_id=sid,visit=row['visit'],sample_rate_hz=rate,block_samples=n,
                            block_duration_ms=n/rate*1000,native_state=row['state'])
                # Reuse identical 2.5 MS/s calculations rather than repeat them.
                if rate==2500000:
                    result['state']=row['state']
                    if row['state']=='replayed':
                        result.update(held=row['held_band_phase'],all_phase=row['all_band_phase'],
                                      curve_fits=row['curve_fits'],supported=row['production_relative_phase']['supported'],
                                      model=row['broadband']['model'])
                    else:
                        result['reason']=row['reason']
                    results.append(result)
                    continue
                try:
                    iq=source.read_visit(ordinals[row['visit']])
                    assert hashlib.sha256(iq.tobytes()).hexdigest()==row['iq_sha256']
                    contracts={1:AdaptiveHopVisitAnalysisV1,2:DualRx10mAdaptiveHopVisitAnalysisV2,
                               3:Feature103VisitAnalysisV3,4:Feature104VisitAnalysisV4}
                    dense=contracts[row['dense_glrt']['schema_version']].model_validate(row['dense_glrt'])
                    probes=base.relative_phase_probes(dense)
                    train=[p for p in probes if p.start_sample+rate*20//1000<=len(iq)//2]
                    if not train:
                        raise ValueError('No training-half paired pilot frequency evidence')
                    seed=float(np.median([p.seeds[1].acquired_cfo_hz-p.seeds[0].acquired_cfo_hz for p in train]))
                    m=base.estimate_broadband_alignment(iq,rate,receiver_cfo_seed_hz=seed,
                         cfo_search_half_width_hz=900000,block_samples=n).model
                    frequency=np.fft.fftshift(np.fft.fftfreq(n,1/rate));window=np.hanning(n)
                    left=[];right=[]
                    for start in range(0,len(iq)//2-n+1,n):
                        dt=(np.arange(start,start+n)-m.reference_sample)/rate
                        rotation=np.exp(-2j*np.pi*(m.relative_cfo_hz*dt+.5*m.relative_cfo_rate_hz_s*dt**2))
                        left.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,0]*window)))
                        right.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,1]*rotation*window)))
                    eligible=abs(frequency)<rate/2-40000
                    for sample in (0,len(iq)-1):
                        eligible &= abs(frequency+m.relative_cfo_hz+m.relative_cfo_rate_hz_s*(sample-m.reference_sample)/rate)<rate/2-40000
                    ids,h=base.normalize_response(np.array(left),np.array(right),frequency,
                        np.searchsorted(frequency,m.frequency_hz),m.channel_transfer,eligible)
                    model=dataclasses.replace(m,frequency_hz=tuple(frequency[ids]),channel_transfer=tuple(h))
                    held=base.frequency_held_out_tracking(iq,rate,model,block_samples=n)
                    full=base.frequency_held_out_tracking(iq,rate,model,block_samples=n,training_fraction=0)
                    errors=np.array([p['held_band_residual_phase_rad'] for p in held['rows']])
                    supported=held['tracked']['coherence']>max(.05,3*held['wrong_time']['coherence']) and abs(np.mean(np.exp(1j*errors)))>.8
                    tt=np.array([p['center_sample']/rate for p in full['rows']])
                    best,curves,cv,sigma=base.curve.select_fit(tt,np.array([p['training_band_phase_rad'] for p in full['rows']]))
                    ht=np.array([p['center_sample']/rate for p in held['rows']])
                    hp=np.array([p['training_band_phase_rad']+p['held_band_residual_phase_rad'] for p in held['rows']])
                    validation={}
                    for name,curve in curves.items():
                        residual=base.wrap(hp-np.interp(ht,tt,curve))
                        validation[name]=dict(B_rms_deg=float(np.degrees(np.sqrt(np.mean(residual**2)))),B_resultant=float(abs(np.mean(np.exp(1j*residual)))))
                    result.update(state='replayed',supported=bool(supported),model=base.serial(m),held=held,all_phase=full,
                         curve_fits=dict(selected=best,time_s=tt,curves_rad=curves,A_cv_rms_deg={k:float(np.degrees(v)) for k,v in cv.items()},B_validation=validation))
                    print(sid,row['visit'],'matched',bool(supported),round(held['tracked']['coherence'],4),flush=True)
                except Exception as exc:
                    result.update(state='abstained',reason=f'{type(exc).__name__}: {exc}')
                    print(sid,row['visit'],result['reason'],flush=True)
                results.append(result)
                base.save(ROOT/'matched-duration.json',dict(elapsed_s=time.monotonic()-started,rows=results))
    captures.close()
    base.save(ROOT/'matched-duration.json',dict(elapsed_s=time.monotonic()-started,rows=results))


if __name__=='__main__':
    run()
