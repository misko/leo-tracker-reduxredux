"""Within-dwell standard-CFO agreement; nearest-bank coverage, not recovery."""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'


def differences(probes, gap):
    banks = {(p['receiver_id'], p['probe_index']):
             [c['tracking_cfo_hz'] for c in p['candidates'] if c['passed_margin_gate']]
             for p in probes}
    errors = []
    total = missing = 0
    for (rx, window), current in banks.items():
        if window < gap:
            continue
        previous = banks.get((rx, window-gap), [])
        total += len(current)
        if not previous:
            missing += len(current)
        else:
            errors.extend(min(abs(f-old) for old in previous) for f in current)
    return errors, total, missing


def summarize(errors, total, missing):
    a = np.asarray(errors)
    return {'later_positive_entries': total, 'no_prior_positive_entries': missing,
            'entries_with_prior_bank': len(errors),
            'absolute_delta_hz_quantiles': dict(zip(('median', 'p90', 'p95', 'p99', 'max'),
                map(float, np.quantile(a, [.5, .9, .95, .99, 1])))) if len(a) else {},
            'within_hz': {str(t): int(np.count_nonzero(a <= t)) for t in (100, 500, 1000, 2000, 8000, 20000)}}


def main():
    bins = {}
    dwells = 0
    for line in SOURCE.read_text().splitlines():
        row = json.loads(line)
        if row['method'] != 'original' or row['repeat'] != 0:
            continue
        assert row['status'] == 'ok'
        probes = row['result']['probes']
        assert len(probes) == 22
        dwells += 1
        for gap in (1, 2, 5, 10):
            errors, total, missing = differences(probes, gap)
            for rate in ('all', str(row['context']['rate_hz'])):
                b = bins.setdefault((rate, gap), [[], 0, 0])
                b[0].extend(errors); b[1] += total; b[2] += missing
    result = {'scope': 'Nearest positive tracking-CFO in an earlier window of the same receiver and dwell. Many-to-one, no timing/identity gate; no CFO-distance prefilter. Not physical drift, GLRT recovery, or a causal detector.',
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'dwells': dwells,
              'by_rate': {rate: {str(gap*10): summarize(*bins[(rate,gap)]) for gap in (1,2,5,10)}
                          for rate in ('all','2500000','5000000','7500000','10000000')}}
    (HERE/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['by_rate']['2500000'], indent=2))


if __name__ == '__main__':
    main()
