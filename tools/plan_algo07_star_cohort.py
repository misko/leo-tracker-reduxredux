"""Predeclare a deterministic full-cohort order without using fit outcomes."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from leo.cli.algo07_profile import write_new


def plan(inventory, *, seed):
    if inventory.get('kind') != 'algo07-star-cohort-input-inventory':
        raise ValueError('Public native-evidence inventory required')
    members = inventory['members']
    if (len(members) != inventory['fast_members'] or
            len({m['dataset_label'] for m in members}) != len(members) or
            len({m['recording_id'] for m in members}) != len(members)):
        raise ValueError('Complete unique cohort membership required')
    rows = []
    for member in members:
        if not re.fullmatch(r'DS26-[0-9]{4}', member['dataset_label']):
            raise ValueError('DS26 fast cohort required')
        row = dict(member)
        if row['availability'] == 'available':
            native_hash = row.get('input_sha256')
            if (not row.get('run_id') or not isinstance(native_hash, str) or
                    not re.fullmatch(r'sha256:[0-9a-f]{64}', native_hash)):
                raise ValueError('Available member must bind exact native bytes')
            key = f"{seed}:{row['dataset_label']}:{row['input_sha256']}"
            row['ordering_key'] = hashlib.sha256(key.encode('ascii')).hexdigest()
        else:
            row['ordering_key'] = None
        rows.append(row)
    available = sorted((r for r in rows if r['ordering_key']), key=lambda r: r['ordering_key'])
    return dict(schema_version=1, kind='algo07-star-cohort-execution-plan', seed=seed,
                ordering='Ascending SHA256(seed:dataset_label:input_sha256); no fit outcomes',
                fast_members=len(rows), available_members=len(available),
                unavailable_members=len(rows)-len(available), members=rows,
                execution_order=[r['dataset_label'] for r in available],
                per_invocation_maximum_seconds=1800, whole_stage_maximum_seconds=1200,
                simultaneous_paths_limit=4, performance_comparison=False,
                numerical_inference_run=False, ds26_equivalence_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=20261104)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.inventory.read_bytes()
    result = plan(json.loads(raw), seed=args.seed)
    result['inventory_sha256'] = hashlib.sha256(raw).hexdigest()
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('members', 'execution_order')}))
    print('First cases:', ', '.join(result['execution_order'][:8]))
