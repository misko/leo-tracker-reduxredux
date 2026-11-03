import hashlib
import importlib
import json
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main(ds):
    started=time.monotonic()
    plan=json.loads((HERE/'manifest.json').read_text())
    for name,h in plan['hashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    environment=json.loads((HERE.parent/'2026_09_28_full_manifest_inputs/environment.json').read_text())
    modules={}
    for name in ('leo.storage.scanner_tracking_source','leo.application.scanner_trajectory','leo.analysis.persistent_hop_trajectory'):
        obj=importlib.import_module(name)
        h=hashlib.sha256(Path(obj.__file__).read_bytes()).hexdigest()
        assert h==environment['modules'][name]['sha256'],name
        modules[name]=h
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    item=next(x for x in plan['scans'] if x['dataset']==ds)
    baseline=json.loads(Path(item['observations']).read_text())
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw=store.load(item['session_id'])
        assert raw.input_manifest_sha256==baseline['manifest_sha256']
        assert raw.analysis_manifest_sha256==baseline['analysis_manifest_sha256']
        projected=project_scanner_candidates(raw)
        by_id={p.candidate_id:p for p in projected}
        graph=reconstruct_persistent_hop_trajectories(projected,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
        tracks={t.tracklet_id:t for t in graph.tracklets}
        rows=[]
        for track in baseline['tracks']:
            source=tracks[track['track_id']]
            assert len(source.points)==len(track['times_s'])
            for i,p in enumerate(source.points):
                q=by_id[p.candidate_id]
                assert abs((q.support_center_utc_ns-baseline['start_utc_ns'])/1e9-track['times_s'][i])<=1e-9
                assert abs(q.measured_cfo_hz-track['measured_hz'][i])<1e-7
                assert q.receiver_id==track['receiver_id'] and q.channel==track['channel']
                assert q.actual_rf_hz==track['rf_hz'] and q.visit_index==track['visits'][i]
                rows.append(dict(track_id=track['track_id'],index=i,training=track['training_mask'][i],candidate_id=q.candidate_id,source_group_id=q.source_group_id,candidate_rank=q.candidate_rank,exact_score=q.exact_score,control_score=q.control_score,margin=q.margin,standard_uncertainty_hz=q.standard_uncertainty_hz,support_duration_ns=q.support_end_utc_ns-q.support_start_utc_ns))
        result=dict(dataset=ds,session_id=raw.session_id,tracks=len(baseline['tracks']),observations=len(rows),timing_bracket_width_ns=raw.timing.first_sample_bracket_width_ns,rows=rows,module_hashes=modules,baseline_sha256=hashlib.sha256(Path(item['observations']).read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-started)
        with (HERE/f'{ds}.json').open('x') as out:
            json.dump(result,out,indent=2,allow_nan=False)
        print(ds,len(rows),flush=True)
    finally:
        store.close()


if __name__=='__main__':
    main(sys.argv[1])
