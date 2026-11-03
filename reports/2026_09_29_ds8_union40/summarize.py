"""Audit frozen fit outputs and summarize the declared two-start experiment."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = [37.849056280893684, -122.48575489722863]


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*6371008.8*math.asin(min(1, math.sqrt(h)))


def main():
    results = [json.loads((HERE/f'{a}.json').read_text()) for a in ['old', 'rank']]
    for result in results:
        for path, digest in result['hashes'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
        assert len(set(result['sessions'])) == 40
        assert result['fit']['qualified']
        for key, fit_key in [('training', 'score'), ('held', 'held_score')]:
            assert abs(sum(g[key] for g in result['groups'])-result['fit'][fit_key]) < 1e-7
    assert results[0]['sessions'] == results[1]['sessions']
    selected = max(results, key=lambda r: r['fit']['score'])
    groups = []
    for g in selected['groups']:
        groups.append(dict(group=g['group'], scans=g['scans'], deltas={
            a: {k: g[k]-g['controls'][a][k] for k in ['training', 'held']}
            for a in ['old', 'rank']}))
    summary = dict(
        selected_start=selected['start_arm'], reference_deg=REFERENCE,
        endpoint_gap_m=distance(*[r['fit']['estimate_deg'] for r in results]),
        starts=[dict(start=r['start_arm'], reference_distance_m=distance(r['fit']['estimate_deg'], REFERENCE),
                     training=r['fit']['score'], held=r['fit']['held_score'],
                     elapsed_seconds=r['elapsed_seconds']) for r in results],
        groups=groups,
        union_deltas={a: {k: sum(g['deltas'][a][k] for g in groups) for k in ['training', 'held']}
                      for a in ['old', 'rank']},
        hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [HERE/'old.json', HERE/'rank.json', Path(__file__)]})
    (HERE/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
