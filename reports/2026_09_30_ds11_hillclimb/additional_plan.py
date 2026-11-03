"""Freeze timestamp-only additional DS11 replication before challenger results."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '2026_09_30_ds11_single10'
MANIFEST = HERE.parent / '2026_09_30_ds11_post_ds10/local/manifest.json'


def select(captures, excluded, count=12):
    available = sorted((r for r in captures if r['session_id'] not in excluded),
                       key=lambda r: (r['capture_start_utc_ns'], r['session_id']))
    if len(available) < count or count < 2:
        raise ValueError('Insufficient additional recordings')
    ranks = [i*(len(available)-1)//(count-1) for i in range(count)]
    return [available[i] for i in ranks]


def main():
    original = json.loads((BASE/'plan.json').read_text())
    captures = json.loads(MANIFEST.read_text())['captures']
    excluded = {r['session_id'] for r in original['inputs']}
    selected = select(captures, excluded)
    document = dict(purpose='Additional-scan replication; interleaved in time, same exposed site',
                    count=len(selected), original_count=len(excluded), captures=selected,
                    selection='Twelve floor(i*(N-1)/11) ranks of the remaining55; no outcome selection',
                    config=original['config'],
                    source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [MANIFEST, BASE/'plan.json', Path(__file__)]})
    with (HERE/'additional-plan.json').open('x') as stream:
        json.dump(document, stream, indent=2)
    print('Frozen', len(selected), 'additional recordings')


if __name__ == '__main__':
    main()
