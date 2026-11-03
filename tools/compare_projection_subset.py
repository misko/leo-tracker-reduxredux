"""Compare emitted observation/support checkpoints without hiding dropped rows."""
import argparse
import json
from pathlib import Path

from leo.native_pipeline.runner import digest, write_json


def compare_lines(actual, reference, header_lines):
    if header_lines not in (1, 2) or len(reference) <= header_lines or len(actual) < header_lines:
        raise ValueError('missing checkpoint headers or reference rows')
    def index(lines):
        result = {}
        for row in lines[header_lines:]:
            key, separator, _ = row.partition('\t')
            if not key or not separator or key in result:
                raise ValueError('invalid or duplicate candidate ID')
            result[key] = row
        return result
    a, r = index(actual), index(reference)
    mismatch = sorted(key for key, value in a.items() if r.get(key) != value)
    missing = sorted(r.keys() - a.keys())
    headers = actual[:header_lines] == reference[:header_lines]
    positions = {key: i for i, key in enumerate(r)}
    order = [positions[key] for key in a if key in positions]
    ordered_subset = len(order) == len(a) and order == sorted(order)
    return {'headers_exact': headers, 'rows': len(a), 'reference_rows': len(r),
            'all_emitted_rows_exact': headers and not mismatch,
            'ordered_subset': ordered_subset,
            'complete_exact': headers and not mismatch and not missing and ordered_subset,
            'mismatched_or_unexpected_ids': mismatch, 'missing_reference_ids': missing}


def compare_checkpoints(actual, reference):
    results = {}
    ids = {}
    for name, headers in [('observations.tsv', 1), ('graph.tsv', 2)]:
        a, r = actual / name, reference / name
        lines = a.read_text().splitlines()
        results[name] = compare_lines(lines, r.read_text().splitlines(), headers)
        results[name]['input_sha256'] = {'actual': digest(a), 'reference': digest(r)}
        ids[name] = [row.split('\t', 1)[0] for row in lines[headers:]]
    results['observation_support_ids_exact'] = ids['observations.tsv'] == ids['graph.tsv']
    results['emitted_science_exact'] = results['observation_support_ids_exact'] and all(
        results[name]['all_emitted_rows_exact'] for name in ids)
    results['complete_exact'] = results['emitted_science_exact'] and all(
        results[name]['complete_exact'] for name in ids)
    results['scope'] = 'Projection checkpoint comparison; incomplete subsets never qualify lossless replay'
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('actual', 'reference', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    result = compare_checkpoints(args.actual, args.reference)
    write_json(args.output, result)
    print(json.dumps({k: result[k] for k in ('emitted_science_exact', 'complete_exact')}))
    if not result['complete_exact']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
