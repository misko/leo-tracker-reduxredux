"""Bind raw timing-match events to existing causal donor geometry."""
from collections import defaultdict,Counter
import inspect
import json
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HERE.parent/'detection_evidence'))
from epoch_pairs import digest
from events import event


def main(index):
    from tools.rx_paired_opportunities import export_input,projected_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    from leo.application.persistent_hop_trajectory import FRAME_RATE_HZ
    started=time.monotonic();assert index in (16,17)
    donor_path=HERE.parent/f'acquisition_calibration/donor-{index:02d}.json';donor=json.loads(donor_path.read_text())
    calpath=HERE.parent/'detection_evidence/soft-calibration.json';cal=json.loads(calpath.read_text())
    for doc in (donor,cal):
        for p,h in doc['sources'].items():assert digest(p)==h,p
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:raw=store.load(donor['session_id'])
    finally:store.close()
    assert raw.qualified and raw.timing.qualified
    previous=json.loads((HERE.parent/f'detection_evidence/epoch-pairs-{index:02d}.json').read_text())
    assert previous['input_manifest_sha256']==raw.input_manifest_sha256
    assert previous['analysis_manifest_sha256']==raw.analysis_manifest_sha256
    projected=projected_candidates(raw)
    graph=reconstruct_persistent_hop_trajectories(list(projected.values()),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    tracks={t.tracklet_id:t for t in graph.tracklets};owners=defaultdict(set)
    for lane in donor['lanes']:
        key=(lane['norad'],lane['rf_hz'])
        for tid in lane['tracks']:
            for p in tracks[tid].points:owners[p.candidate_id].add(key)
    opportunities,_=export_input(raw,split=donor['role'],cache_sha256='public-input:'+raw.input_manifest_sha256+':'+raw.analysis_manifest_sha256,projected=projected)
    by_rf=defaultdict(list)
    for o in opportunities:by_rf[o['receivers']['rx0']['actual_rf_hz']].append(o)
    rows=[];counts=Counter()
    for lane in donor['lanes']:
        key=(lane['norad'],lane['rf_hz']);windows=by_rf[lane['rf_hz']]
        assert len(windows)==len(lane['times_s'])
        for j,o in enumerate(windows):
            candidates=[[],[]];anchors=[]
            for rx in (0,1):
                for c in o['receivers'][f'rx{rx}']['candidates']:
                    if not c['passed_fractional_margin_gate']:continue
                    cid=c['projected_candidate_id']
                    point=dict(id=cid,receiver=rx,epoch_us=(c['integer_epoch_sample']+c['fractional_epoch_offset_samples'])/donor['sample_rate_hz']*1e6)
                    candidates[rx].append(point)
                    if owners.get(cid)=={key}:anchors.append(point)
            if not anchors:
                counts['unanchored_source_windows']+=1;continue
            out=event(anchors,candidates,owners,key,cal['threshold_us'],1e6/FRAME_RATE_HZ)
            rows.append(dict(source=f"{lane['norad']}:{lane['rf_hz']}",norad=lane['norad'],rf_hz=lane['rf_hz'],window_id=o['source_window_id'],time_s=lane['times_s'][j],los_enu=lane['los_enu'][j],training=lane['training_mask'][j],**out))
            counts['events']+=1
            for field in ('hit','raw_only','conflicting_inferred_partner'):counts[field]+=out[field]
            counts['shift_hits']+=sum(out['shift_hits'])
    paths=[Path(__file__),HERE/'events.py',HERE/'PROTOCOL.md',donor_path,calpath,HERE.parent/f'detection_evidence/epoch-pairs-{index:02d}.json']
    paths+=[Path(inspect.getfile(f)) for f in (export_input,projected_candidates,ScannerTrackingInputStore,reconstruct_persistent_hop_trajectories)]
    result=dict(index=index,role=donor['role'],family=2,frequencies=donor['rf_hz'],rows=rows,counts=dict(counts),sources={str(p):digest(p) for p in paths},elapsed_s=time.monotonic()-started)
    with (HERE/f'input-{index:02d}.json').open('x') as f:json.dump(result,f,allow_nan=False)
    print(json.dumps(dict(index=index,counts=result['counts'],elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
