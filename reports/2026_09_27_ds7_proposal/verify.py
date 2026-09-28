"""Verify the proposed membership and seals without storage or IQ access."""
import hashlib
import json
from pathlib import Path


def verify(root):
    manifest = json.loads((root / 'proposed-manifest.json').read_text())
    inventory = json.loads((root / 'inventory.json').read_text())
    parent = json.loads((root / 'ds6-parent-manifest.json').read_text())
    rows = manifest['captures']
    ids = [r['session_id'] for r in rows]
    assert manifest['status'] == 'proposal_not_minted'
    assert len(ids) == len(set(ids))
    assert not set(ids) & {r['session_id'] for r in parent['captures']}
    assert ids == [r['session_id'] for r in inventory['captures'] if r['recording_complete']]
    assert rows == [r for r in inventory['captures'] if r['recording_complete']]
    assert ids == [r['session_id'] for r in sorted(rows, key=lambda r: (r['capture_start_utc_ns'], r['session_id']))]
    lower = max(r['capture_end_utc_ns'] for r in parent['captures'])
    for r in rows:
        assert r['capture_start_earliest_utc_ns'] > lower
        assert r['finalized_utc_ns'] <= manifest['inventory_cutoff_utc_ns']
        assert r['utc_qualified'] and r['source_span_attested']
        assert r['terminal_state'] == 'completed' and r['terminal_error_code'] == 0
        assert not r['exclusion_reasons']
        assert r['visits'] == r['events'] == r['retained_visit_count']
        assert not any(r[k] for k in ('device_dropped_events', 'transport_missing_sample_count',
                                      'unreceived_tail_sample_count', 'unclassified_sample_count'))
        assert r['total_sample_count'] == r['valid_sample_count']
        assert r['uncompressed_bytes'] == r['total_sample_count'] * len(r['receiver_ids']) * 4
    assert manifest['counts']['recordings'] == len(rows)
    assert manifest['counts']['visits'] == sum(r['visits'] for r in rows)
    units = json.loads((root / 'evaluation-units.json').read_text())
    assert units['full_dataset'] == ids
    assert [s for g in units['groups_of_8'] for s in g] + units['remainder'] == ids
    assert sorted(s for g in units['rate_strata'].values() for s in g) == sorted(ids)
    expected = manifest['parent']['manifest_sha256']
    assert 'sha256:' + hashlib.sha256((root / 'ds6-parent-manifest.json').read_bytes()).hexdigest() == expected
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        h, name = line.split('  ', 1)
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == h, name
    print(f'PASS: {len(rows)} proposed recordings, exact DS6 exclusion, chronology, sample accounting, units and seals')


if __name__ == '__main__':
    verify(Path(__file__).resolve().parent)
