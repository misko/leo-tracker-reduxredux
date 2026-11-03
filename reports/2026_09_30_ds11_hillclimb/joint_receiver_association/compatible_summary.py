"""Score every frozen compatible fit, retaining failures in denominators."""
import json
from pathlib import Path
import sys
import numpy as np
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / '2026_09_30_ds11_single10'))
from summarize import distance


def main():
    receipt_path = HERE / 'compatible-run.json'
    receipt = read(receipt_path)
    assert len(receipt['receipts']) == 20
    sources = {str(receipt_path): digest(receipt_path), str(Path(__file__)): digest(Path(__file__))}
    rows = []
    indices = [0, 4, 9, 16, 19, 20]
    arms = ['original', 'doppler', 'receiver', 'signed', 'swapped', 'permuted']
    for i in indices:
        original = HERE.parent.parent / '2026_09_30_ds11_single10' / 'runs' / f'{i:02d}_iid.json'
        old = read(original)['selected']
        sources[str(original)] = digest(original)
        rows.append(dict(index=i, arm='original', qualified=bool(old), distance_m=distance(old['estimate_deg']) if old else None))
        for arm in arms[1:]:
            path = HERE / f'position-{i:02d}-{arm}.json'
            if not path.exists():
                rows.append(dict(index=i, arm=arm, qualified=False, distance_m=None, status='missing_or_failed'))
                continue
            result = read(path)
            sources[str(path)] = digest(path)
            for p, h in result['sources'].items():
                assert digest(p) == h, p
            rows.append(dict(index=i, arm=arm, qualified=result['qualified'], distance_m=distance(result['coordinates_deg']), score=result['score'], held_score=result['held_score'], expected_pairs=result['expected_pairs'], elapsed_s=result['elapsed_s']))
    lookup = {(r['index'], r['arm']): r for r in rows}
    metrics = {}
    for name, cohort in [('all_six', indices), ('four_extension', [4, 9, 19, 20])]:
        metrics[name] = {}
        for arm in arms:
            good = [lookup[i, arm] for i in cohort if lookup[i, arm]['qualified']]
            errors = [r['distance_m'] for r in good]
            metrics[name][arm] = dict(qualified=len(good), attempted=len(cohort), median_m=float(np.median(errors)) if errors else None, mean_m=float(np.mean(errors)) if errors else None, p90_m=float(np.percentile(errors, 90)) if errors else None, below_1km=sum(v < 1000 for v in errors), wins_vs_doppler=sum(lookup[i, arm]['qualified'] and lookup[i, 'doppler']['qualified'] and lookup[i, arm]['distance_m'] < lookup[i, 'doppler']['distance_m'] for i in cohort))
    a, b = metrics['all_six']['signed'], metrics['all_six']['doppler']
    passed = a['qualified'] == b['qualified'] == 6 and a['wins_vs_doppler'] >= 4 and a['median_m'] <= .9 * b['median_m'] and a['p90_m'] <= b['p90_m']
    result = dict(rows=rows, metrics=metrics, compatible_gate_passed=bool(passed), sources=sources, reference='unsurveyed roof reference', scope='six exact RF/rate matches among 32 original DS11 scans')
    with (HERE / 'compatible-summary.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=rows, metrics=metrics, passed=bool(passed)), indent=2))


if __name__ == '__main__':
    main()
