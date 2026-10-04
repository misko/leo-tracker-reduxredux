"""Fresh historical Scan B selection; reuse the frozen discovery/calibration pool.

Does not rerun IQ refinement, orbit discovery, calibration, or position fitting.
Writes a new directory, never overwriting the historical reference.
"""
import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


LEGACY = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    source = LEGACY / 'position-top-2km/B-top/candidate-pool.json'
    pool = json.loads(source.read_text())
    for name, expected in pool['sources'].items():
        if digest(Path(name)) != expected.removeprefix('sha256:'):
            raise ValueError(f'Historical source changed: {name}')
    modes = [[(r['catalog_number'], r['offset_s']) for r in pool['arms'][a]]
             for a in ('fitted-c', 'zero-c')]
    assert modes[0] == modes[1], 'RF arms must share timing/identity candidates'
    sys.path.insert(0, str(LEGACY))
    from penalty_replace_search import Search
    from greedy_restart_scan import compile_mode
    from replay import ROOT

    original = np.asarray(pool['original_rows'], dtype=int)
    frozen = ROOT / 'frozen/B-observations.npz'
    with np.load(frozen, allow_pickle=False) as arrays:
        groups = arrays['group'][original]
        times = arrays['times_s'][original]
        receivers = arrays['receiver'][original]
        channels = arrays['channel'][original]
    assert len(original) == len(set(original)) == len(set(groups)) == 3602
    refined = json.loads((LEGACY / 'position-top-2km/B-refinement/refined.json').read_text())
    winners = {}
    for row in refined['records']:
        key = tuple(row['probe_key'])
        priority = (row['refinement'].get('margin', row['original_margin']), -row['row_index'])
        if key not in winners or priority > winners[key][0]:
            winners[key] = (priority, row['row_index'])
    assert set(original) == {v[1] for v in winners.values()}
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for arm in ('fitted-c', 'zero-c'):
        historical_path = source.parent / f'{arm}.json'
        historical = json.loads(historical_path.read_text())
        assert historical['source_sha256'].removeprefix('sha256:') == digest(source)
        compiled = [compile_mode(r, receivers, channels) for r in pool['arms'][arm]]
        result = Search(compiled, groups, times).run(3)
        for stage in ('initial', 'final'):
            value = result[stage]
            for assigned in value['assignments']:
                assigned['row_index'] = int(original[assigned['row_index']])
            value.update(coverage=value['assigned']/len(original),
                         unassigned=len(original)-value['assigned'])
            assert len({a['row_index'] for a in value['assignments']}) == value['assigned']
            assert value['objective'] == value['assigned'] - 10*value['satellites']
        exact = all(result[stage] == historical[stage] for stage in ('initial', 'final'))
        final = result['final']
        summary = dict(arm=arm, denominator=len(original), greedy_assigned=result['initial']['assigned'],
                       assigned=final['assigned'], unassigned=final['unassigned'],
                       coverage=final['coverage'], satellites=final['satellites'], objective=final['objective'],
                       rms_hz=math.sqrt(sum(a['residual_hz']**2 for a in final['assignments'])/final['assigned']),
                       accepted_replacements=sum(p['accepted'] for p in result['passes']),
                       exact_historical_stages_match=exact, elapsed_s=result['elapsed_s'])
        result.update(scan='B', session_id=pool['scan'], arm=arm, summary=summary,
                      scope=__doc__, timestamp_utc=datetime.now(timezone.utc).isoformat(),
                      sources={str(p):digest(p) for p in (source, historical_path, frozen, Path(__file__),
                               LEGACY/'penalty_replace_search.py', LEGACY/'greedy_restart_scan.py')},
                      upstream_source_hashes_verified=len(pool['sources']))
        with (output/f'{arm}.json').open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    with (output/'summary.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    assert all(s['exact_historical_stages_match'] for s in summaries), 'Replay differs: inspect saved outputs'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
