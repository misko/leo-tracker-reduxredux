"""Blind production-native fractional timing under physical delay and Doppler."""

import argparse
import shutil
from pathlib import Path
import numpy as np
from probe_dynamic_pilot_timing import FS,PERIOD,geometry,periodic_sample,detrend
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.analysis.starlink.templates import qin_edge_pilot_frame,CONTROL_SYMBOL_ROLL

OUT=ROOT/'reports/2026_10_19_native_dynamic_timing'
BUILD=ROOT/'.build-short-window-native-host'


def quantize(samples):
    samples=np.asarray(samples,complex)
    scale=12000/max(float(np.max(abs(samples))),1e-20)
    result=np.empty((len(samples),1,2),dtype='<i2')
    result[:,0,0]=np.rint(samples.real*scale).astype('<i2');result[:,0,1]=np.rint(samples.imag*scale).astype('<i2')
    return result


def scene(edge,time_s):
    template=np.asarray(qin_edge_pilot_frame(FS,edge),dtype='<c16');waveform=np.zeros(10000,complex)
    for frame in range(3):
        start=round(frame*PERIOD);stop=min(start+len(template),len(waveform));waveform[start:stop]+=template[:stop-start]
    local=np.arange(FS//50)/FS;delay,rate=geometry(time_s+local)
    samples=periodic_sample(waveform,(time_s+local-delay)*FS)
    samples*=np.exp(2j*np.pi*(100000*local-11.5e9*(delay-delay[0])))
    return template,quantize(samples),float(geometry(time_s+local.mean())[0]),float(100000-11.5e9*np.mean(rate))


def run(edges,times):
    OUT.mkdir(parents=True,exist_ok=True);receipt=read(BUILD/'build-receipt.json')
    library=BUILD/'libleo-adaptive-detector.so';assert sha(library)==receipt['outputs'][library.name]
    artifacts=OUT/'native_artifacts';artifacts.mkdir(exist_ok=True)
    shutil.copyfile(library,artifacts/library.name);shutil.copyfile(BUILD/'build-receipt.json',artifacts/'build-receipt.json')
    rows=[]
    for edge in edges:
        template=np.asarray(qin_edge_pilot_frame(FS,edge),dtype='<c16')
        control=np.asarray(qin_edge_pilot_frame(FS,edge,symbol_roll=CONTROL_SYMBOL_ROLL),dtype='<c16')
        with NativeShortWindow(str(library),template,control,sample_rate_hz=FS,receiver_count=1,fractional_epoch=True) as context:
            for t in times:
                _,samples,delay,cfo=scene(edge,float(t));result=context.analyze(samples)
                candidates=[c for c in result['rows'][0]['candidates'] if c['fractional_epoch']['status']=='complete']
                winner=max(candidates,key=lambda c:c['fractional_epoch']['margin']) if candidates else None
                row=dict(edge=edge,scene_time_s=float(t),delay_s=delay,injected_midpoint_CFO_hz=cfo,
                    candidate_count=len(candidates),winner=winner)
                if winner is not None:
                    row.update(epoch_samples=winner['refined_epoch']+winner['fractional_epoch']['offset_samples'],
                        measured_CFO_hz=winner['fractional_epoch']['tracking_cfo_hz'])
                rows.append(row);write(OUT/'partial.json',dict(rows=rows,source_sha256=sha(Path(__file__))))
                print(edge,t,'detected',winner is not None,'CFO error',None if winner is None else round(row['measured_CFO_hz']-cfo,3),flush=True)
    summaries=[]
    for edge in edges:
        local=[r for r in rows if r['edge']==edge and r['winner'] is not None]
        if len(local)!=len(times) or len(times)<3:continue
        t=np.array([r['scene_time_s'] for r in local]);epoch=np.array([r['epoch_samples'] for r in local])
        unwrapped=np.unwrap(epoch*2*np.pi/PERIOD)*PERIOD/(2*np.pi)
        observed=detrend(t,unwrapped);expected=detrend(t,np.array([r['delay_s'] for r in local])*FS)
        summaries.append(dict(edge=edge,times_s=t,observed_detrended_samples=observed,expected_detrended_samples=expected,
            delay_curvature_gain=float(observed@expected/(expected@expected)),
            positive_RMS_samples=float(np.sqrt(np.mean((observed-expected)**2))),
            negative_RMS_samples=float(np.sqrt(np.mean((observed+expected)**2))),
            CFO_error_RMS_hz=float(np.sqrt(np.mean([(r['measured_CFO_hz']-r['injected_midpoint_CFO_hz'])**2 for r in local])))))
    write(OUT/'result.json',dict(rows=rows,summaries=summaries,source_sha256=sha(Path(__file__)),
        library_sha256=sha(library),build_receipt_sha256=sha(BUILD/'build-receipt.json'),
        native_binding_sha256=sha(ROOT/'src/leo/analysis/starlink/native_short_window.py'),
        template_sha256=sha(ROOT/'src/leo/analysis/starlink/templates.py'),
        waveform_source_sha256=sha(ROOT/'tools/probe_dynamic_pilot_timing.py'),
        blind_native_CFO_and_epoch_search=True,truth_seeded_search=False,
        waveform='noiseless pilot-only three-frame periodic approximation, linear interpolation, CI16 quantization',
        native_binary_is_receipt_verified_but_capture_binary_identity_is_not_proven=True,
        no_recorded_IQ_TLE_or_GPS_input=True))
    print('timing summaries',[{k:v for k,v in s.items() if not isinstance(v,np.ndarray)} for s in summaries],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--edges',nargs='+',default=['lower','upper'])
    parser.add_argument('--times',nargs='+',type=float,default=list(np.arange(-120,121,20)))
    args=parser.parse_args();run(args.edges,args.times)
