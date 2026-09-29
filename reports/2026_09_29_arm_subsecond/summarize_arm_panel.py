"""Summarize measured per-dwell CPU distributions; never extrapolate rates."""
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


def summarize(folder):
    manifest_path = folder/'manifest.json'
    rows_path = folder/'rows.jsonl'
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    assert manifest['complete'] and digest == manifest['rows_sha256']
    records = [json.loads(line) for line in rows_path.read_text().splitlines()]
    assert len(records) == manifest['processed_dwells']
    groups = {}
    for record in records:
        assert record['returncode'] == 0 and len(record['rows']) == 22
        times = [row['timings_ms']['fused_total'] for row in record['rows']]
        assert all(math.isfinite(x) and x >= 0 for x in times)
        groups.setdefault(str(record['context']['rate_hz']), []).append(sum(times))
    output = {}
    for rate, values in groups.items():
        ordered = sorted(values)
        output[rate] = {
            'dwells': len(values), 'windows': 22*len(values),
            'mean_ms': statistics.mean(values), 'median_ms': statistics.median(values),
            'p95_ms': ordered[math.ceil(0.95*len(ordered))-1],
            'min_ms': ordered[0], 'max_ms': ordered[-1],
            'under_one_second': sum(x < 1000 for x in values),
            'within_120ms': sum(x <= 120 for x in values),
        }
    return {
        'scope': 'Measured CPU time per complete dual-RX dwell; all 22 windows; '
                 'file reads, initial setup and simultaneous capture excluded',
        'percentile_method': 'nearest rank', 'by_rate': output,
        'rows_sha256': digest,
        'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cohort', type=Path)
    args = parser.parse_args()
    result = summarize(args.cohort)
    (args.cohort/'cpu-distribution.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['by_rate'], indent=2))
