"""Separate confirmation scoring after all five frozen fits are sealed."""
import json
from pathlib import Path
import sys
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / '2026_09_30_ds11_single10'))
from summarize import distance


def main():
    arms = ('doppler', 'receiver', 'signed', 'swapped', 'permuted')
    sources = {str(Path(__file__)): digest(Path(__file__))}
    receipts = {}
    for arm in arms:
        path = HERE / f'additional-01-{arm}.receipt.json'
        receipts[arm] = read(path)
        sources[str(path)] = digest(path)
    original_path = HERE.parent / 'additional/runs/01_iid.json'
    original = read(original_path)['selected']
    sources[str(original_path)] = digest(original_path)
    rows = [dict(arm='original', qualified=True, distance_m=distance(original['estimate_deg']))]
    for arm in arms:
        path = HERE / f'additional-01-{arm}.json'
        if receipts[arm]['exit_code'] != 0 or not path.exists():
            rows.append(dict(arm=arm, qualified=False, distance_m=None, exit_code=receipts[arm]['exit_code']))
            continue
        result = read(path)
        for p, h in result['sources'].items():
            assert digest(p) == h, p
        sources[str(path)] = digest(path)
        rows.append(dict(arm=arm, qualified=result['qualified'], distance_m=distance(result['coordinates_deg']), score=result['score'], held_score=result['held_score'], expected_pairs=result['expected_pairs'], elapsed_s=result['elapsed_s']))
    lookup = {r['arm']: r for r in rows}
    passed = lookup['signed']['qualified'] and lookup['doppler']['qualified'] and all(lookup['signed']['distance_m'] < lookup[a]['distance_m'] for a in ('original', 'doppler'))
    output = dict(rows=rows, confirmation_passed=bool(passed), sources=sources, reference='unsurveyed roof reference', scope='one exact RF/rate match among separate 12 recordings')
    with (HERE / 'additional-summary.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=rows, passed=bool(passed)), indent=2))


if __name__ == '__main__':
    main()
