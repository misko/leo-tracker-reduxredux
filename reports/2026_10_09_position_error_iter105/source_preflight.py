"""Verify saved snapshots without numerical work or further source access."""
import hashlib
import json
from pathlib import Path
from leo.contracts.digests import canonical_digest

HERE=Path(__file__).resolve().parent


def main():
    path=HERE/'source-snapshot.json';snapshot=json.loads(path.read_text());checked=0
    for member in snapshot['members']:
        assert member['sampled_point_count']==member['available_coarse_point_count']==400
        assert not member['compatibility']['eligible']
        assert 'reference_latitude_deg' not in member['document']
        for key,receipt in member['checkpoints'].items():
            payload=(HERE/receipt['file']).read_bytes()
            assert hashlib.sha256(payload).hexdigest()==receipt['file_sha256'],key
            assert canonical_digest(json.loads(payload))==receipt['value_sha256'],key
            checked+=1
    result=dict(snapshot_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),members=len(snapshot['members']),checked_payloads=checked,
                sampled_coarse_points=2000,available_coarse_points=2000,missing_keys=sum(len(m['missing_keys']) for m in snapshot['members']),
                status='saved-payload-integrity-verified',model_compatibility='pending driver preflight; no numerical validation performed',
                snapshotter_sha256=hashlib.sha256((HERE/'source_snapshot.py').read_bytes()).hexdigest())
    (HERE/'source-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result)


if __name__=='__main__':main()
