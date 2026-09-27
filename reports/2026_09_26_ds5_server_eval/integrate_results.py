"""Normalize worker outputs and replay measured costs on recorded arrivals.

Separate worker builds keep their own baselines. This report never treats
cross-build timings or unsupported-rate absence as detector equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

from evaluation_core import Candidate, VisitJob, compare_cases, replay_serial_worker


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def search_rows(receipt):
    rows = []
    for row in receipt['rows']:
        candidates = [Candidate(bool(c['fractional_complete']), c['margin'],
                                c['tracking_cfo_hz'],
                                (c['epoch'] + c['fractional_offset_samples']) / row['rate_hz'],
                                c['window_index'])
                      for c in row['representative']['candidates']]
        rows.append(dict(case_id=row['case_id'], rx=row['rx'], method=row['variant'],
                         candidates=candidates, service_ms=row['timing_median']['wall_ms']))
    return rows, 'baseline_blind_512'


def band_rows(receipt):
    rows = []
    for row in receipt['rows']:
        detection = row['detection']
        candidates = []
        if detection['source_time_seconds'] is not None:
            candidates = [Candidate(bool(detection['fractional_complete']
                                          and detection['supported']),
                                    detection['margin'], detection['cfo_hz'],
                                    detection['source_time_seconds'], detection['window'])]
        if detection.get('evaluation_status') == 'unknown_unsupported_boundary':
            candidates = None
        rows.append(dict(case_id=row['case_id'], rx=row['receiver'], method=row['method'],
                         candidates=candidates, service_ms=median(row['timing_wall_ms'])))
    return rows, 'native_rate'


def integrate(cases, receipt, kind):
    rows, baseline_name = search_rows(receipt) if kind == 'search' else band_rows(receipt)
    subset = [c for c in cases if c['split'] == receipt['split']]
    expected = {(c['case_id'], rx) for c in subset for rx in range(2)}
    indexed = {}
    for row in rows:
        key = (row['case_id'], row['rx'])
        method_rows = indexed.setdefault(row['method'], {})
        if key not in expected or key in method_rows:
            raise ValueError('duplicate or unexpected result row')
        method_rows[key] = row
    baseline = indexed.get(baseline_name, {})
    methods = {}
    for method, method_rows in indexed.items():
        strata = {}
        for origin in sorted({c['origin'] for c in subset}):
            for rate in sorted({c['rate_hz'] for c in subset if c['origin'] == origin}):
                keys = [(c['case_id'], rx) for c in subset
                        if c['origin'] == origin and c['rate_hz'] == rate for rx in range(2)]
                reference = {k: baseline[k]['candidates'] if k in baseline else None for k in keys}
                proposed = {k: method_rows[k]['candidates'] if k in method_rows else None
                            for k in keys}
                strata[f'{origin}:{rate}'] = compare_cases(reference, proposed)
        real = sorted((c for c in subset if c['origin'] == 'real_ds5'),
                      key=lambda c: (c['session_id'], c['source_start_counter']))
        origins = {}
        jobs = []
        for case in real:
            session = case['session_id']
            origin = origins.setdefault(session, case['source_start_counter'])
            keys = [(case['case_id'], rx) for rx in range(2)]
            complete = all(key in method_rows for key in keys)
            costs = tuple(method_rows[k]['service_ms'] for k in keys) if complete else ()
            jobs.append(VisitJob(session, case['visit_index'],
                                 (case['source_start_counter'] - origin) / case['rate_hz'],
                                 (case['source_end_counter_exclusive'] - origin) / case['rate_hz'],
                                 costs, complete))
        methods[method] = {'by_origin_and_rate': strata,
                           'arrival_replay': replay_serial_worker(jobs)}
    return {'split': receipt['split'], 'baseline': baseline_name, 'methods': methods,
            'limitations': ['real data reference-relative retention is not truth recall',
                            'service costs are desktop medians, not ARM forecasts',
                            'short recorded blocks begin with an empty queue',
                            'high-rate baseline absence is explicit unknown',
                            'synthetic known-truth scoring remains in worker reports']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--kind', choices=('search', 'band'), required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    receipt = json.loads(args.receipt.read_text())
    expected_dataset_hash = receipt.get('dataset_cases_sha256',
                                        receipt.get('dataset_manifest_sha256'))
    if expected_dataset_hash is None or (
            expected_dataset_hash.removeprefix('sha256:') != digest(args.dataset)):
        raise ValueError('worker receipt does not identify this exact frozen dataset')
    result = integrate(dataset['cases'], receipt, args.kind)
    result['inputs'] = {str(path): digest(path) for path in (args.dataset, args.receipt)}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
