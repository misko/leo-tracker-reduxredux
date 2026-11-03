"""Bounded metadata/trajectory eligibility check through public input ports."""
from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time
from policy import choose,family

HERE=Path(__file__).resolve().parent;PARENT=HERE.parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(ordinal):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    from tools.rx_paired_opportunities import projected_candidates
    started=time.monotonic()
    candidates=PARENT/'acquisition_calibration/extra-2p5-candidates.json';inventory=PARENT/'acquisition-calibration-inventory.json'
    old,inv=[json.loads(p.read_text()) for p in (candidates,inventory)]
    for p,h in old['sources'].items():assert digest(p)==h,p
    selected=choose(old['captures'],inv['earliest_target_utc_ns']);capture=selected[ordinal]
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:raw=store.load(capture['session_id'])
    finally:store.close()
    assert raw.input_manifest_sha256==capture['manifest_sha256']
    assert raw.qualified and raw.timing.qualified
    projected=projected_candidates(raw);by_id={c.candidate_id:c for c in projected.values()}
    graph=reconstruct_persistent_hop_trajectories(list(projected.values()),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    frequencies=sorted({c.actual_rf_hz for c in projected.values()})
    rf_family=family(raw.sample_rate_hz,frequencies,inv['families'])
    rows=[]
    for track in graph.tracklets:
        points=[by_id[p.candidate_id] for p in track.points]
        rows.append(dict(track_id=track.tracklet_id,receiver=points[0].receiver_id,
                         rf_hz=points[0].actual_rf_hz,support=len(points),
                         span_s=(max(p.support_center_utc_ns for p in points)-min(p.support_center_utc_ns for p in points))/1e9))
    paths=[Path(__file__),HERE/'policy.py',HERE/'PROTOCOL.md',candidates,inventory]
    paths += [Path(inspect.getfile(f)) for f in (ScannerTrackingInputStore,projected_candidates,reconstruct_persistent_hop_trajectories)]
    out=dict(ordinal=ordinal,session_id=capture['session_id'],family=rf_family,
             sample_rate_hz=raw.sample_rate_hz,rf_hz=frequencies,projected_candidates=len(projected),
             retained_tracks=len(rows),tracks_by_receiver=dict(Counter(r['receiver'] for r in rows)),
             tracks=rows,input_manifest_sha256=raw.input_manifest_sha256,
             analysis_manifest_sha256=raw.analysis_manifest_sha256,
             capture_metadata=capture,sources={str(p):digest(p) for p in paths},
             orbit_support_checked=False,calibration_ready=False,elapsed_s=time.monotonic()-started)
    with (HERE/f'capture-{ordinal:02d}.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k not in ('tracks','sources','capture_metadata')},indent=2))


if __name__=='__main__':main(int(sys.argv[1]))
