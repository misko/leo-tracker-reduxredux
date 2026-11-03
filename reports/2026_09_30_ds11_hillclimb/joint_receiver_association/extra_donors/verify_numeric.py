"""Verify numerical donor products, their source bindings and causal snapshots."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap=HERE/'availability.json';availability=json.loads(ap.read_text());assert availability['passed']
    sources={str(p):digest(p) for p in (Path(__file__),ap,HERE/'test_policy.py',HERE/'test_availability.py')}
    for p,h in availability['sources'].items():assert digest(p)==h,p
    rows=[]
    for i in range(4):
        folder=HERE/f'numeric-{i:02d}';tp=folder/'tracks.json';mp=folder/'banks/manifest.json';bp=folder/'banks/banks.npz'
        receipts=[]
        for stage in ('tracks','banks'):
            rp=HERE/f'{stage}-{i:02d}.receipt.json';receipt=json.loads(rp.read_text());assert receipt['exit_code']==0
            for p,h in receipt['sources'].items():assert digest(p)==h,p
            sources[str(rp)]=digest(rp);receipts.append(receipt)
        tracks=json.loads(tp.read_text());manifest=json.loads(mp.read_text());proof=availability['rows'][i]
        assert tracks['analysis_manifest_sha256']==proof['analysis_manifest_sha256']
        assert manifest['tracks_sha256']=='sha256:'+digest(tp)
        assert manifest['baseline_snapshot_sha256']==proof['baseline_snapshot_sha256']
        actual={(r['provider'],r['collected_utc_ns'],r['snapshot_sha256']) for r in manifest['provider_sources']}
        expected={(r['provider'],r['request_utc_ns'],r['snapshot_sha256']) for r in proof['provider_sources']}
        assert actual==expected
        supported={t['track_id']:t for t in tracks['tracks'] if sum(t['training_mask'])>=2 and sum(not x for x in t['training_mask'])>=1}
        assert set(supported)=={t['track_id'] for t in manifest['tracks']}
        candidates=0
        with np.load(bp,allow_pickle=False) as bank:
            np.testing.assert_array_equal(bank['timing_grid_s'],np.arange(-5,5.001,.25))
            for row in manifest['tracks']:
                j=row['index'];ids=bank[f'candidate_ids_{j}'];pos=bank[f'position_km_{j}'];vel=bank[f'velocity_km_s_{j}']
                n=len(supported[row['track_id']]['times_s'])
                assert len(ids)==row['candidate_count'] and len(set(ids))==len(ids) and (ids>=0).all() and (ids<manifest['catalogue_size']).all()
                assert pos.shape==vel.shape==(len(ids),41,n,3)
                assert np.isfinite(pos).all() and np.isfinite(vel).all()
                candidates+=len(ids)
        for p in (tp,mp,bp,folder/'banks/shortlists.json'):sources[str(p)]=digest(p)
        rows.append(dict(ordinal=i,family=proof['family'],exported_tracks=len(tracks['tracks']),bank_tracks=len(supported),candidate_track_slots=candidates,
                         track_worker_s=receipts[0]['elapsed_s'],bank_worker_s=receipts[1]['elapsed_s']))
    test=subprocess.run([sys.executable,'-m','unittest','test_policy','test_availability'],cwd=HERE,capture_output=True,text=True,timeout=60)
    assert test.returncode==0,test.stdout+test.stderr
    out=dict(passed=True,rows=rows,component_tests_passed=4,test_output=test.stdout+test.stderr,sources=sources,
             source_identity_calibrated=False,receiver_calibration_fitted=False,position_fits=0,
             causal_position_improvement_established=False)
    with (HERE/'numeric-summary.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    audit=dict(passed=True,previous_goal_turn='progress: four prospective donor captures verified',
               numerical_exports=8,component_tests_passed=4,goal_status='active',causal_position_improvement_established=False,
               sources={str(HERE/'numeric-summary.json'):digest(HERE/'numeric-summary.json')})
    with (HERE.parent/'progress-audit-23.json').open('x') as f:json.dump(audit,f,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k!='sources'},indent=2))


if __name__=='__main__':main()
