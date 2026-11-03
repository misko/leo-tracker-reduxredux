"""Sealed stratified real-IQ comparison of reference and continuous pilot fits."""

import argparse
import json
import random
import time
from pathlib import Path
import numpy as np
from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import PilotWorkspace, pilot_wave
from probe_ds23_raw_pilot_refinement import OUT as RAW
from refine_ds23_receiver_panel import OUT as DENSE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_19_ds23_fast_pilot_estimator'
PANELS=[RAW/'DS23-0202_tracks_panel.npz', RAW/'DS23-0274_tracks_panel.npz', DENSE/'DS23-0202_panel.npz']


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    pool={}
    for path in PANELS:
        z=np.load(path,allow_pickle=False);meta=json.loads(str(z['metadata_json']))
        ownership={oid:(t['receiver'],int(t['channel']>4)) for t in meta['tracks'] for oid in t['observation_ids']}
        for p in meta['points']:
            oid=p['observation_id'];rx,band=ownership[oid]
            # Earlier per-curve panels take precedence over a duplicate RX2 window.
            if oid not in pool:
                pool[oid]=dict(case=meta['case'],receiver=rx,band=band,panel=str(path.relative_to(ROOT)),point=p)
    selected=[];rng=random.Random(2026101903)
    for case in ('DS23-0202','DS23-0274'):
        for rx in (1,2):
            for band in (0,1):
                group=sorted([r for r in pool.values() if (r['case'],r['receiver'],r['band'])==(case,rx,band)],key=lambda r:r['point']['observation_id'])
                if len(group)<12:raise ValueError('each frozen RX/band stratum needs twelve real probes')
                selected+=rng.sample(group,12)
    assert len(selected)==len({r['point']['observation_id'] for r in selected})==96
    plan=dict(selected=selected,seed=2026101903,points_per_case_RX_band=12,
        panel_sha256={str(p.relative_to(ROOT)):sha(p) for p in PANELS},source_sha256=sha(Path(__file__)),
        no_GPS_or_satellite_selection=True,no_new_RF_or_recording_read=True,
        physical_bounds=dict(frequency_radius_hz=800,epoch_samples=.75,code_rate_ppm=40),
        common_frequency_scout_hz=[-600,600,100],point_order_preserved=True)
    path=OUT/'plan.json'
    if path.exists() and read(path)!=plan:raise ValueError('refusing to change sealed benchmark sample')
    write(path,plan)
    print('Sealed96 points across eight case/RX/band strata',flush=True)


def reference(samples,fs,edge,epoch,center):
    p=PilotWorkspace(samples,fs,edge,epoch)
    frequencies=center+np.arange(-600,601,100)
    f=float(frequencies[int(np.argmax(p.evaluate(frequencies)))])
    return p.joint_fit(f)


def run():
    plan=read(OUT/'plan.json')
    assert plan['source_sha256']==sha(Path(__file__))
    panels={p:np.load(ROOT/p,allow_pickle=False) for p in plan['panel_sha256']}
    assert all(sha(ROOT/p)==digest for p,digest in plan['panel_sha256'].items())
    metadata={p:json.loads(str(z['metadata_json'])) for p,z in panels.items()}
    for meta in metadata.values():
        for edge in ('lower','upper'):pilot_wave(meta['sample_rate_hz'],edge)
    rows=[];started=time.monotonic()
    for number,entry in enumerate(plan['selected']):
        point,panel=entry['point'],panels[entry['panel']]
        values=panel[point['window_key']][:,point['receiver_offset']]
        samples=values[:,0].astype(float)+1j*values[:,1].astype(float)
        fs=metadata[entry['panel']]['sample_rate_hz'];peak=point['peak']
        center=peak['fractional_tracking_cfo_hz'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
        results={}
        for method in (('reference','continuous') if number%2==0 else ('continuous','reference')):
            before=time.perf_counter()
            result=(reference(samples,fs,point['edge'],epoch,center) if method=='reference'
                else FastPilotWorkspace(samples,fs,point['edge'],epoch).fast_joint_fit(center))
            results[method]=dict(result=result,seconds=time.perf_counter()-before)
        rows.append(dict(entry=entry,results=results,archived_CFO_hz=center,
            CFO_difference_hz=results['continuous']['result']['CFO_hz']-results['reference']['result']['CFO_hz'],
            score_difference=results['continuous']['result']['score']-results['reference']['result']['score']))
        if len(rows)%12==0:
            write(OUT/'benchmark_partial.json',dict(rows=rows))
            print('Fitted',len(rows),'of96; seconds',round(time.monotonic()-started,1),flush=True)
    write(OUT/'benchmark.json',dict(rows=rows,seconds=time.monotonic()-started,source_sha256=sha(Path(__file__)),
        continuous_source_sha256=sha(ROOT/'tools/fast_local_pilot_refinement.py'),
        reference_source_sha256=sha(ROOT/'tools/local_pilot_refinement.py'),plan_sha256=sha(OUT/'plan.json'),
        identical_samples_template_likelihood_and_parameter_count=True,
        both_use_same_nominal_frequency_scout=True,core_fitter_only_not_full_pipeline=True,
        templates_warmed_before_timing=True,method_order_alternates=True,
        no_GPS_TLE_or_polynomial_input_to_either_fit=True))
    print('Core seconds reference/continuous',[sum(r['results'][m]['seconds'] for r in rows) for m in ('reference','continuous')],flush=True)
    print('Minimum continuous score difference',min(r['score_difference'] for r in rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','fit'],required=True)
    prepare() if parser.parse_args().stage=='prepare' else run()
