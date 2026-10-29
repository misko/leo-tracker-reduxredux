"""Freeze eligible unused public fast exports without reading evaluation truth."""
import argparse
from collections import Counter
import hashlib
import itertools
from pathlib import Path

from debug_fast_graph_unassociated import read, write
from leo.storage.fast_graph_position import FastGraphPositionStore


def eligible(tracks, owned):
    rows = [t for t in tracks if t['channel'] in (7, 8)
            and len(t['times']) >= 20 and max(t['times'])-min(t['times']) >= 24
            and not set(t['observation_ids']) & owned]
    pairs = [(a['key'], b['key']) for a, b in itertools.combinations(rows, 2)
             if a['receiver'] == b['receiver'] and a['channel'] != b['channel']
             and min(max(a['times']), max(b['times']))-max(min(a['times']), min(b['times'])) >= 20]
    return dict(tracks=[dict(component=t['key'], points=len(t['times'])) for t in rows], pairs=pairs)


def identity(source):
    # Session names change between dataset and automatic export; raw authority
    # must also match when excluding an already used recording.
    return {source[k] for k in ('session_id', 'raw_recording_authority_digest', 'input_manifest_sha256') if source.get(k)}


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    old = read(args.study/'combined-reentry/protocol.json')
    roots = [(Path(old['root']), c) for c in old['primary_cases']+old['remaining_cases']]
    separate = read(args.study/'separate-fast-validation/protocol.json')
    roots += [(Path(separate['root']), c) for c in separate['cases']]
    roots += [(args.pilot/'run/inference', 'SCAN')]
    excluded = set()
    for root, c in roots:
        excluded.update(identity(read(root/c/'tracking.json')['source']))
    store = FastGraphPositionStore(args.bulk_root)
    rows = []; seen = set()
    for job in store.inputs():
        status = store.status(job['job_id'])
        row = dict(job_id=job['job_id'], input_sha256=job['input_sha256'],
                   status=status['state'] if status else 'unprocessed')
        if row['status'] != 'complete':
            rows.append(row); continue
        terminal, artifact = store.terminal(job)
        source = read(job['input_path'])['source']; ids = identity(source)
        row.update(session_id=source['session_id'], sample_rate_hz=source['sample_rate_hz'],
                   excluded=bool(ids & excluded), duplicate=bool(ids & seen),
                   raw_authority=source.get('raw_recording_authority_digest'),
                   artifact=artifact, capture_mode_label=source.get('capture_mode'))
        seen.update(ids)
        if row['sample_rate_hz'] == 10_000_000 and not row['excluded'] and not row['duplicate']:
            root = Path(artifact['path']).parent/'inference'
            tracks = read(root/'SCAN/tracks.json')
            owned = {o for arm in terminal['arms'].values() for t in arm['gates']['tracks']+arm.get('linear_gates', [])
                     for o in t.get('observation_ids', [])}
            row.update(root=str(root), eligibility=eligible(tracks, owned),
                       captured_utc_ns=read(root/'SCAN/prepared.json')['metadata']['anchor_utc_ns'])
            # The public export labels short-window fast data "adaptive".
            # Verify actual acquisition format through the fast report port.
            report = store.inputs_port.detail(job['run_id'], include_points=False)
            row['fast_report_recording_id'] = report.get('recording_id')
            row['report_scalar_metadata'] = {k:v for k,v in report.items() if not isinstance(v, (dict, list))}
        rows.append(row)
    candidates = [r for r in rows if r.get('eligibility', {}).get('tracks')]
    # Freeze an affordable all-pairs-first, largest-target-first panel before
    # recovery or position evaluation. No endpoint/error participates.
    candidates.sort(key=lambda r:(-bool(r['eligibility']['pairs']),
                                  -sum(t['points'] for t in r['eligibility']['tracks']), r['job_id']))
    selected = candidates[:8]
    write(args.output/'inventory.json', dict(rows=rows, excluded_identities=sorted(excluded),
          states=dict(Counter(r['status'] for r in rows)), selected=selected,
          selection='up to eight unused complete 10 MS/s public fast exports: pairs first, then eligible point count, job ID tie break',
          no_GPS_selection=True, production_changed=False,
          source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print('states', Counter(r['status'] for r in rows), 'eligible', len(candidates), 'selected', len(selected), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','pilot','bulk-root','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
