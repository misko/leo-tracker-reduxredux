"""Replay the sealed 96-probe benchmark with fractional frame placement."""

from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json
import time

import numpy as np

from decoupled_pilot_clocks import ContinuousCoupledWorkspace,isolated_pilot_wave
from ds23_joint_frame_phase import phase_line
from fast_local_pilot_refinement import FastPilotWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_ds23_fast_pilot_estimator/benchmark.json'
OUT=ROOT/'reports/2026_10_19_algo03_fractional_pilot_benchmark'


def phase_summary(work,fit):
    d=work.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],details=True)
    times=np.array([work.t[ix].mean() for ix in work.frames]);gains=d['coefficients'][:,0]
    weights=d['energies'][:,0]*abs(gains)**2
    return phase_line(times,gains,weights)


def main():
    if OUT.exists():
        raise FileExistsError('preserve same-sample benchmark')
    OUT.mkdir();document=read(SOURCE);names=sorted({r['entry']['panel'] for r in document['rows']})
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),benchmark_sha256=sha(SOURCE),
        helper_sha256=sha(ROOT/'tools/decoupled_pilot_clocks.py'),
        sample_panel_sha256={p:sha(ROOT/p) for p in names},same_samples_and_parameter_count=True,
        no_GPS_TLE_satellite_polynomial_or_position_used=True,workers=8,
        only_fractional_frame_template_placement_changes=True))
    panels={p:np.load(ROOT/p,allow_pickle=False) for p in names}
    for edge in ('lower','upper'):
        isolated_pilot_wave(2500000,edge);isolated_pilot_wave(2500000,edge,True)
    def one(index,row):
        e=row['entry'];point=e['point'];panel=panels[e['panel']]
        fs=json.loads(str(panel['metadata_json']))['sample_rate_hz']
        values=panel[point['window_key']][:,point['receiver_offset']]
        y=values[:,0].astype(float)+1j*values[:,1]
        epoch=point['peak']['integer_epoch_sample']+point['peak']['fractional_epoch_offset_samples']
        previous=row['results']['continuous']['result'];old=FastPilotWorkspace(y,fs,point['edge'],epoch)
        replay=float(old.evaluate([previous['CFO_hz']],previous['offset_samples'],previous['modulation_ppm'])[0])
        if abs(replay-previous['score'])>1e-10:
            raise ValueError('same-IQ legacy likelihood replay failed')
        work=ContinuousCoupledWorkspace(y,fs,point['edge'],epoch)
        begin=time.monotonic();fit=work.fast_joint_fit(point['peak']['fractional_tracking_cfo_hz'])
        seconds=time.monotonic()-begin
        return dict(index=index,entry=e,legacy_fit=previous,fractional_fit=fit,
            CFO_change_hz=fit['CFO_hz']-previous['CFO_hz'],score_ratio=fit['score']/previous['score'],
            legacy_phase=phase_summary(old,previous),fractional_phase=phase_summary(work,fit),
            seconds=seconds,legacy_likelihood_replay_difference=replay-previous['score'])
    rows=[];started=time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for future in as_completed([executor.submit(one,k,row) for k,row in enumerate(document['rows'])]):
                r=future.result();rows.append(r)
                if len(rows)%24==0:print('completed',len(rows),flush=True)
        write(OUT/'results.json',dict(rows=sorted(rows,key=lambda r:r['index']),seconds=time.monotonic()-started,
            protocol_sha256=sha(OUT/'protocol.json'),no_position_or_calibration_updated=True,
            no_claim_that_RF_score_gain_improves_localization=True))
    finally:
        for p in panels.values():p.close()


if __name__=='__main__':main()
