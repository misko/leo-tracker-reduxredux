"""Read-only full-IQ export for a pinned 2.5 MS/s adaptive capture.

Run in the maintained-server environment. Server GLRT inventories independently
verify these raw hashes before the staged data qualifies an ARM comparison.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np


def raw_visit(values):
    if values.dtype != np.dtype('<i2') or values.shape != (300000, 2, 2) or not values.flags.c_contiguous:
        raise ValueError('unsupported IQ dtype, geometry or layout')
    raw = values.tobytes(order='C')
    return raw, hashlib.sha256(raw).hexdigest()


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', required=True)
    p.add_argument('--manifest-digest', required=True)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    store = AdaptiveHopIqStore('/srv/bulk/leo', read_only=True)
    try:
        session = store.inspect(args.session)
        if session.manifest_sha256 != args.manifest_digest:
            raise ValueError('capture digest differs')
        manifest = session.manifest.model_dump(mode='json')
        geometry = manifest['receipt']['plan']['geometry']
        events = manifest['receipt']['events']
        if (geometry['sample_rate_hz'] != 2500000 or geometry['receiver_ids'] != [0, 1]
                or manifest['timing']['qualified'] is not True or not 1 <= len(events) <= 10000):
            raise ValueError('unsupported or unqualified capture')
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/'capture-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        entries = []
        started = time.monotonic()
        with store.reader(args.session, expected=session) as reader:
            for i, event in enumerate(events):
                if time.monotonic()-started > 300:
                    raise TimeoutError('bounded export exceeded 300 seconds')
                visit, values = reader.read_visit_ci16(i)
                if visit.event.model_dump(mode='json') != event or event['visit_index'] != i:
                    raise ValueError('visit authority differs')
                raw, digest = raw_visit(values)
                name = f'visit-{i:06d}.ci16'
                with (args.output/name).open('xb') as output:
                    output.write(raw)
                entries.append({'visit': i, 'event': event, 'path': name,
                                'size_bytes': len(raw), 'raw_sha256': digest})
                if len(entries) % 256 == 0:
                    print(json.dumps({'exported': len(entries)}), flush=True)
        (args.output/'inventory.json').write_text(json.dumps(entries, indent=2)+'\n')
        (args.output/'inputs.sha256').write_text(''.join(f"{r['raw_sha256']}  {r['path']}\n" for r in entries))
        receipt = {'status': 'complete', 'session': args.session,
                   'capture_digest': args.manifest_digest, 'visits': len(entries),
                   'bytes': sum(r['size_bytes'] for r in entries),
                   'wall_s': time.monotonic()-started,
                   'scope': 'Full recorded IQ, read-only source; independent server raw-hash comparison required'}
        (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps(receipt), flush=True)
    finally:
        store.close()


if __name__ == '__main__':
    main()
