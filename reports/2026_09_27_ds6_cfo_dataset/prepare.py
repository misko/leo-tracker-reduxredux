"""Export numerical CFO tracks for all frozen DS6 recordings, without raw IQ."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
SEED=2026092711


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partition(session,visit):
    return int(hashlib.sha256(f'{SEED}:visit:{session}:{visit}'.encode()).hexdigest()[:8],16)%10<6


def freeze():
    inventory=HERE.parent/'2026_09_27_ds6_roof/approved-inventory.json'
    source_files=['src/leo/operations/adaptive_tle_position_inputs.py',
        'src/leo/application/scanner_trajectory.py','src/leo/analysis/persistent_hop_trajectory.py',
        'src/leo/storage/scanner_tracking_source.py','src/leo/analysis/adaptive_tle_prediction.py']
    protocol=dict(source_sha256=digest(Path(__file__)),inventory_sha256=digest(inventory),
        implementation_sha256={name:digest(ROOT/name) for name in source_files},
        captures=json.loads(inventory.read_text())['captures'],seed=SEED,
        partition='SHA256(seed:visit:session:visit), first 32 bits modulo10 <6; whole visit shared across tracks and receivers',
        scope='All 43 frozen DS6 captures; existing analyzed metadata only; no RF or raw IQ replay',
        tracks='Public preparation port; three-second six-observation trajectories, no location-based filtering',
        failure_policy='Record unavailable evidence explicitly; do not replace captures; integrity errors stop the export')
    assert len(protocol['captures'])==43
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def prepare(limit):
    import numpy as np
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs,AdaptiveTleInputUnavailable
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    assert digest(HERE.parent/'2026_09_27_ds6_roof/approved-inventory.json')==protocol['inventory_sha256']
    for name,value in protocol['implementation_sha256'].items():assert digest(ROOT/name)==value
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    count=0
    try:
        for capture in protocol['captures']:
            session=capture['session_id'];output=HERE/f'{session}-plan.json'
            if output.exists():
                assert json.loads(output.read_text())['protocol_sha256']==digest(HERE/'protocol.json')
                continue
            if count>=limit:break
            raw=store.load(session)
            assert raw.input_manifest_sha256==capture['manifest_sha256']
            class Inputs:
                def load(self,name):
                    assert name==session
                    return raw
            base=dict(session_id=session,protocol_sha256=digest(HERE/'protocol.json'),
                input_manifest_sha256=raw.input_manifest_sha256,analysis_manifest_sha256=raw.analysis_manifest_sha256,
                rate_hz=raw.sample_rate_hz)
            try:
                prepared=prepare_adaptive_tle_position_inputs(session,inputs=Inputs(),archive=TleArchiveReader(Path('/var/lib/leo/tle')))
            except AdaptiveTleInputUnavailable as error:
                result=dict(base,state='unavailable',reason=str(error),tracks=[])
            else:
                points=project_scanner_candidates(raw);byid={p.candidate_id:p for p in points}
                graph=reconstruct_persistent_hop_trajectories(points,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
                numeric={t.track_id:t for t in prepared.tracks};tracks=[]
                for track in graph.tracklets:
                    if track.tracklet_id not in numeric:continue
                    pts=[byid[p.candidate_id] for p in track.points];num=numeric[track.tracklet_id]
                    np.testing.assert_allclose([(p.support_center_utc_ns-prepared.start_utc_ns)/1e9 for p in pts],num.times_s,rtol=0,atol=1e-9)
                    tracks.append(dict(track_id=track.tracklet_id,times_s=num.times_s.tolist(),measured_hz=num.measured_hz.tolist(),
                        training_mask=[partition(session,p.visit_index) for p in pts],receiver_id=pts[0].receiver_id,
                        channel=pts[0].channel,rf_hz=pts[0].actual_rf_hz,visits=[p.visit_index for p in pts],
                        candidate_ids=[p.candidate_id for p in pts]))
                assert {t['track_id'] for t in tracks}==set(numeric)
                result=dict(base,state='complete',start_utc_ns=prepared.start_utc_ns,snapshot_digest=prepared.snapshot_digest,
                    timing=raw.timing.model_dump(mode='json'),evidence_sha256=prepared.evidence_sha256,tracks=tracks)
            with output.open('x') as f:json.dump(result,f)
            count+=1
            print(session,result['state'],len(result['tracks']),'tracks',flush=True)
    finally:store.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--limit',type=int,default=43)
    args=parser.parse_args()
    if args.freeze:freeze()
    else:prepare(args.limit)
