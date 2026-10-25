"""Inventory two existing export schemas; no RF, orbit or location inference."""
import collections
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
BASE = Path('/srv/bulk/leo/research/ds25-20261024')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    document = json.loads(path.read_bytes())
    source = document['source']
    probes = source['probes']
    candidate_fields = collections.Counter()
    finite_fields = collections.Counter()
    candidates = 0
    for probe in probes:
        for candidate in probe['candidates']:
            candidates += 1
            candidate_fields.update(candidate.keys())
            finite_fields.update(key for key, value in candidate.items() if value is not None)
    assert all(count <= candidates for count in candidate_fields.values())
    assert source['sample_rate_hz'] == 10_000_000
    assert source['session_id'].startswith('fast-')
    return dict(path=str(path), sha256=digest(path), top_level_fields=sorted(document),
        source_fields=sorted(source), sample_rate_hz=source['sample_rate_hz'],
        probe_count=len(probes), candidate_count=candidates,
        probe_fields=sorted(set().union(*(set(p) for p in probes))),
        candidate_field_presence=dict(sorted(candidate_fields.items())),
        candidate_field_nonnull=dict(sorted(finite_fields.items())),
        clock_anchor_fields=sorted(document['clock_anchor']),
        clock_anchor_before_fields=sorted(document['clock_anchor']['before']),
        clock_anchor_after_fields=sorted(document['clock_anchor']['after']),
        source_timing_is_null=source.get('timing') is None,
        scope='Verified fast-session exported contract only; not all raw/companion authorities.')


if __name__ == '__main__':
    started = time.monotonic()
    paths = [REPO / name for name in (
        'src/leo/contracts/fast_scan.py',
        'src/leo/contracts/fast_scan_native.py',
        'src/leo/contracts/recording.py',
        'docs/operations/radio20-lt3d-004b-20261001.md')]
    rows = [inventory(BASE / case / 'tracking.json') for case in ('DS24-0010', 'DS24-0013')]
    result = dict(exports=rows, source_bindings={str(p): digest(p) for p in paths},
        script_sha256=digest(Path(__file__)), processing_seconds=time.monotonic()-started,
        new_RF=False, IQ_processing=False, orbit_propagation=False, position_fits=0,
        changes_to_originals=False)
    with (HERE / 'metadata_inventory.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'exports':len(rows), 'processing_seconds':result['processing_seconds'],
        'candidate_counts':[r['candidate_count'] for r in rows]}))
