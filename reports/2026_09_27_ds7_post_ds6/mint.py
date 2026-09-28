"""Mint the approved DS7 metadata snapshot; read source storage only."""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from leo.storage.adaptive_hop import AdaptiveHopIqStore

ROOT = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
PROPOSAL = ROOT / 'reports/2026_09_27_ds7_proposal'
DEST = ROOT / 'reports/2026_09_27_ds7_post_ds6'


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def main():
    if DEST.exists():
        raise RuntimeError('Refusing to overwrite an existing DS7 mint')
    sys.path.insert(0, str(PROPOSAL))
    from verify import verify
    verify(PROPOSAL)
    approved = (PROPOSAL / 'proposed-manifest.json').read_bytes()
    manifest = json.loads(approved)
    store = AdaptiveHopIqStore(Path('/srv/bulk/leo'), read_only=True)
    poses = {}
    checks = []
    started = datetime.now(timezone.utc).isoformat()
    for row in manifest['captures']:
        sid = row['session_id']
        session = store.inspect(sid)
        assert session.manifest_sha256 == row['manifest_sha256'], sid
        payload = (Path('/srv/bulk/leo/capture-pose') / row['pose_authority_revision'] / (sid + '.json')).read_bytes()
        assert digest(payload) == row['pose_file_sha256'], sid
        poses[sid] = payload
        checks.append({'session_id': sid, 'manifest_sha256': session.manifest_sha256,
                       'pose_file_sha256': digest(payload)})
    authority = Path('/etc/leo/station-authority/gauss-r20-roof-20260926-v1.json').read_bytes()
    assert digest(authority) == 'sha256:265b11f58ffee16672c3c46f0d95947220f60ab77eab3a9c0cb5e1a60c9e17d9'
    manifest.update(schema='ds7-admission/v1', status='minted', dataset_id='DS7',
                    dataset_name='DS7 complete post-DS6 adaptive recordings',
                    minted_utc=datetime.now(timezone.utc).isoformat(),
                    approved_proposal_sha256=digest(approved),
                    source_bulk_root='/srv/bulk/leo',
                    pose_authority_file_sha256=digest(authority),
                    retention={'requested_policy': 'retain all DS7 source recordings for reproducible research',
                               'enforced_hold': False,
                               'scope': 'Metadata freeze; no payload copy or storage retention mutation. Inspected catalog retention supports recordings, scanner and persistent-hop stores, not this adaptive-hop store. No backup or indefinite retention guarantee is asserted.'})
    del manifest['proposed_dataset_id']
    DEST.mkdir()
    (DEST / 'pose').mkdir()
    (DEST / 'approved-proposal.json').write_bytes(approved)
    for name in ('ds6-parent-manifest.json', 'recordings.csv', 'TABLE.md'):
        shutil.copyfile(PROPOSAL / name, DEST / name)
    (DEST / 'pose-authority.json').write_bytes(authority)
    for sid, payload in poses.items():
        (DEST / 'pose' / (sid + '.json')).write_bytes(payload)
    units = json.loads((PROPOSAL / 'evaluation-units.json').read_bytes())
    units['status'] = 'frozen_evaluation_units_not_a_train_test_split'
    receipt = {'started_utc': started, 'finished_utc': manifest['minted_utc'],
               'storage_reader_release': manifest['storage_reader_release'],
               'verification_scope': manifest['integrity_scope'],
               'payload_files_statted': False, 'payload_rehashed': False, 'captures': checks}
    for name, obj in [('manifest.json', manifest), ('evaluation-units.json', units), ('mint-verification.json', receipt)]:
        (DEST / name).write_text(json.dumps(obj, indent=2) + '\n')
    shutil.copyfile(__file__, DEST / 'mint.py')
    print(f'Minted {len(checks)} recordings at {DEST}; documentation and artifact seals follow')


if __name__ == '__main__':
    main()
