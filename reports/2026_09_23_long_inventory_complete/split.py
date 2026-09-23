"""Freeze exposure-aware random whole-eight-hour groups from metadata only."""

import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

EXPOSED = {'2026-09-21T00:00:00+00:00', '2026-09-21T08:00:00+00:00'}


def assign(inventory, seed=20260923):
    start = datetime.fromisoformat(inventory['window_start'])
    end = datetime.fromisoformat(inventory['window_end_exclusive'])
    rows = {r['session_id']: r for r in inventory['scans']}
    eligible = {}
    for group in inventory['utc_8h_groups']:
        key = group['utc_8h_start']
        stamp = datetime.fromisoformat(key)
        ids = group['session_ids']
        if not (start <= stamp and stamp + timedelta(hours=8) <= end):
            continue
        if len(ids) < 40 or any(rows[sid]['nominal_duration_s'] != 300 for sid in ids):
            continue
        if any(not rows[sid]['contained_nominal_interval'] for sid in ids):
            raise ValueError('crossing capture')
        eligible[key] = ids
    if len(eligible) != 5 or not eligible.keys() >= EXPOSED:
        raise ValueError('expected frozen five-group cohort')
    rng = random.Random(seed)
    test = rng.choice(sorted(set(eligible) - EXPOSED))
    rest = sorted(set(eligible) - {test})
    rng.shuffle(rest)
    partitions = {}
    for name, groups in [('train', rest[:2]), ('validation', rest[2:]), ('test', [test])]:
        partitions[name] = {
            'groups': groups,
            'session_ids': [sid for key in groups for sid in eligible[key]],
        }
    all_ids = [sid for part in partitions.values() for sid in part['session_ids']]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('duplicate capture across groups')
    if set(all_ids) & set(inventory['excluded_ids']):
        raise ValueError('excluded capture included')
    return {'seed': seed, 'group_hours': 8, 'partitions': partitions,
            'known_track_exposed_groups': sorted(EXPOSED),
            'assignment_uses_track_or_position_outcomes': False,
            'test_scope': 'Not opened for track evidence in this work; historical exposure unknown',
            'duration_views_scan_counts': [1, 6, 16, 'all']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = assign(json.loads(args.inventory.read_text()))
    result['inventory_sha256'] = hashlib.sha256(args.inventory.read_bytes()).hexdigest()
    result['worker_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
