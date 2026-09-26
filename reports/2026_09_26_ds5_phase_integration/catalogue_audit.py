"""Join phase seed candidates to the exact production TLE-input track configuration."""
from pathlib import Path
from collections import defaultdict
import json,hashlib
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader

HERE=Path(__file__).resolve().parent
PREVIOUS=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_26_ds5_probabilistic/results.json')

def main():
    plan=json.loads((HERE/'plan.json').read_text());old={r['session_id']:r for r in json.loads(PREVIOUS.read_text())['scans']}
    scans=[];store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        for scan in plan['scans']:
            sid=scan['session_id'];source=store.load(sid)
            prepared=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
            assert prepared.evidence_sha256==old[sid]['evidence_sha256']
            assert prepared.snapshot_digest==old[sid]['snapshot_digest']
            candidates=project_scanner_candidates(source);byid={c.candidate_id:c for c in candidates}
            graph=reconstruct_persistent_hop_trajectories(candidates,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
            tids={t.track_id for t in prepared.tracks};membership=defaultdict(list)
            probes={(q.visit_index,q.receiver_id):q for q in source.probes if q.probe_index==0}
            for track in graph.tracklets:
                if track.tracklet_id not in tids:continue
                for point in track.points:
                    c=byid[point.candidate_id];membership[c.visit_index,c.receiver_id,c.candidate_rank].append(track.tracklet_id)
            visits=[];groups=defaultdict(list)
            for v in scan['selected']:
                modes=[]
                for mode in v['modes']:
                    matches=[membership[v['visit'],rx,r['candidate_rank']] for rx,r in enumerate(mode['seeds'])]
                    equivalents=[]
                    for rx,seed in enumerate(mode['seeds']):
                        supported=set(matches[rx]);evidence=[]
                        for c in probes[v['visit'],rx].candidates:
                            if not c.passed_fractional_margin_gate:continue
                            epoch_error=(c.integer_epoch_sample+c.fractional_epoch_offset_samples-seed['integer_epoch_sample']-seed['fractional_epoch_offset_samples']+source.sample_rate_hz/1500)%(source.sample_rate_hz/750)-source.sample_rate_hz/1500
                            diff=c.fractional_tracking_cfo_hz-seed['tracking_absolute_baseband_cfo_hz'];alias=round(diff/(1/4.4e-6));residual=diff-alias/(4.4e-6)
                            links=membership[v['visit'],rx,c.candidate_rank]
                            if abs(epoch_error)<=3 and abs(residual)<=2000 and links:
                                supported.update(links);evidence.append(dict(candidate_rank=c.candidate_rank,alias_lift=alias,frequency_residual_hz=residual,epoch_error_samples=epoch_error,track_ids=links))
                        equivalents.append(dict(track_ids=sorted(supported),evidence=evidence))
                    unique=[(rx,ids[0]) for rx,ids in enumerate(matches) if len(ids)==1]
                    equivalent_unique=[(rx,m['track_ids'][0]) for rx,m in enumerate(equivalents) if len(m['track_ids'])==1]
                    modes.append(dict(matches_by_rx=matches,equivalent_matches=equivalents,equivalent_preferred_track=(equivalent_unique[0][1] if equivalent_unique else None),equivalent_preferred_rx=(equivalent_unique[0][0] if equivalent_unique else None),preferred_track=(unique[0][1] if unique else None),preferred_rx=(unique[0][0] if unique else None)))
                visits.append(dict(visit=v['visit'],channel=v['channel'],edge=v['edge'],modes=modes))
                if len(modes)==2 and all(m['preferred_track'] for m in modes):
                    key=json.dumps([v['channel'],v['edge'],*[m['preferred_track'] for m in modes]])
                    groups[key].append(v['visit'])
            equivalent_groups=defaultdict(list)
            for v in visits:
                if len(v['modes'])==2 and all(m['equivalent_preferred_track'] for m in v['modes']):
                    key=json.dumps([v['channel'],v['edge'],*[m['equivalent_preferred_track'] for m in v['modes']]])
                    equivalent_groups[key].append(v['visit'])
            item=dict(session_id=sid,evidence_sha256=prepared.evidence_sha256,snapshot_digest=prepared.snapshot_digest,sites=old[sid]['sites'],source_result_sha256=hashlib.sha256(PREVIOUS.read_bytes()).hexdigest(),track_count=len(prepared.tracks),catalogue_count=len(prepared.candidate_indices),visits=visits,recurring_pairs=[dict(key=k,visits=v) for k,v in groups.items()],equivalent_recurring_pairs=[dict(key=k,visits=v) for k,v in equivalent_groups.items()])
            scans.append(item);print(sid,'tracks',len(tids),'pairs',[(len(v),v) for v in groups.values()],flush=True)
            print('alias-equivalent groups',[(len(v),v) for v in equivalent_groups.values()],flush=True)
    finally:store.close()
    (HERE/'catalogue-input-audit.json').write_text(json.dumps(dict(scans=scans),indent=2)+'\n')

if __name__=='__main__':main()
