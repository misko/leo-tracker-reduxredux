"""Resolve graph observations to original candidates using public trajectory ports.

Support intervals alone are not unique: optimizer modes may share an interval.
Use the public tracklet point's normalized CFO as well, never its margin.
"""
from collections import defaultdict
import json
from prepare import HERE
from evaluate import load_inputs
from pairing import provenance_key
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories,
    persistent_hop_tracklet_graph,
)


def resolve(raw):
    candidates=project_scanner_candidates(raw)
    source={c.candidate_id:c for c in candidates}
    if len(source)!=len(candidates):
        raise ValueError('duplicate projected candidate ID')
    trajectory=reconstruct_persistent_hop_trajectories(candidates,
        config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    points=defaultdict(set)
    for track in trajectory.tracklets:
        for point in track.points:
            c=source[point.candidate_id]
            key=(track.tracklet_id,*provenance_key(c),f'rx-{c.receiver_id}',point.normalized_dealiased_cfo_hz)
            points[key].add(c.candidate_id)
    result=defaultdict(set)
    for hypothesis in trajectory.hypotheses:
        for tid in hypothesis.tracklet_ids:
            graph=persistent_hop_tracklet_graph(hypothesis,tid)
            for o in graph.observations:
                key=(tid,o.source_group_id,o.source_sample_start,o.source_sample_end,
                     o.support_center_utc_ns,o.stream_id,o.measured_cfo_hz)
                result[(tid,o.observation_id)].update(points.get(key,set()))
    return [dict(track_id=tid,observation_id=oid,candidate_ids=sorted(ids))
            for (tid,oid),ids in sorted(result.items())]


def main():
    inventory,inputs=load_inputs();result={}
    for x in inventory:
        sid=x['session_id']
        if sid not in inputs:continue
        rows=resolve(inputs[sid])
        result[sid]=dict(input_manifest_sha256=x['input_manifest_sha256'],
                         analysis_manifest_sha256=x['analysis_manifest_sha256'],rows=rows)
        (HERE/'source_links.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
        print(sid,'linked',sum(len(r['candidate_ids'])==1 for r in rows),'of',len(rows),flush=True)


if __name__=='__main__':main()
