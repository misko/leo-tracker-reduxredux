"""Verify DS6 artifact seals and membership offline; does not read raw IQ."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent


def digest(payload):
    return 'sha256:' + hashlib.sha256(payload).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load(name):
    return json.loads((root / name).read_text())


seals = (root / 'SHA256SUMS').read_text().splitlines()
sealed = set()
for line in seals:
    expected, name = line.split('  ', 1)
    assert digest((root / name).read_bytes()) == 'sha256:' + expected, name
    sealed.add(name)
assert sealed == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
manifest = load('manifest.json')
approved = load('approved-inventory.json')
units = load('evaluation-units.json')
authority = load('pose-authority.json')
rows = manifest['captures']
ids = [r['session_id'] for r in rows]
assert len(ids) == len(set(ids)) == 43
assert ids == [r['session_id'] for r in approved['captures']]
assert sum(r['visits'] for r in rows) == 95269
assert digest(canonical(ids)) == manifest['session_inventory_sha256'] == units['session_inventory_sha256']
assert digest((root / 'approved-inventory.json').read_bytes()) == manifest['approved_inventory_sha256']
assert digest(canonical(authority)) == manifest['pose_authority_digest']
assert units['full_dataset'] == ids
assert units['single_scans'] == [[sid] for sid in ids]
assert len(units['groups_of_8']) == 5 and all(len(g) == 8 for g in units['groups_of_8'])
assert [sid for group in units['groups_of_8'] for sid in group] + units['remainder'] == ids
assert len(units['remainder']) == 3
assert sorted(sid for group in units['rate_strata'].values() for sid in group) == sorted(ids)
for row, prior in zip(rows, approved['captures']):
    pose = load(row['pose_path'])
    assert row['manifest_sha256'] == prior['manifest_sha256'] == pose['manifest_sha256']
    assert pose['session_id'] == row['session_id']
    assert pose['pose_authority'] == authority
    assert pose['pose_authority_digest'] == manifest['pose_authority_digest']
    assert digest(canonical({k: v for k, v in pose.items() if k != 'binding_digest'})) == row['binding_digest'] == pose['binding_digest']
    assert digest((root / row['pose_path']).read_bytes()) == row['pose_file_sha256']
    assert row['session_id'] in units['rate_strata'][str(row['sample_rate_hz'])]
print('PASS: all seals, 43 approved recordings, 95,269 visits, pose bindings and evaluation partitions')
