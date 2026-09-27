"""Verify complete DS6 membership, sealed sources, and whole-visit partitions."""
import hashlib
import json
from pathlib import Path

from prepare import partition

HERE=Path(__file__).resolve().parent


def test_complete_dataset_and_random_groups():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'prepare.py').read_bytes()).hexdigest()==protocol['source_sha256']
    expected={c['session_id']:c for c in protocol['captures']}
    files=list(HERE.glob('scan-fw-*-plan.json'))
    assert len(files)==len(expected)==43
    for path in files:
        data=json.loads(path.read_text());session=data['session_id']
        assert data['input_manifest_sha256']==expected[session]['manifest_sha256']
        assert data['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert data['state']=='complete',data
        groups={}
        for track in data['tracks']:
            n=len(track['times_s'])
            assert all(len(track[k])==n for k in ['measured_hz','training_mask','visits','candidate_ids'])
            for visit,training in zip(track['visits'],track['training_mask'],strict=True):
                assert training==partition(session,visit)
                assert visit not in groups or groups[visit]==training
                groups[visit]=training
        assert set(groups.values())=={False,True}


def test_existing_four_scan_inputs_are_numerically_unchanged():
    old=HERE.parent/'2026_09_27_ds6_common_rate_validation'
    for path in old.glob('scan-fw-*-plan.json'):
        before=json.loads(path.read_text());after=json.loads((HERE/path.name).read_text())
        for key in ['start_utc_ns','snapshot_digest','input_manifest_sha256','analysis_manifest_sha256']:
            assert before[key]==after[key]
        assert {t['track_id']:t for t in before['tracks']}=={t['track_id']:t for t in after['tracks']}
