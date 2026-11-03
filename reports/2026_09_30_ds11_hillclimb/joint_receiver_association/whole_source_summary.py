"""Unseal the whole-source pilot after all original cells and retry terminate."""
import json
from pathlib import Path
import sys
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / '2026_09_30_ds11_single10'))
from summarize import distance


def main():
    jobs = [('original', 0), ('original', 16), ('additional', 1)]
    sources, rows = {}, []
    for cohort, index in jobs:
        for arm in ('doppler', 'signed'):
            assert (HERE / f'whole-{cohort}-{index:02d}-{arm}.receipt.json').exists()
    assert (HERE / 'whole-original-00-signed.retry.receipt.json').exists()
    for cohort, index in jobs:
        base = HERE.parent.parent / '2026_09_30_ds11_single10' if cohort == 'original' else HERE.parent / 'additional'
        original_path = base / f'runs/{index:02d}_iid.json'
        sources[str(original_path)] = digest(original_path)
        rows.append(dict(cohort=cohort, index=index, arm='original', qualified=True, distance_m=distance(read(original_path)['selected']['estimate_deg'])))
        for arm in ('doppler', 'signed'):
            prefix = HERE / f'whole-{cohort}-{index:02d}-{arm}'
            receipt_path = prefix.with_suffix('.receipt.json')
            receipt = read(receipt_path)
            sources[str(receipt_path)] = digest(receipt_path)
            retry = cohort == 'original' and index == 0 and arm == 'signed'
            if retry:
                path = HERE / 'whole-original-00-signed.retry.json'
                retry_receipt = HERE / 'whole-original-00-signed.retry.receipt.json'
                code = read(retry_receipt)['exit_code']
                sources[str(retry_receipt)] = digest(retry_receipt)
            else:
                path = prefix.with_suffix('.json')
                code = receipt['exit_code']
            if code or not path.exists():
                rows.append(dict(cohort=cohort, index=index, arm=arm, qualified=False, distance_m=None, exit_code=code, original_exit_code=receipt['exit_code']))
                continue
            result = read(path)
            for p, h in result['sources'].items():
                assert digest(p) == h, p
            sources[str(path)] = digest(path)
            rows.append(dict(cohort=cohort, index=index, arm=arm, qualified=result['qualified'], distance_m=distance(result['coordinates_deg']), score=result['score'], held_score=result['held_score'], expected_sources=result['expected_sources'], elapsed_s=result['elapsed_s'], engineering_continuation=retry, original_exit_code=receipt['exit_code']))
    lookup = {(r['cohort'], r['index'], r['arm']): r for r in rows}
    passed = all(lookup[c, i, 'signed']['qualified'] and lookup[c, i, 'doppler']['qualified'] and all(lookup[c, i, 'signed']['distance_m'] < lookup[c, i, a]['distance_m'] for a in ('original', 'doppler')) for c, i in jobs)
    sources[str(Path(__file__))] = digest(Path(__file__))
    output = dict(rows=rows, pilot_passed=bool(passed), original_attempts=6, original_timeouts=1, engineering_retries=1, sources=sources, scope='three previously examined recordings; complete-source grouping, original candidate banks')
    with (HERE / 'whole-source-summary.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=rows, passed=bool(passed)), indent=2))


if __name__ == '__main__':
    main()
