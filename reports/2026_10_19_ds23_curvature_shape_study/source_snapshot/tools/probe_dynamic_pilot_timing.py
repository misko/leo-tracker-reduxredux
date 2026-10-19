"""Synthetic range-delay/Doppler consistency of the pinned reference estimator."""

import argparse
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT,write,sha
from leo.analysis.starlink.templates import qin_edge_pilot_frame

OUT=ROOT/'reports/2026_10_19_dynamic_pilot_timing'
PUBLISHED_COMMIT='772633600c2900af71847251a6db5a5e3c935fb1'
FS=2_500_000
PERIOD=FS/750
LIGHT_KM_S=299792.458


def periodic_sample(waveform,positions):
    integer=np.floor(positions).astype(np.int64);fraction=positions-integer
    return (1-fraction)*waveform[integer%len(waveform)]+fraction*waveform[(integer+1)%len(waveform)]


def geometry(times,height_km=550.,speed_km_s=7.5):
    times=np.asarray(times);distance=np.hypot(height_km,speed_km_s*times)
    rate=speed_km_s**2*times/distance
    return distance/LIGHT_KM_S,rate/LIGHT_KM_S


def detrend(times,values):
    x=np.column_stack((np.ones(len(times)),np.asarray(times)-np.mean(times)))
    return np.asarray(values)-x@np.linalg.lstsq(x,values,rcond=None)[0]


def pinned_reference():
    relative='src/leo/analysis/starlink/acquisition.py'
    payload=subprocess.run(['git','show',f'{PUBLISHED_COMMIT}:{relative}'],cwd=ROOT,check=True,capture_output=True).stdout
    directory=OUT/'source_reference';directory.mkdir(parents=True,exist_ok=True)
    path=directory/'acquisition.py';path.write_bytes(payload)
    template_path=ROOT/'src/leo/analysis/starlink/templates.py'
    template_payload=subprocess.run(['git','show',f'{PUBLISHED_COMMIT}:src/leo/analysis/starlink/templates.py'],cwd=ROOT,check=True,capture_output=True).stdout
    assert hashlib.sha256(template_payload).hexdigest()==sha(template_path)
    name='ds23_pinned_reference_acquisition';spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    module._native_acquisition=None
    return module


def run(edges):
    OUT.mkdir(parents=True,exist_ok=True);reference=pinned_reference();rows=[]
    scene_times=np.arange(-120.,121.,20.)
    local=np.arange(50000)/FS;mid=local.mean();rf=11.5e9;radio_cfo=100000.
    for edge in edges:
        template=np.asarray(qin_edge_pilot_frame(FS,edge),complex)
        waveform=np.zeros(10000,complex)
        for frame in range(3):
            start=round(frame*PERIOD);stop=min(start+len(template),len(waveform))
            waveform[start:stop]+=template[:stop-start]
        for t0 in scene_times:
            delay,_=geometry(t0+local);truth,rate=geometry(t0+mid)
            samples=periodic_sample(waveform,(t0+local-delay)*FS)
            samples*=np.exp(2j*np.pi*(radio_cfo*local-rf*(delay-delay[0])))
            cfo=float(radio_cfo-rf*rate)
            config=reference.SymbolwiseAcquisitionConfig(residual_cfo_min_hz=cfo-20000,
                residual_cfo_max_hz=cfo+20000,coarse_cfo_step_hz=20000,
                fine_cfo_radius_hz=1000,fine_cfo_step_hz=100,
                conditioned_cfo_radius_hz=200,conditioned_cfo_step_hz=20,
                retained_candidate_count=4,candidate_epoch_separation_samples=5,candidate_cfo_separation_hz=10000)
            result=reference.acquire_symbolwise(samples,FS,reference.ReceiverFrequencyCalibration('synthetic',0,'0'*64),edge=edge,config=config)
            winner=result.winner
            row=dict(edge=edge,scene_time_s=t0,range_delay_s=float(truth),injected_CFO_hz=cfo,
                detected=winner is not None)
            if winner is not None:
                row.update(epoch_samples=winner.refined_epoch_sample,CFO_hz=winner.absolute_cfo_hz,
                    exact_score=winner.conditioned_exact_score,control_score=winner.conditioned_control_score,
                    frame_support=winner.frame_support)
            rows.append(row)
            print(edge,t0,'detected',winner is not None,'CFO error',None if winner is None else round(winner.absolute_cfo_hz-cfo,3),flush=True)
            write(OUT/'partial.json',dict(rows=rows,source_sha256=sha(Path(__file__))))
    summaries=[]
    for edge in edges:
        selected=[r for r in rows if r['edge']==edge and r['detected']]
        if len(selected)!=len(scene_times):continue
        times=np.array([r['scene_time_s'] for r in selected]);truth=np.array([r['range_delay_s'] for r in selected])*FS
        epoch=np.array([r['epoch_samples'] for r in selected]);unwrapped=np.unwrap(epoch*2*np.pi/PERIOD)*PERIOD/(2*np.pi)
        measured=detrend(times,unwrapped);expected=detrend(times,truth)
        summaries.append(dict(edge=edge,points=len(selected),delay_curvature_gain=float(measured@expected/(expected@expected)),
            positive_delay_residual_RMS_samples=float(np.sqrt(np.mean((measured-expected)**2))),
            negative_delay_residual_RMS_samples=float(np.sqrt(np.mean((measured+expected)**2))),
            times_s=times,measured_detrended_samples=measured,physical_detrended_samples=expected))
    write(OUT/'result.json',dict(rows=rows,summaries=summaries,source_sha256=sha(Path(__file__)),
        reference_commit=PUBLISHED_COMMIT,reference_source_sha256=sha(OUT/'source_reference/acquisition.py'),
        template_source_sha256=sha(ROOT/'src/leo/analysis/starlink/templates.py'),
        estimator='published Python reference symbolwise acquisition, native acceleration disabled',
        waveform='pilot-only periodic three-frame approximation, linear fractional interpolation, noiseless',
        CFO_search_is_truth_seeded_for_measurement_semantics=True,
        not_a_production_GLRT_fractional_epoch_or_real_transmitter_clock_qualification=True,
        no_recorded_IQ_or_GPS_or_TLE_input=True))
    print('summaries',[{k:v for k,v in r.items() if not isinstance(v,np.ndarray)} for r in summaries],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--edges',nargs='+',default=['lower','upper'])
    run(parser.parse_args().edges)
