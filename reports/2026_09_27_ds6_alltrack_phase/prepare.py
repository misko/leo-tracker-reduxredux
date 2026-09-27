"""Prepare all-track numerical inputs and exact phase-candidate joins."""
import json,pickle,hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def main():
    sid='scan-fw-4c56320fb5ca6994';payload=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_roof_direction_subset/cache/'+sid+'.pickle').read_bytes()
    expected='13f03e1f8a8fe362ec7b500818c27bf35880aa48dbbd37691adc65da384a9d72';assert hashlib.sha256(payload).hexdigest()==expected
    raw=pickle.loads(payload)
    class Inputs:
        def load(self,session):
            assert session==sid
            return raw
    p=prepare_adaptive_tle_position_inputs(sid,inputs=Inputs(),archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    prepared=dict(tracks=p.tracks,start=p.start_utc_ns,evidence=p.evidence_sha256,snapshot=p.snapshot_digest,input=p.input_manifest_sha256)
    manifest=json.loads((ROOT/'2026_09_27_ds6_roof/manifest.json').read_text());member=next(r for r in manifest['captures'] if r['session_id']==sid)
    assert member['manifest_sha256']==prepared['input']==raw.input_manifest_sha256
    plan=json.loads((ROOT/'2026_09_27_latest_ten_phase/plan.json').read_text());scan=next(s for s in plan['scans'] if s['session_id']==sid)
    assert scan['analysis_digest']==raw.analysis_manifest_sha256
    points=project_scanner_candidates(raw);byid={p.candidate_id:p for p in points};bykey={(p.visit_index,p.receiver_id,p.probe_index,p.candidate_rank):p for p in points}
    graph=reconstruct_persistent_hop_trajectories(points,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    ids={t.track_id for t in prepared['tracks']};lookup=defaultdict(list);trackmeta={}
    for track in graph.tracklets:
        if track.tracklet_id not in ids:continue
        sources=[byid[pt.candidate_id] for pt in track.points]
        numerical=next(t for t in prepared['tracks'] if t.track_id==track.tracklet_id)
        np.testing.assert_allclose([(p.support_center_utc_ns-prepared['start'])/1e9 for p in sources],numerical.times_s,rtol=0,atol=1e-9)
        for pt,p in zip(track.points,sources):lookup[p.candidate_id].append(track.tracklet_id)
        trackmeta[track.tracklet_id]=dict(receiver_id=sources[0].receiver_id,channel=sources[0].channel,rf_hz=sources[0].actual_rf_hz,visits=[p.visit_index for p in sources],candidate_ids=[p.candidate_id for p in sources])
    assert set(trackmeta)==ids
    overrides={v['visit']:v['partition']=='train' for v in scan['selected'] if v['partition'] in ['train','held']}
    tracks=[]
    for t in prepared['tracks']:
        meta=trackmeta[t.track_id];assert len(meta['visits'])==len(t.times_s)
        train=[overrides.get(v,int(hashlib.sha256(f'ds6-alltrack-20260927:{sid}:{v}'.encode()).hexdigest()[:8],16)%10<6) for v in meta['visits']]
        tracks.append(dict(track_id=t.track_id,times_s=t.times_s.tolist(),measured_hz=t.measured_hz.tolist(),training_mask=train,**meta))
    joins=[]
    for v in scan['selected']:
        if len(v['modes'])!=2:continue
        row=dict(visit=v['visit'],group=v['group'],partition=v['partition'],modes=[])
        for mode in v['modes']:
            rx=[]
            for seed in mode['seeds']:
                key=(v['visit'],seed['receiver_id'],0,seed['rank']);point=bykey.get(key)
                assert point is not None
                rx.append(dict(receiver_id=seed['receiver_id'],candidate_id=point.candidate_id,old_track_ids=[t['track_id'] for t in mode['tracks'][seed['receiver_id']]],alltrack_ids=lookup[point.candidate_id]))
            row['modes'].append(rx)
        joins.append(row)
    common=defaultdict(list)
    for row in joins:
        left,right=[m[0]['alltrack_ids'] for m in row['modes']]
        if len(left)==len(right)==1:common[(left[0],right[0])].append(row['visit'])
    output=dict(session_id=sid,input_manifest_sha256=prepared['input'],analysis_manifest_sha256=raw.analysis_manifest_sha256,tracking_cache_sha256='sha256:'+expected,evidence_sha256=prepared['evidence'],snapshot_digest=prepared['snapshot'],start_utc_ns=prepared['start'],partition_policy='One hash-assigned partition per whole visit across all RX/tracks; existing phase training/held visits retain their frozen assignment',tracks=tracks,phase_joins=joins,recurring_rx0_pairs=[dict(track_ids=list(k),visits=v) for k,v in common.items()])
    (HERE/'inputs.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(tracks=len(tracks),observations=sum(len(t['times_s']) for t in tracks),phase_dwells=len(joins),joined_pairs=output['recurring_rx0_pairs']),indent=2))
if __name__=='__main__':main()
