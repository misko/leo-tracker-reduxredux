"""Verify the frozen DS7 metadata offline; does not read raw IQ."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load(name):
    return json.loads((root / name).read_bytes())


sealed = set()
for line in (root / 'SHA256SUMS').read_text().splitlines():
    expected, name = line.split('  ', 1)
    assert name not in sealed
    assert digest((root / name).read_bytes()) == 'sha256:' + expected, name
    sealed.add(name)
assert sealed == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
m = load('manifest.json')
approved = load('approved-proposal.json')
parent = load('ds6-parent-manifest.json')
units = load('evaluation-units.json')
authority = load('pose-authority.json')
receipt = load('mint-verification.json')
assert m['status'] == 'minted' and m['dataset_id'] == 'DS7'
assert digest((root / 'approved-proposal.json').read_bytes()) == m['approved_proposal_sha256']
assert digest((root / 'ds6-parent-manifest.json').read_bytes()) == m['parent']['manifest_sha256']
assert digest((root / 'pose-authority.json').read_bytes()) == m['pose_authority_file_sha256']
for key in approved:
    if key not in ('status', 'schema', 'proposed_dataset_id'):
        assert m[key] == approved[key], key
rows = m['captures']
ids = [r['session_id'] for r in rows]
assert len(ids) == len(set(ids)) == m['counts']['recordings'] == 88
assert not set(ids) & {r['session_id'] for r in parent['captures']}
assert digest(canonical(ids)) == m['session_inventory_sha256']
assert ids == units['full_dataset'] == [r['session_id'] for r in receipt['captures']]
assert units['single_scans'] == [[sid] for sid in ids]
assert len(units['groups_of_8']) == 11 and all(len(g) == 8 for g in units['groups_of_8'])
assert not units['remainder']
assert [sid for group in units['groups_of_8'] for sid in group] == ids
assert sorted(s for group in units['rate_strata'].values() for s in group) == sorted(ids)
for key, field in [('visits', 'visits'), ('compressed_bytes', 'compressed_bytes'),
                   ('uncompressed_bytes', 'uncompressed_bytes'),
                   ('dual_receiver_sample_instants', 'total_sample_count')]:
    assert m['counts'][key] == sum(r[field] for r in rows), key
lower = max(r['capture_end_utc_ns'] for r in parent['captures'])
assert ids == [r['session_id'] for r in sorted(rows, key=lambda r: (r['capture_start_utc_ns'], r['session_id']))]
for r, check in zip(rows, receipt['captures']):
    sid = r['session_id']
    assert r['manifest_sha256'] == check['manifest_sha256']
    assert r['pose_file_sha256'] == check['pose_file_sha256']
    assert r['capture_start_earliest_utc_ns'] > lower
    assert r['finalized_utc_ns'] <= m['inventory_cutoff_utc_ns']
    assert r['recording_complete'] and not r['exclusion_reasons']
    assert r['terminal_state'] == 'completed' and r['terminal_error_code'] == 0
    assert r['utc_qualified'] and r['source_span_attested'] and r['restoration_status'] == 'restored'
    assert r['visits'] == r['events'] == r['retained_visit_count'] > 0
    assert not any(r[k] for k in ('device_dropped_events', 'transport_missing_sample_count', 'unreceived_tail_sample_count', 'unclassified_sample_count'))
    assert r['total_sample_count'] == r['valid_sample_count'] > 0
    assert r['uncompressed_bytes'] == r['total_sample_count'] * len(r['receiver_ids']) * 4
    assert sid in units['rate_strata'][str(r['sample_rate_hz'])]
    pose_path = 'pose/' + sid + '.json'
    pose = load(pose_path)
    assert digest((root / pose_path).read_bytes()) == r['pose_file_sha256']
    assert pose['session_id'] == sid and pose['manifest_sha256'] == r['manifest_sha256']
    assert pose['pose_authority'] == authority
    assert digest(canonical(authority)) == pose['pose_authority_digest'] == r['pose_authority_digest']
    assert digest(canonical({k: v for k, v in pose.items() if k != 'binding_digest'})) == pose['binding_digest'] == r['pose_binding_digest']
    assert pose['capture_start_earliest_utc_ns'] == r['capture_start_earliest_utc_ns']
    assert pose['capture_end_utc_ns'] == r['capture_end_utc_ns']
    assert authority['valid_from_utc_ns'] <= r['capture_start_earliest_utc_ns']
    assert authority['valid_until_utc_ns'] >= r['capture_end_utc_ns']
print('PASS: DS7 seals, exact 88 approved recordings, accounting, DS6 exclusion, 88 pose bindings and evaluation units')
