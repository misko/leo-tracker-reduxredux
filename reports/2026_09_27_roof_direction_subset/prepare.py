"""Freeze a chronological roof subset and cache verified public tracking inputs.

Report orchestration only; does not modify source stores or acquire RF.
Pickles are locally generated analysis caches, not portable/public contracts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/srv/bulk/leo')
POSE = ROOT / 'capture-pose/gauss-r20-roof-20260926-v1'


def digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def validate_pose(pose):
    body = {k: v for k, v in pose.items() if k != 'binding_digest'}
    if digest(canonical(body)) != pose['binding_digest']:
        raise ValueError('invalid pose binding digest')
    if digest(canonical(pose['pose_authority'])) != pose['pose_authority_digest']:
        raise ValueError('invalid pose authority digest')
    authority = pose['pose_authority']
    if not (authority['valid_from_utc_ns'] <= pose['capture_start_earliest_utc_ns']
            and pose['capture_end_utc_ns'] <= authority['valid_until_utc_ns']):
        raise ValueError('pose validity does not cover capture')


def select_subset(poses, count=12, calibration_count=8):
    ordered = sorted(poses, key=lambda p: (p['capture_start_earliest_utc_ns'], p['session_id']))
    selected = ordered[-count:]
    if len(selected) != count:
        raise ValueError('insufficient pose-linked captures for frozen design')
    return [dict(pose=p, split='calibration' if i < calibration_count else 'holdout')
            for i, p in enumerate(selected)]


def freeze():
    path = HERE / 'manifest.json'
    if path.exists():
        raise FileExistsError('frozen manifest already exists; do not reselect')
    poses = [json.loads(p.read_text()) for p in POSE.glob('*.json')]
    for pose in poses:
        validate_pose(pose)
    subset = select_subset(poses)
    out = dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
               selection='Newest 12 pose-linked completed captures by capture UTC; first 8 calibration, last 4 holdout. Incomplete analyses excluded without replacement.',
               corpus_pose_count=len(poses), sessions=subset)
    path.write_text(json.dumps(out, indent=2) + '\n')
    for item in subset:
        p = item['pose']
        print(item['split'], p['session_id'], datetime.fromtimestamp(p['capture_start_earliest_utc_ns']/1e9, timezone.utc).isoformat(), flush=True)


def prepare(manifest_name='manifest.json', inventory_name='inventory.json'):
    from leo.storage import BundleNotFoundError
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    manifest = json.loads((HERE / manifest_name).read_text())
    old_inventory = json.loads((HERE / 'inventory.json').read_text()) if (HERE / 'inventory.json').exists() else []
    if inventory_name != 'inventory.json' and (HERE / inventory_name).exists():
        old_inventory += json.loads((HERE / inventory_name).read_text())
    cached = {x['session_id']: x for x in old_inventory if x.get('ready')}
    output = HERE / 'cache'
    output.mkdir(exist_ok=True)
    source = ScannerTrackingInputStore(ROOT)
    captures = AdaptiveHopIqStore(ROOT, read_only=True)
    inventory = []
    try:
        for item in manifest['sessions']:
            p = item['pose']; sid = p['session_id']
            validate_pose(p)
            cap = captures.inspect(sid)
            if cap.manifest_sha256 != p['manifest_sha256']:
                raise ValueError(f'{sid}: pose/capture mismatch')
            if cap.manifest.receipt.radio_id != p['pose_authority']['radio_id']:
                raise ValueError(f'{sid}: pose radio does not match capture')
            entry = dict(session_id=sid, split=item['split'], pose_verified=True,
                         input_manifest_sha256=cap.manifest_sha256,
                         capture_start_utc_ns=p['capture_start_earliest_utc_ns'])
            try:
                if sid in cached:
                    cache_data = Path(cached[sid]['cache_file']).read_bytes()
                    if digest(cache_data) != cached[sid]['cache_sha256']:
                        raise ValueError('cache digest mismatch')
                    raw = pickle.loads(cache_data)
                else:
                    raw = source.load(sid)
            except BundleNotFoundError as exc:
                entry.update(ready=False, reason=str(exc))
            else:
                if not raw.qualified or raw.input_manifest_sha256 != cap.manifest_sha256:
                    raise ValueError(f'{sid}: unqualified or mismatched tracking input')
                probes = {(q.visit_index, q.probe_index, q.probe_start_ms, q.receiver_id): q for q in raw.probes}
                if len(probes) != len(raw.probes):
                    raise ValueError(f'{sid}: duplicate probes')
                visits = {q.visit_index for q in raw.probes}
                expected = {e.visit_index for e in cap.manifest.receipt.events}
                if visits != expected:
                    raise ValueError(f'{sid}: missing or unexpected visits')
                for q in raw.probes:
                    other = probes.get((q.visit_index, q.probe_index, q.probe_start_ms, 1-q.receiver_id))
                    if other is None or (q.channel, q.edge, q.valid_start_counter) != (other.channel, other.edge, other.valid_start_counter):
                        raise ValueError(f'{sid}: missing/non-simultaneous counterpart')
                data = cache_data if sid in cached else pickle.dumps(raw, protocol=5)
                path = output / f'{sid}.pickle'
                if path.exists() and path.read_bytes() != data:
                    raise ValueError(f'{sid}: immutable cache mismatch')
                if not path.exists():
                    path.write_bytes(data)
                entry.update(ready=True, visits=len(visits), probes=len(raw.probes),
                             sample_rate_hz=raw.sample_rate_hz,
                             analysis_manifest_sha256=raw.analysis_manifest_sha256,
                             cache_file=str(path), cache_sha256=digest(data))
            inventory.append(entry)
            (HERE / inventory_name).write_text(json.dumps(inventory, indent=2)+'\n')
            print(json.dumps(entry), flush=True)
    finally:
        source.close(); captures.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['freeze', 'prepare'])
    parser.add_argument('--manifest', default='manifest.json')
    parser.add_argument('--inventory', default='inventory.json')
    args = parser.parse_args()
    freeze() if args.action == 'freeze' else prepare(args.manifest, args.inventory)
