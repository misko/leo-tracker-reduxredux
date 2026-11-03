"""Bounded shared-transmitter-phase screen on previously selected saved IQ."""

from pathlib import Path
import time

import numpy as np

from ds23_joint_frame_phase import paired_phase
from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import pilot_wave
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE=ROOT/'reports/2026_10_19_algo03_cross_receiver_carrier'
OUT=ROOT/'reports/2026_10_19_algo03_joint_frame_phase'


def frame_gains(samples,fs,edge,epoch,fit):
    workspace=FastPilotWorkspace(samples,fs,edge,epoch)
    d=workspace.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],details=True)
    gain=d['coefficients'][:,0];energy=d['energies'][:,0]
    y=np.asarray(samples);noise=[]
    for k,index in enumerate(workspace.frames):
        raw=np.vdot(y[index]-y[index].mean(),y[index]-y[index].mean()).real
        noise.append(max(float(raw-abs(gain[k])**2*energy[k]),1.)/len(index))
    variance=np.asarray(noise)/energy
    snr=np.maximum(abs(gain)**2/variance-1.,.01)
    times=np.array([workspace.t[index].mean() for index in workspace.frames])
    return dict(times=times,gains=gain,snr=snr,fit=fit)


def main():
    if OUT.exists():
        raise FileExistsError('preserve phase qualification')
    OUT.mkdir();protocol=read(SOURCE/'protocol.json');old=read(SOURCE/'results.json')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_joint_frame_phase.py'),
        original_RF_selection_sha256=sha(SOURCE/'protocol.json'),
        original_within_frame_fit_sha256=sha(SOURCE/'results.json'),
        panel_sha256=protocol['panel_sha256'],
        no_GPS_TLE_satellite_ID_or_position_used=True,
        no_new_measurements_added_and_no_calibration_updated=True,
        controls=['permuted receiver frame-phase sequence',
                  'one-frame shift in same receiver window',
                  'different saved window at same RF',
                  'different native frame epoch in same IQ window'],
        thresholds=dict(paired_coherence=.9,maximum_individual_coherence=.8,
            minimum_effective_frames=8,permutation_tail=.01),
        frequency_ambiguity_750Hz_unresolved_and_no_covariance_claim=True))
    panels={}
    for path,digest in protocol['panel_sha256'].items():
        if sha(ROOT/path)!=digest:
            raise ValueError('saved IQ changed')
        panels[path]=np.load(ROOT/path,allow_pickle=False)
    for edge in ('lower','upper'):
        pilot_wave(2_500_000,edge)
    started=time.monotonic();frames=[];results=[]
    try:
        for index,row in enumerate(old['rows']):
            e=row['entry'];fs=e['sample_rate_hz'];values=panels[e['panel']][e['window_key']]
            f=[]
            for rx in (0,1):
                y=values[:,rx,0].astype(float)+1j*values[:,rx,1]
                f.append(frame_gains(y,fs,e['edge'],e['epochs'][rx],row['fits'][rx]))
            n=min(len(d['times']) for d in f);times=(f[0]['times'][:n]+f[1]['times'][:n])/2
            actual=paired_phase(times,f[0]['gains'][:n],f[1]['gains'][:n],f[0]['snr'][:n],f[1]['snr'][:n],seed=51432+index)
            delta=row['fits'][1]['CFO_hz']-row['fits'][0]['CFO_hz']
            actual['differential_CFO_mod750_candidate_hz']=delta+actual['frequency_correction_mod750_hz']
            shifted=paired_phase(times[:-1],f[0]['gains'][:n-1],f[1]['gains'][1:n],
                f[0]['snr'][:n-1],f[1]['snr'][1:n],seed=51532+index)
            document=read(ROOT/'reports/2026_10_19_algo02_ds23_full'/e['case']/'tracking.json')
            source=document.get('source',document)
            probe=next(p for p in source['probes'] if p['visit_index']==e['visit_index'] and p['receiver_id']==1)
            period=fs/750
            alternatives=[p for p in probe['candidates'] if p['passed_fractional_margin_gate'] and
                abs((p['integer_epoch_sample']+p['fractional_epoch_offset_samples']-e['epochs'][0]+period/2)%period-period/2)>10]
            unmatched=None
            if alternatives:
                peak=max(alternatives,key=lambda p:p['fractional_margin'])
                epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
                y=values[:,1,0].astype(float)+1j*values[:,1,1]
                ws=FastPilotWorkspace(y,fs,e['edge'],epoch)
                fit=ws.fast_joint_fit(peak['fractional_tracking_cfo_hz'])
                alt=frame_gains(y,fs,e['edge'],epoch,fit);nn=min(n,len(alt['times']))
                unmatched=paired_phase((f[0]['times'][:nn]+alt['times'][:nn])/2,
                    f[0]['gains'][:nn],alt['gains'][:nn],f[0]['snr'][:nn],alt['snr'][:nn],seed=51632+index)
            frames.append(f);results.append(dict(entry=e,actual=actual,next_frame_control=shifted,
                unmatched_epoch_control=unmatched,within_frame_fits=row['fits']))
            print(index,e['case'],e['channel'],'phase coherence',round(actual['coherence'],4),
                'individual',[round(v['coherence'],4) for v in actual['individual']],
                'candidate',actual['shared_nonlinear_phase_candidate'],flush=True)
        for k,row in enumerate(results):
            controls=[];e=row['entry']
            for j,other in enumerate(results):
                o=other['entry']
                if j==k or (e['case'],e['rf_hz'])!=(o['case'],o['rf_hz']):
                    continue
                a,b=frames[k][0],frames[j][1];n=min(len(a['times']),len(b['times']))
                controls.append(dict(other_index=j,result=paired_phase((a['times'][:n]+b['times'][:n])/2,
                    a['gains'][:n],b['gains'][:n],a['snr'][:n],b['snr'][:n],seed=51732+k*10+j)))
            row['different_window_controls']=controls
        write(OUT/'results.json',dict(rows=results,seconds=time.monotonic()-started,
            protocol_sha256=sha(OUT/'protocol.json'),
            no_GPS_TLE_satellite_ID_position_or_calibration_updated=True,
            no_750Hz_ambiguity_resolution_or_calibrated_joint_covariance=True))
    finally:
        for panel in panels.values():
            panel.close()


if __name__=='__main__':
    main()
