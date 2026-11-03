"""Bounded dual-RX frame-fingerprint proposal on existing GLRT contracts."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import bisect
import json
import time

import numpy as np

from ds23_frame_registration import circular_line, epoch_pairs, wrap
from localize_merged_track_catalogue import raw_curvature
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT / 'reports/2026_10_19_algo02_ds23_full'
OUT = ROOT / 'reports/2026_10_19_algo03_frame_registration'


def run_case(case):
    directory = SOURCE/case
    document = read(directory/'tracking.json')
    if 'source' not in document:
        return dict(case=case, available=False, reason='no_saved_dual_RX_probe_contract')
    source = document['source']; fs = 2_500_000
    anchor = document['clock_anchor']['sample_counter']
    tracks = read(directory/'tracks.json')
    curve_ids = {}
    for t in tracks:
        t['times'], t['values'] = np.asarray(t['times']), np.asarray(t['values'])
        if raw_curvature(t):
            for oid in t['observation_ids']:
                curve_ids[oid] = t['key']
    observations = read(directory/'observations.json')
    anchors = {(o['receiver']-1, round(o['time_s']*fs)): dict(
        component=curve_ids[o['observation_id']], cfo=o['measured_cfo_hz'])
        for o in observations if o['observation_id'] in curve_ids}
    probes = source['probes']
    lookup = {(p['visit_index'],p['receiver_id']):p for p in probes}
    rx1_channels = {}
    for p in probes:
        if p['receiver_id'] == 1:
            rx1_channels.setdefault(p['channel'],[]).append(p)
    for group in rx1_channels.values():
        group.sort(key=lambda p:p['valid_start_counter'])
    times_by_channel = {ch:[p['valid_start_counter'] for p in group]
                       for ch,group in rx1_channels.items()}
    rows, controls = [], []
    synchronized = 0
    for a in probes:
        if a['receiver_id'] != 0:
            continue
        b = lookup.get((a['visit_index'],1))
        if b is None or (a['channel'],a['actual_rf_hz'],a['valid_start_counter']) != (
                b['channel'],b['actual_rf_hz'],b['valid_start_counter']):
            continue
        synchronized += 1
        ta = (a['valid_start_counter']-anchor)/fs+.01
        aa = anchors.get((0,round(ta*fs)))
        bb = anchors.get((1,round(ta*fs)))
        if aa is None and bb is None:
            continue
        def choose(first, second, control=False):
            result=[]
            for pair in epoch_pairs(first['candidates'],second['candidates'],fs):
                owners=[]
                if aa is not None and abs(wrap(pair['first']['cfo']-aa['cfo']))<250:
                    owners.append(aa['component'])
                if not control and bb is not None and abs(wrap(pair['second']['cfo']-bb['cfo']))<250:
                    owners.append(bb['component'])
                if owners:
                    result.append(dict(time_s=ta,channel=a['channel'],rf_hz=a['actual_rf_hz'],
                        visit_index=a['visit_index'],curved_anchor_components=owners,**pair))
            return result
        rows += choose(a,b)
        ch = a['channel']
        control_index=bisect.bisect_left(times_by_channel[ch],a['valid_start_counter']+10*fs)
        if control_index<len(rx1_channels[ch]):
            other=rx1_channels[ch][control_index]
            if other['actual_rf_hz']==a['actual_rf_hz']:
                controls += choose(a,other,control=True)
    bands = {}
    for band in (0,1):
        group=[r for r in rows if int(r['channel']>4)==band]
        wrong=[r for r in controls if int(r['channel']>4)==band]
        if len(group)<6:
            bands[str(band)] = dict(pair_count=len(group), qualified=False, reason='fewer_than_six_pairs')
            continue
        t=np.array([r['time_s'] for r in group]);y=np.array([r['differential_cfo_hz'] for r in group])
        fitted=circular_line(t,y)
        boundary=float(np.median(t));train=t<=boundary
        prediction=circular_line(t[train],y[train]) if train.sum()>=3 else None
        temporal_test=None
        if prediction is not None:
            delta=wrap(y[~train]-prediction['offset_hz']-prediction['rate_hz_s']*(t[~train]-prediction['reference_time_s']))
            temporal_test=dict(boundary_s=boundary,training=prediction,validation_count=int((~train).sum()),
                validation_inliers=int((abs(delta)<150).sum()),validation_residual_hz=delta)
        wrong_fit=(circular_line([r['time_s'] for r in wrong],[r['differential_cfo_hz'] for r in wrong])
                   if len(wrong)>=6 else None)
        inliers=[] if fitted is None else [r for r,active in zip(group,fitted['inliers']) if active]
        per_visit={}
        for r in inliers:
            per_visit.setdefault(r['visit_index'],[]).append(r)
        multiple=sum(len(group)>=2 and abs(wrap(group[0]['first']['epoch']-group[1]['first']['epoch'],fs/750))>2
                     for group in per_visit.values())
        bands[str(band)]=dict(pair_count=len(group),fit=fitted,temporal_test=temporal_test,
            inlier_unique_visits=len(per_visit),multiple_simultaneous_epoch_visits=int(multiple),
            inlier_curve_components=sorted({c for r in inliers for c in r['curved_anchor_components']}),
            inlier_channels=sorted({r['channel'] for r in inliers}),
            wrong_window_pairs=len(wrong),wrong_window_fit=wrong_fit,
            no_calibration_qualification_claim=True)
    result=dict(case=case,available=True,bands=bands,pairs=rows,wrong_window_pairs=controls,
        synchronized_visits=synchronized,curved_observation_count=len(curve_ids),
        no_GPS_TLE_satellite_ID_or_position_used=True,linear_curves_never_calibration_anchors=True,
        no_position_or_calibration_updated=True,
        source_sha256={name:sha(directory/name) for name in ['tracking.json','tracks.json','observations.json']})
    write(OUT/(case+'.json'),result)
    return dict(case=case,available=True,pairs=len(rows),bands={key:dict(
        count=value['pair_count'],inliers=int(np.sum(value['fit']['inliers'])) if value.get('fit') else 0,
        multiple_epochs=value.get('multiple_simultaneous_epoch_visits',0),
        test=value.get('temporal_test',{}).get('validation_inliers',0) if value.get('temporal_test') else 0)
        for key,value in bands.items()})


def main():
    if OUT.exists():
        raise FileExistsError('preserve RF-only registration trial')
    OUT.mkdir()
    cases=read(ROOT/'reports/2026_10_19_algo03_catalogue72/protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,workers=30,single_thread_numerics=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_frame_registration.py'),
        frame_epoch_tolerance_samples=.2,circular_CFO_tolerance_hz=150.,maximum_relative_drift_hz_s=60.,
        eligibility='at least one matched native peak belongs to a raw actively curved GLRT track',
        calibration_not_updated=True,no_GPS_TLE_satellite_ID_or_position_used=True,
        controls='RX1 vs RX2 from 10 seconds later; temporal second-half prediction',
        require_multiple_simultaneous_distinct_epochs_before_future_calibration=True))
    started=time.monotonic();results=[]
    with ProcessPoolExecutor(max_workers=30) as executor:
        for f in as_completed([executor.submit(run_case,c) for c in cases]):
            result=f.result();results.append(result);print(json.dumps(result),flush=True)
    write(OUT/'execution.json',dict(results=results,seconds=time.monotonic()-started,
        no_position_or_calibration_updated=True))


if __name__=='__main__':
    main()
