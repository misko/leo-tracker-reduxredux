"""Score the fully sealed time-aware experiment, including failed cells."""
import json
from pathlib import Path
import sys
import numpy as np
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / '2026_09_30_ds11_single10'))
from summarize import distance


def main():
    jobs = [('original', i) for i in (0, 4, 9, 16, 19, 20)] + [('additional', 1)]
    arms = ('receiver', 'signed', 'swapped', 'permuted')
    sources = {str(Path(__file__)): digest(Path(__file__)), str(HERE / 'SEQUENCE_POSITION_PROTOCOL.md'): digest(HERE / 'SEQUENCE_POSITION_PROTOCOL.md')}
    for cohort, index in jobs:
        for arm in arms:
            path = HERE / f'sequence-{cohort}-{index:02d}-{arm}.receipt.json'
            assert path.exists()
    rows = []
    for cohort, index in jobs:
        base = HERE.parent.parent / '2026_09_30_ds11_single10' if cohort == 'original' else HERE.parent / 'additional'
        original_path = base / f'runs/{index:02d}_iid.json'
        original = read(original_path)['selected']
        sources[str(original_path)] = digest(original_path)
        rows.append(dict(cohort=cohort, index=index, arm='original', qualified=True, distance_m=distance(original['estimate_deg'])))
        baseline_path = HERE / (f'position-{index:02d}-doppler.json' if cohort == 'original' else 'additional-01-doppler.json')
        baseline = read(baseline_path)
        sources[str(baseline_path)] = digest(baseline_path)
        rows.append(dict(cohort=cohort, index=index, arm='doppler', qualified=baseline['qualified'], distance_m=distance(baseline['coordinates_deg'])))
        for arm in arms:
            prefix = HERE / f'sequence-{cohort}-{index:02d}-{arm}'
            receipt = read(prefix.with_suffix('.receipt.json'))
            sources[str(prefix.with_suffix('.receipt.json'))] = digest(prefix.with_suffix('.receipt.json'))
            if receipt['exit_code'] or not prefix.with_suffix('.json').exists():
                rows.append(dict(cohort=cohort, index=index, arm=arm, qualified=False, distance_m=None, exit_code=receipt['exit_code']))
                continue
            result = read(prefix.with_suffix('.json'))
            sources[str(prefix.with_suffix('.json'))] = digest(prefix.with_suffix('.json'))
            for p, h in result['sources'].items():
                assert digest(p) == h, p
            rows.append(dict(cohort=cohort, index=index, arm=arm, qualified=result['qualified'], distance_m=distance(result['coordinates_deg']), score=result['score'], held_score=result['held_score'], expected_pairs=result['expected_pairs'], elapsed_s=result['elapsed_s']))
    lookup = {(r['cohort'], r['index'], r['arm']): r for r in rows}
    metrics = {}
    for arm in ('original', 'doppler', *arms):
        good = [r for r in rows if r['arm'] == arm and r['qualified']]
        errors = [r['distance_m'] for r in good]
        metrics[arm] = dict(qualified=len(good), attempted=7, median_m=float(np.median(errors)) if errors else None, p90_m=float(np.percentile(errors, 90)) if errors else None, mean_m=float(np.mean(errors)) if errors else None, wins_vs_doppler=sum(lookup[c, i, arm]['qualified'] and lookup[c, i, arm]['distance_m'] < lookup[c, i, 'doppler']['distance_m'] for c, i in jobs))
    signed, baseline = metrics['signed'], metrics['doppler']
    gates = dict(all_primary_qualified=signed['qualified'] == baseline['qualified'] == 7, wins=signed['wins_vs_doppler'] >= 5, median=signed['median_m'] <= .9 * baseline['median_m'] if signed['median_m'] is not None else False, tail=signed['p90_m'] <= baseline['p90_m'] if signed['p90_m'] is not None else False, additional=lookup['additional', 1, 'signed']['qualified'] and lookup['additional', 1, 'signed']['distance_m'] <= lookup['additional', 1, 'doppler']['distance_m'])
    output = dict(rows=rows, metrics=metrics, gates=gates, passed=all(gates.values()), sources=sources, scope='seven previously examined compatible records; no fresh blind holdout')
    with (HERE / 'sequence-summary.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=rows, metrics=metrics, gates=gates, passed=output['passed']), indent=2))


if __name__ == '__main__':
    main()
