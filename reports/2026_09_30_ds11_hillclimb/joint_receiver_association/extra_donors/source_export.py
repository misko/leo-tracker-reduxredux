"""Receiver/source observations at frozen location and qualified donor timing."""
from collections import defaultdict
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp
from context import load,fast,read,digest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE.parent/'acquisition_calibration'))
from bit_ownership import source_bits
from tools.rx_paired_opportunities import projected_candidates,export_input
from tools.ds7_export_baseline import partition


def main(index):
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets,parse_element_set_records
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    started=time.monotonic();doc,config,xy,capture,entry,sources=load(index)
    tp=HERE/f'timing-{index:02d}.json';timing=read(tp)
    for p,h in timing['sources'].items():assert digest(p)==h,p
    assert timing['selected'] is not None and timing['selected']['qualified']
    x=np.array(timing['selected']['x']);np.testing.assert_array_equal(x[:2],xy)
    sources[str(tp)]=digest(tp)
    folder=HERE/f'numeric-{index:02d}'
    manifest=read(folder/'banks/manifest.json');archive=TleArchiveReader(Path('/var/lib/leo/tle'));refs=archive.list_snapshots()
    choices={};roster=None
    for declared in manifest['provider_sources']:
        matches=[r for r in refs if r.provider==declared['provider'] and r.collected_utc_ns==declared['collected_utc_ns'] and r.digest==declared['snapshot_sha256']]
        assert len(matches)==1;ref=matches[0];sources[str(ref.path)]=digest(ref.path)
        text,_=exclude_labelled_starlink_debris(archive.read(ref));records=list(parse_element_set_records(text));epochs=parse_element_sets(text).element_epoch_utc_ns()
        if ref.digest==manifest['baseline_snapshot_sha256']:roster=records
        for record,epoch in zip(records,epochs,strict=True):
            key=(int(epoch),ref.collected_utc_ns,ref.digest)
            if record.satellite_number not in choices or key>choices[record.satellite_number][0]:choices[record.satellite_number]=(key,record)
    assert roster is not None
    catalogue=parse_element_sets(''.join(choices[r.satellite_number][1].text for r in roster))
    assert len(catalogue.satellite_numbers)==manifest['catalogue_size']
    engine=fast.Stationary(doc,config);tracks={t['track_id']:t for t in doc['tracks']}
    metadata={r['track_id']:r for r in manifest['tracks']}
    grid=np.array(config['timing_grid_s']);hi=int(np.searchsorted(grid,x[2],side='right'));lo=hi-1
    assert 0<=lo<hi<len(grid)
    taus=grid[[lo,hi]];fraction=(x[2]-taus[0])/(taus[1]-taus[0])
    selected={};excluded=[];maximum=0.
    with np.load(folder/'banks/banks.npz',allow_pickle=False) as bank:
        for tid,t in tracks.items():
            prediction,visible=engine.prediction(t,x);scores,_,audits,_=fast.profile(t['y'][None]-prediction,t['mask'])
            assert all(a['converged'] for a in audits)
            scores=np.where(visible,scores,-np.inf);posterior=np.exp(scores-logsumexp(scores));slot=int(np.argmax(posterior))
            if posterior[slot]<.9:excluded.append(dict(track_id=tid,confidence=float(posterior[slot]),reason='ambiguous_identity'));continue
            candidate=int(bank[f"candidate_ids_{metadata[tid]['index']}"][slot])
            p,v,valid=propagate_candidate_states(catalogue,np.array([candidate]),doc['start_utc_ns'],np.array(t['times_s']),taus)
            np.testing.assert_array_equal(valid,[candidate])
            error=max(float(np.max(abs(p[0]-t['candidate_position_km'][slot,[lo,hi]]))),float(np.max(abs(v[0]-t['candidate_velocity_km_s'][slot,[lo,hi]]))))
            assert error<1e-8;maximum=max(maximum,error)
            selected[tid]=dict(candidate=candidate,norad=int(catalogue.satellite_numbers[candidate]),confidence=float(posterior[slot]),rf_hz=t['rf_hz'])
    assert selected,'No training-supported source identities'
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:raw=store.load(entry['session_id'])
    finally:store.close()
    assert raw.qualified and raw.timing.qualified and raw.input_manifest_sha256==entry['manifest_sha256'] and raw.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    projected=projected_candidates(raw);by_id={p.candidate_id:p for p in projected.values()}
    opportunities,_=export_input(raw,split='validation',cache_sha256='public-input:'+raw.input_manifest_sha256+':'+raw.analysis_manifest_sha256,projected=projected)
    graph=reconstruct_persistent_hop_trajectories(list(projected.values()),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    graphtracks={t.tracklet_id:t for t in graph.tracklets};views={}
    for i,o in enumerate(opportunities):
        for rx in (0,1):
            for c in o['receivers'][f'rx{rx}']['candidates']:
                cid=c['projected_candidate_id']
                if cid is not None:assert cid not in views;views[cid]=(i,rx)
    owners=defaultdict(set);groups=defaultdict(list)
    for tid,s in selected.items():
        key=(s['norad'],s['rf_hz']);groups[key].append(tid);points=graphtracks[tid].points;t=tracks[tid]
        assert len(points)==len(t['times_s'])
        for j,p in enumerate(points):
            c=by_id[p.candidate_id]
            assert abs((c.support_center_utc_ns-doc['start_utc_ns'])/1e9-t['times_s'][j])<1e-9
            assert abs(p.normalized_dealiased_cfo_hz-t['y'][j])<1e-7
            assert c.receiver_id==t['receiver_id'] and c.actual_rf_hz==t['rf_hz'] and c.visit_index==t['visits'][j]
            owners[p.candidate_id].add(key)
    times=np.array([((o['window_start_utc_ns']-doc['start_utc_ns'])+(o['window_end_utc_ns']-doc['start_utc_ns']))/2e9 for o in opportunities])
    ids=sorted({s['candidate'] for s in selected.values()})
    positions,_,valid=propagate_candidate_states(catalogue,np.array(ids),doc['start_utc_ns'],times,taus)
    np.testing.assert_array_equal(valid,ids)
    receiver,_=fast.baseline.site(*engine.coordinates(x));lat,lon=np.radians(engine.coordinates(x))
    rotation=np.array([[-np.sin(lon),np.cos(lon),0],[-np.sin(lat)*np.cos(lon),-np.sin(lat)*np.sin(lon),np.cos(lat)],[np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]])
    lanes=[]
    for key,members in sorted(groups.items()):
        norad,rf=key;indices=[i for i,o in enumerate(opportunities) if o['receivers']['rx0']['actual_rf_hz']==rf]
        bits=source_bits(key,owners,views,len(opportunities));slot=ids.index(selected[members[0]]['candidate'])
        pos=positions[slot,0]*(1-fraction)+positions[slot,1]*fraction;los=pos-receiver;los/=np.linalg.norm(los,axis=-1)[:,None]
        lanes.append(dict(norad=norad,rf_hz=rf,tracks=members,times_s=times[indices].tolist(),los_enu=(los@rotation.T)[indices].tolist(),bits=bits[indices].tolist(),training_mask=[partition(entry['session_id'],opportunities[i]['source_window']['visit_index']) for i in indices]))
    paths=[Path(__file__),HERE/'TRANSFER_PROTOCOL.md',ROOT/'tools/rx_paired_opportunities.py',ROOT/'tools/ds7_export_baseline.py',HERE.parent/'acquisition_calibration/bit_ownership.py']
    paths += [Path(inspect.getfile(f)) for f in (propagate_candidate_states,ScannerTrackingInputStore,reconstruct_persistent_hop_trajectories,parse_element_sets)]
    sources.update({str(p):digest(p) for p in paths})
    result=dict(index=100+index,ordinal=index,family=capture['family'],role='validation',session_id=entry['session_id'],sample_rate_hz=capture['sample_rate_hz'],rf_hz=capture['rf_hz'],lanes=lanes,
                inferred_labels=True,selected_tracks=selected,excluded_tracks=excluded,original_bank_replay_maximum=maximum,fixed_geometry_x=x.tolist(),sources=sources,elapsed_s=time.monotonic()-started)
    with (HERE/f'donor-{index:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(index=index,family=capture['family'],source_groups=len(lanes),selected_tracks=len(selected),excluded_tracks=len(excluded),replay=maximum,elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
