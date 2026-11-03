"""Read-only validation of recorded pose companions for the original DS11 panel."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical_digest(d):return 'sha256:'+hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def validate(document,entry):
    content={k:v for k,v in document.items() if k!='binding_digest'}
    assert canonical_digest(content)==document['binding_digest']
    pose=document['pose_authority'];assert canonical_digest(pose)==document['pose_authority_digest']
    assert document['session_id']==entry['session_id'] and document['manifest_sha256']==entry['manifest_sha256']
    assert pose['valid_from_utc_ns']<=document['capture_start_earliest_utc_ns']<=document['capture_end_utc_ns']<pose['valid_until_utc_ns']
    return pose
def main():
    plan_path=HERE.parents[1]/'2026_09_30_ds11_single10/plan.json';plan=json.loads(plan_path.read_text())
    files={p.stem:p for p in Path('/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1').glob('*.json')}
    sources={str(plan_path):digest(plan_path)};rows=[]
    for index,entry in enumerate(plan['inputs']):
        path=files[entry['session_id']];d=json.loads(path.read_text());pose=validate(d,entry);sources[str(path)]=digest(path)
        rows.append(dict(index=index,session_id=entry['session_id'],pose_authority_digest=d['pose_authority_digest'],
                         altitude_m=pose['altitude_m'],altitude_datum=pose['altitude_datum'],
                         phase_center_baseline_enu_m=pose['phase_center_baseline_enu_m'],
                         receiver_elevations_deg=[r['elevation_deg'] for r in pose['receivers']],
                         receiver_mapping_status=[r['mapping_status'] for r in pose['receivers']]))
    for p in (Path(__file__),HERE/'test_run.py',ROOT/'tools/bind_adaptive_capture_pose.py'):sources[str(p)]=digest(p)
    result=dict(rows=rows,summary=dict(captures=len(rows),verified_companions=len(rows),
            distinct_pose_authorities=len({r['pose_authority_digest'] for r in rows}),
            measured_altitudes=sum(r['altitude_m'] is not None for r in rows),
            measured_phase_center_baselines=sum(r['phase_center_baseline_enu_m'] is not None for r in rows)),
            sources=sources,read_only=True,position_fits=0)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
