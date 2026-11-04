"""Inventory every fast member through public native-evidence ports.

This is input availability accounting, not a numerical comparison. The supplied
membership document is hashed; unavailable members remain in the denominator.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from leo.cli.algo07_profile import write_new
from leo.storage.fast_scan import FastScanStore


def inventory(membership, store):
    members = membership['members']
    if len({m['recording_id'] for m in members}) != len(members):
        raise ValueError('Duplicate dataset recording membership')
    rows = []
    for member in members:
        if member['mode'] != 'fast':
            continue
        row = {key: member[key] for key in
               ('dataset_label', 'recording_id', 'session_id', 'sample_rate_hz')}
        try:
            status = store.automatic_status(member['recording_id'])
            run_id = (status or {}).get('run_id')
            row['run_id'] = run_id
            if not run_id:
                row['availability'] = 'no_native_run'
            else:
                data = store.tracking_input_path(run_id).read_bytes()
                tracking = json.loads(data)
                source = tracking['source']
                if source['session_id'] != member['session_id']:
                    raise ValueError('Native evidence belongs to a different session')
                original = store.source(source['session_id'], source['input_manifest_sha256'])
                if original['recording_name'] != member['recording_id']:
                    raise ValueError('Source inventory belongs to a different recording')
                report = store.detail(run_id, include_points=False)
                if report['session_id'] != member['session_id']:
                    raise ValueError('Native report belongs to a different session')
                row.update(availability='available',
                           input_sha256='sha256:'+hashlib.sha256(data).hexdigest(),
                           source_sha256=source['input_manifest_sha256'])
        except (OSError, ValueError, KeyError, TypeError) as error:
            row.update(availability='invalid_or_unavailable',
                       reason=f'{type(error).__name__}: {error}')
        rows.append(row)
    return dict(schema_version=1, kind='algo07-star-cohort-input-inventory',
                total_members=len(members), fast_members=len(rows),
                excluded_nonfast_members=len(members)-len(rows),
                counts=dict(Counter(r['availability'] for r in rows)), members=rows,
                numerical_inference_run=False, equivalence_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--membership', type=Path, required=True)
    parser.add_argument('--bulk-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.membership.read_bytes()
    result = inventory(json.loads(raw), FastScanStore(args.bulk_root))
    result['membership_sha256'] = hashlib.sha256(raw).hexdigest()
    write_new(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'members'}))
