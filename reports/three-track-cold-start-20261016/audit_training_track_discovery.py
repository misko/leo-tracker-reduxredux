import json
from pathlib import Path
import numpy as np
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
source=load_input(json.loads(Path('/srv/bulk/leo/fast-scan-tracking-inputs/fast-9571943d3dccdf4f327e1346d1bf34b8.json').read_text()))
winners={}
for p in project_scanner_candidates(source):
    old=winners.get(p.source_group_id)
    if old is None or (-p.margin,p.candidate_rank,p.candidate_id)<(-old.margin,old.candidate_rank,old.candidate_id):winners[p.source_group_id]=p
points=sorted(winners.values(),key=lambda p:(p.support_center_utc_ns,p.source_group_id));out=[]
point_lookup={p.candidate_id:p for p in points}
def track_ids(track):return {point_lookup[p.candidate_id].source_group_id for p in track.points}
def track_span(track):return (max(point_lookup[p.candidate_id].support_center_utc_ns for p in track.points)-min(point_lookup[p.candidate_id].support_center_utc_ns for p in track.points))/1e9
for fold in ['early_to_late','late_to_early']:
    root=Path('/tmp/three-track-investigation/cold-fold-'+fold+'-v1');derivation=json.loads((root/'derivation.json').read_text())
    prepared,_=prepare_views(load_input(json.loads((root/'training-input.json').read_text())))
    all_ids=set(prepared['all'].observations.window_ids)
    raw=reconstruct_persistent_hop_trajectories(tuple(p for p in points if p.source_group_id in all_ids and p.margin>0),config=PersistentHopTrajectoryConfig())
    eligible=[t for t in raw.tracklets if len(t.points)>=15 and track_span(t)>=15]
    for target in derivation['targets']:
        ids={points[i].source_group_id for i in target['training_rows']}
        record=dict(fold=fold,track=target['track'],training_count=len(ids),views=[])
        raw_ranked=sorted(raw.tracklets,key=lambda t:len(track_ids(t)&ids),reverse=True)
        best_raw=raw_ranked[0];raw_overlap=len(track_ids(best_raw)&ids)
        raw_span=track_span(best_raw)
        receiver=best_raw.lane_key[2]
        receiver_ranked=sorted([t for t in eligible if t.lane_key[2]==receiver],key=lambda t:-track_span(t))
        identity=track_ids(best_raw)
        receiver_rank=next((i+1 for i,t in enumerate(receiver_ranked) if track_ids(t)==identity),None)
        record.update(raw_track_overlap=raw_overlap,raw_track_size=len(best_raw.points),raw_track_span_s=raw_span,passes_15point_15second_filter=len(best_raw.points)>=15 and raw_span>=15,all_view_receiver_span_rank=receiver_rank)
        for view in ['all','low']:
            item=prepared[view];obs=item.observations;rows=np.array([i for i,k in enumerate(obs.window_ids) if k in ids]);assert len(rows)==len(ids)
            values=np.unwrap(obs.measured_hz[rows]*2*np.pi/(1/4.4e-6))*(1/4.4e-6)/(2*np.pi);time=obs.times_s[rows]
            rr=values-np.polyval(np.polyfit(time-time.mean(),values,2),time-time.mean())
            member=set().union(*(set(t) for t in item.bootstrap_tracks));ranked=sorted([(len(set(t)&set(rows)),t) for t in item.bootstrap_tracks],key=lambda r:r[0],reverse=True)
            record['views'].append(dict(view=view,training_span_s=float(np.ptp(time)),raw_quadratic_rms_hz=float(np.sqrt(np.mean(rr**2))),points_in_any_bootstrap_track=sum(int(i in member) for i in rows),best_bootstrap_track_overlap=ranked[0][0] if ranked else 0,best_bootstrap_track_size=len(ranked[0][1]) if ranked else 0,best_bootstrap_track_span_s=float(np.ptp(obs.times_s[list(ranked[0][1])])) if ranked else 0))
        out.append(record)
destination=Path('/tmp/three-track-investigation/training_track_discovery_audit.json');destination.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
