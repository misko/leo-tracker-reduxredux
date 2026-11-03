"""Source-specific calibration views from historical public products."""
from collections import defaultdict
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp
from doppler_pilot import fast,read,digest,HERE,HILL
sys.path.insert(0,str(HERE.parents[2]))
from tools.rx_paired_opportunities import export_input,projected_candidates
from tools.ds7_export_baseline import partition

def main(which):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets,parse_element_set_records
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    started=time.monotonic();inventory=read(HERE/'calibration-inventory.json')
    for p,h in inventory['sources'].items():assert digest(p)==h
    row=inventory['eligible'][which];entry=row['input'];index=row['index']
    planpath=HILL.parent/'2026_09_30_ds10_scale_weighting/plan.json';plan=read(planpath)
    x=np.asarray(plan['baseline']['x'])[[0,1,index+2]]
    doc=fast.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
    manifest=read(next(a['path'] for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.json')))
    npz=next(a['path'] for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.npz'))
    sources=dict(inventory['sources']);archive=TleArchiveReader(Path('/var/lib/leo/tle'));refs=archive.list_snapshots();loaded=[]
    for declared in manifest['provider_sources']:
        ref=next(r for r in refs if r.provider==declared['provider'] and r.collected_utc_ns==declared['collected_utc_ns'] and 'sha256:'+r.sha256==declared['snapshot_sha256'])
        assert ref.collected_utc_ns<doc['start_utc_ns']-505_000_000_000
        text=archive.read(ref);assert 'sha256:'+__import__('hashlib').sha256(text.encode()).hexdigest()==declared['snapshot_sha256']
        filtered,_=exclude_labelled_starlink_debris(text);records=list(parse_element_set_records(filtered));epochs=parse_element_sets(filtered).element_epoch_utc_ns()
        loaded.append((declared,records,epochs));sources[str(ref.path)]=digest(ref.path)
    original=next(records for declared,records,_ in loaded if declared['snapshot_sha256']==manifest['baseline_snapshot_sha256'])
    choices={}
    for declared,records,epochs in loaded:
        for record,epoch in zip(records,epochs,strict=True):
            key=(int(epoch),declared['collected_utc_ns'],declared['snapshot_sha256'])
            if record.satellite_number not in choices or key>choices[record.satellite_number][0]:choices[record.satellite_number]=(key,record)
    catalogue=parse_element_sets(''.join(choices[r.satellite_number][1].text for r in original))
    assert len(catalogue.satellite_numbers)==manifest['catalogue_size']
    engine=fast.Stationary(doc,plan['config']);tracks={t['track_id']:t for t in doc['tracks']};selections={};excluded=[];replay=0.
    grid=np.asarray(plan['config']['timing_grid_s']);hi=int(np.searchsorted(grid,x[2],side='right'));lo=hi-1
    assert 0<=lo<hi<len(grid);taus=grid[[lo,hi]];fraction=(x[2]-taus[0])/(taus[1]-taus[0])
    with np.load(npz,allow_pickle=False) as bank:
        for item in manifest['tracks']:
            t=tracks[item['track_id']];prediction,visible=engine.prediction(t,x)
            scores,_,audits,_=fast.profile(t['y'][None,:]-prediction,t['mask']);assert all(a['converged'] for a in audits)
            scores=np.where(visible,scores,-np.inf);post=np.exp(scores-logsumexp(scores));slot=int(np.argmax(post))
            ids=bank[f"candidate_ids_{item['index']}"]
            if post[slot]<.9:excluded.append(dict(track_id=t['track_id'],confidence=float(post[slot])));continue
            candidate=int(ids[slot]);number=int(catalogue.satellite_numbers[candidate])
            p,v,valid=propagate_candidate_states(catalogue,np.array([candidate]),doc['start_utc_ns'],np.asarray(t['times_s']),taus)
            np.testing.assert_array_equal(valid,[candidate])
            err=max(float(np.max(abs(p[0]-t['candidate_position_km'][slot,[lo,hi]]))),float(np.max(abs(v[0]-t['candidate_velocity_km_s'][slot,[lo,hi]]))))
            assert err<1e-8;replay=max(replay,err)
            selections[t['track_id']]=dict(candidate=candidate,norad=number,confidence=float(post[slot]),rf_hz=t['rf_hz'])
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:raw=store.load(entry['session_id'])
    finally:store.close()
    assert raw.input_manifest_sha256==entry['manifest_sha256'] and raw.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    projected=projected_candidates(raw)
    opportunities,_=export_input(raw,split='calibration' if which==0 else 'validation',cache_sha256='public-input:'+raw.input_manifest_sha256+':'+raw.analysis_manifest_sha256,projected=projected)
    assert all(o['opportunity_status'] in ('both_receivers_candidate_present','both_receivers_candidate_absent','one_receiver_candidate_present') for o in opportunities)
    graph=reconstruct_persistent_hop_trajectories(list(projected.values()),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    graphtracks={t.tracklet_id:t for t in graph.tracklets};candidate_views={}
    for i,o in enumerate(opportunities):
        for rx in (0,1):
            for c in o['receivers'][f'rx{rx}']['candidates']:
                if c['projected_candidate_id'] is not None:candidate_views[c['projected_candidate_id']]=(i,rx)
    owners=defaultdict(set);groups=defaultdict(list)
    for tid,selection in selections.items():
        key=(selection['norad'],selection['rf_hz']);groups[key].append(tid)
        for point in graphtracks[tid].points:owners[point.candidate_id].add(key)
    windows_time=np.array([((o['window_start_utc_ns']+o['window_end_utc_ns'])/2-doc['start_utc_ns'])/1e9 for o in opportunities])
    selected_ids=sorted({s['candidate'] for s in selections.values()})
    positions,_,valid=propagate_candidate_states(catalogue,np.array(selected_ids),doc['start_utc_ns'],windows_time,taus)
    np.testing.assert_array_equal(valid,selected_ids)
    receiver,_=fast.baseline.site(*engine.coordinates(x));lat,lon=np.radians(engine.coordinates(x))
    rotation=np.array([[-np.sin(lon),np.cos(lon),0],[-np.sin(lat)*np.cos(lon),-np.sin(lat)*np.sin(lon),np.cos(lat)],[np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]])
    lanes=[]
    for key,members in sorted(groups.items()):
        number,rf=key;indices=[i for i,o in enumerate(opportunities) if o['receivers']['rx0']['actual_rf_hz']==rf]
        bits=np.zeros((len(opportunities),2),dtype=int)
        for cid,ks in owners.items():
            if key in ks:
                i,rx=candidate_views[cid];bits[i,rx]=1 if len(ks)==1 else -1
        candidate=selections[members[0]]['candidate'];slot=selected_ids.index(candidate)
        p=positions[slot,0]*(1-fraction)+positions[slot,1]*fraction
        los=p-receiver;los/=np.linalg.norm(los,axis=-1)[:,None];enu=los@rotation.T
        lanes.append(dict(norad=number,rf_hz=rf,tracks=members,times_s=windows_time[indices].tolist(),los_enu=enu[indices].tolist(),bits=bits[indices].tolist(),
            training_mask=[partition(entry['session_id'],opportunities[i]['source_window']['visit_index']) for i in indices]))
    for p in (Path(__file__),HERE/'CALIBRATION_PROTOCOL.md',HERE/'calibration-inventory.json',planpath,HERE.parents[2]/'tools/ds7_export_baseline.py',
              Path(inspect.getfile(propagate_candidate_states)),Path(inspect.getfile(reconstruct_persistent_hop_trajectories))):sources[str(p)]=digest(p)
    result=dict(index=index,session_id=entry['session_id'],role='calibration' if which==0 else 'validation',lanes=lanes,
                inferred_labels=True,excluded_ambiguous_tracks=excluded,original_bank_replay_maximum=replay,
                fixed_geometry_x=x.tolist(),sources=sources,elapsed_s=time.monotonic()-started)
    with (HERE/f'donor-{which}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(role=result['role'],sources=len(lanes),tracks=len(selections),excluded=len(excluded),replay=replay,elapsed_s=result['elapsed_s'])))
if __name__=='__main__':main(int(sys.argv[1]))
