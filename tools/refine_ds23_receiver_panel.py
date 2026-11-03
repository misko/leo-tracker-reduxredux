"""Bounded existing-IQ remeasurement of all active curved tracks on one RX."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
from investigate_algo01_ds23_0217 import problem
from local_pilot_refinement import PilotWorkspace
from probe_ds23_refined_family_catalogue import context
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,DATASET,read,write,sha

OUT=ROOT/'reports/2026_10_19_ds23_receiver_remeasurement'


def prepare(case):
    OUT.mkdir(parents=True,exist_ok=True);scan,node,keep,*_=context(case,True)
    p=problem(scan,node,'c0',keep)
    keys=[scan.tracks[i]['key'] for i,sl in zip(p.members,p.slices,strict=True) if scan.tracks[i]['receiver']==2 and keep[sl].any()]
    originals=read(SOURCE/case/'tracks.json');tracks=[t for t in originals if t['key'] in keys]
    if len(tracks)!=len(keys):raise ValueError('all nominated curves must have original graph authorities')
    count=sum(len(t['observation_ids']) for t in tracks)
    if count>1200:raise ValueError('fixed1200-point diagnostic budget exceeded')
    write(OUT/(case+'_plan.json'),dict(case=case,receiver=2,track_keys=keys,points=count,
        active_points=sum(int(keep[sl].sum()) for i,sl in zip(p.members,p.slices,strict=True) if scan.tracks[i]['receiver']==2),
        max_raw_windows=7000,max_points=1200,tracking_sha256=sha(SOURCE/case/'tracking.json'),
        tracks_sha256=sha(SOURCE/case/'tracks.json'),source_sha256=sha(Path(__file__)),
        selection='all original curves with active RX2 calibration points; all points of each curve, no GPS',
        no_new_RF_collection=True,workers=2,worker_budget_seconds=480))
    print(case,'RX2 panel',len(tracks),'curves',count,'points',flush=True)


def export(case):
    # This explicit read-side stage alone imports the concrete recording port.
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.storage.short_window import ShortWindowReader
    plan=read(OUT/(case+'_plan.json'));document=read(SOURCE/case/'tracking.json')
    assert plan['tracking_sha256']==sha(SOURCE/case/'tracking.json') and plan['tracks_sha256']==sha(SOURCE/case/'tracks.json')
    evidence,_,_=frequency_evidence(document)
    lookup={'sha256:'+hashlib.sha256(identity.encode()).hexdigest():p for identity,p in zip(evidence.ids,document['source']['probes'],strict=True)}
    tracks=[t for t in read(SOURCE/case/'tracks.json') if t['key'] in plan['track_keys']]
    required={}
    for t in tracks:
        for oid in t['observation_ids']:
            p=lookup[oid];peak=max((c for c in p['candidates'] if c['passed_fractional_margin_gate']),key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
            if p['visit_index']>=plan['max_raw_windows']:raise ValueError('visit outside fixed raw-read budget')
            required.setdefault(p['visit_index'],[]).append(dict(observation_id=oid,track_key=t['key'],
                receiver_id=p['receiver_id'],channel=p['channel'],edge=p['edge'],rf_hz=p['actual_rf_hz'],
                visit_index=p['visit_index'],sample_counter=p['valid_start_counter'],peak=peak))
    member=next(m for m in read(DATASET/'manifest.json')['members'] if m['dataset_label']==case)
    arrays={};points=[];manifests=[];visited=0
    for authority in member['raw_recording']['segments']:
        path=Path(authority['path']);assert 'sha256:'+sha(path)==authority['sha256']
        reader=ShortWindowReader(path.parent);manifests.append(dict(path=str(path),sha256=sha(path)))
        for window in reader.windows():
            visited+=1;visit=window.index.acquisition['global_visit']
            if visit in required:
                key=f'window_{visit:06d}';arrays[key]=np.array(window.samples,copy=True)
                for p in required[visit]:
                    assert window.index.acquisition['sample_start']==p['sample_counter']
                    points.append(dict(p,window_key=key,receiver_offset=reader.manifest.receiver_ids.index(p['receiver_id']),raw_window_sha256=window.index.iq_sha256))
            if len(points)==plan['points'] or visited>=plan['max_raw_windows']:break
        if len(points)==plan['points'] or visited>=plan['max_raw_windows']:break
    assert len(points)==len({p['observation_id'] for p in points})==plan['points']
    metadata=dict(case=case,tracks=tracks,points=points,sample_rate_hz=document['source']['sample_rate_hz'],
        plan_sha256=sha(OUT/(case+'_plan.json')),reader_source_sha256=sha(ROOT/'src/leo/storage/short_window.py'),
        recording_manifests=manifests,raw_windows_read=visited,all_original_selected_points_exported=True,
        read_only_existing_recording=True)
    arrays['metadata_json']=np.array(json.dumps(metadata));np.savez_compressed(sys.stdout.buffer,**arrays)


def refine(case,worker_id):
    panel=OUT/(case+'_panel.npz');z=np.load(panel,allow_pickle=False);m=json.loads(str(z['metadata_json']));fs=m['sample_rate_hz']
    started=time.monotonic();rows=[]
    for number,p in enumerate(m['points']):
        if number%2!=worker_id:continue
        v=z[p['window_key']][:,p['receiver_offset']];y=v[:,0].astype(float)+1j*v[:,1].astype(float);peak=p['peak']
        epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples'];center=peak['fractional_tracking_cfo_hz']
        workspace=PilotWorkspace(y,fs,p['edge'],epoch)
        fixed=workspace.frequency_fit(center);joint=workspace.joint_fit(fixed['CFO_hz'])
        odd=workspace.frequency_fit(center,subset='odd');even=workspace.frequency_fit(center,subset='even')
        for r in (fixed,joint,odd,even):r['effective_time_from_probe_start_s']=workspace.effective_time(r)
        rows.append(dict(point=p,archived_CFO_hz=center,fixed_epoch_CFO=fixed,joint_CFO_epoch_rate=joint,odd_frames=odd,even_frames=even))
        if len(rows)%20==0:
            write(OUT/f'{case}_worker{worker_id}_partial.json',dict(rows=rows))
            print(case,'worker',worker_id,'points',len(rows),'seconds',round(time.monotonic()-started,1),flush=True)
    write(OUT/f'{case}_worker{worker_id}.json',dict(case=case,rows=rows,seconds=time.monotonic()-started,
        source_sha256=sha(Path(__file__)),refinement_source_sha256=sha(ROOT/'tools/local_pilot_refinement.py'),
        panel_sha256=sha(panel),worker_id=worker_id,no_GPS_TLE_or_satellite_in_local_refinement=True))


def combine(case):
    z=np.load(OUT/(case+'_panel.npz'),allow_pickle=False);metadata=json.loads(str(z['metadata_json']))
    workers=[read(OUT/f'{case}_worker{k}.json') for k in range(2)];rows=[r for w in workers for r in w['rows']]
    assert len(rows)==len({r['point']['observation_id'] for r in rows})==sum(len(t['observation_ids']) for t in metadata['tracks'])
    assert all(w['panel_sha256']==sha(OUT/(case+'_panel.npz')) for w in workers)
    write(OUT/(case+'_refined.json'),dict(case=case,rows=rows,panel_metadata=metadata,
        panel_sha256=workers[0]['panel_sha256'],source_sha256=sha(Path(__file__)),
        refinement_source_sha256=sha(ROOT/'tools/local_pilot_refinement.py'),
        no_IQ_payload_for_publication=True,original_contracts_not_modified=True,
        workers_sha256=[sha(OUT/f'{case}_worker{k}.json') for k in range(2)]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--stage',choices=['prepare','export','refine','combine'],required=True)
    parser.add_argument('--worker-id',type=int,choices=[0,1]);args=parser.parse_args()
    if args.stage=='prepare':prepare(args.case)
    elif args.stage=='export':export(args.case)
    elif args.stage=='refine':refine(args.case,args.worker_id)
    else:combine(args.case)
