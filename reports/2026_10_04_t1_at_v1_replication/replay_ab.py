"""Fresh A/B greedy + replacement replays using immutable refined discovery pools."""
import json
import math
import sys
from pathlib import Path
import numpy as np
from run import digest

LEGACY = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
OUT = Path('/srv/bulk/leo/t1-at-v1-replication-20261004/replayed-ab-verified')


def replay(scan):
    target = OUT/scan
    if (target/'summary.json').exists():
        return json.loads((target/'summary.json').read_text())
    folder = LEGACY/('full-scan-A-refinement/top-one' if scan == 'A' else 'position-top-2km/B-top')
    source = folder/'candidate-pool.json'
    pool = json.loads(source.read_text())
    for path, expected in pool['sources'].items():
        assert digest(Path(path).read_bytes()).removeprefix('sha256:') == expected.removeprefix('sha256:'), path
    sys.path.insert(0, str(LEGACY))
    from penalty_replace_search import Search
    from greedy_restart_scan import compile_mode
    from replay import ROOT
    original = np.asarray(pool['original_rows'], int)
    with np.load(ROOT/f'frozen/{scan}-observations.npz') as z:
        groups, times, receivers, channels = [z[k][original] for k in ('group','times_s','receiver','channel')]
    assert len(set(groups)) == len(original) == len(set(original))
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms']['fitted-c']] == [(m['catalog_number'],m['offset_s']) for m in pool['arms']['zero-c']]
    target.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for arm in ('fitted-c','zero-c'):
        historical=json.loads((folder/f'{arm}.json').read_text())
        result=Search([compile_mode(m,receivers,channels) for m in pool['arms'][arm]],groups,times).run(3)
        for stage in ('initial','final'):
            r=result[stage]
            for a in r['assignments']: a['row_index']=int(original[a['row_index']])
            r.update(coverage=r['assigned']/len(original),unassigned=len(original)-r['assigned'])
            # A also archived a fraction of *all alternative hypotheses*.
            # This is not the top-window coverage denominator used here.
            assert all(value == historical[stage][key] for key,value in r.items()), (scan,arm,stage)
        r=result['final']
        summary=dict(scan=scan,arm=arm,denominator=len(original),assigned=r['assigned'],
            coverage=r['coverage'],unassigned=r['unassigned'],satellites=r['satellites'],
            rms_hz=math.sqrt(np.mean([a['residual_hz']**2 for a in r['assignments']])),
            objective=r['objective'],accepted_replacements=sum(p['accepted'] for p in result['passes']),
            exact_historical_stages_match=True)
        result.update(summary=summary,source=str(source),source_sha256=digest(source.read_bytes()),
                      scope=__doc__,upstream_source_hashes_verified=len(pool['sources']))
        (target/f'{arm}.json').write_text(json.dumps(result,indent=2,allow_nan=False))
        summaries.append(summary)
    (target/'summary.json').write_text(json.dumps(summaries,indent=2,allow_nan=False))
    return summaries


if __name__ == '__main__':
    for scan in ('A','B'): print(json.dumps(replay(scan)),flush=True)
