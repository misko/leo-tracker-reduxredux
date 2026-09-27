"""Receipt-only failure localization; never reads IQ or retunes the candidate."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def classify(row, rx):
    primary = row['native_decisions']['native_tracked'][rx]
    result = row['tone_rescue_result']
    if primary['active']:
        return 'active_primary_identity_disagreement'
    if result['rescue_receiver'] != rx:
        return 'inactive_receiver_not_selected'
    events = result['rescue_events']
    if events and all(e['reason'] == 'python_margin_failed' for e in events):
        return 'all_probe_zero_proposals_below_margin'
    return 'other_rescue_failure'


def audit(document):
    rows = document['rows']
    assert document['gates']['complete'] and len(rows) == 64
    assert document['error'] is None and document['source_lock_stable']
    rate = str(rows[0]['rate_hz'])
    summary = document['summary']['by_rate'][rate]
    counts = {}
    for method in ('native_tracked', 'tone_rescue'):
        assessments = [a for r in rows for a in r['native_assessments'][method]]
        counts[method] = {
            'reference_positive_receivers': sum(a['reference_active'] for a in assessments),
            'matched_reference_receivers': sum(a['matched_reference'] for a in assessments),
            'lost_reference_receivers': sum(a['lost_reference'] for a in assessments),
            'additional_or_mismatched_active_receivers': sum(a['additional_or_mismatched'] for a in assessments),
        }
        for key, value in counts[method].items():
            assert value == summary['quality'][method][key]
    misses = []
    extra_routes = Counter()
    for row in rows:
        assert row['input_immutable']
        for rx, primary in enumerate(row['native_decisions']['native_tracked']):
            if primary['active']:
                assert primary == row['native_decisions']['tone_rescue'][rx]
            a = row['native_assessments']['tone_rescue'][rx]
            if a['additional_or_mismatched']:
                extra_routes[row['native_decisions']['tone_rescue'][rx]['route']] += 1
            if a['lost_reference']:
                pairs = [p for p in row['application_pair_inventory'] if p['receiver'] == rx]
                misses.append({
                    'case_id': row['case_id'], 'receiver': rx,
                    'failure_stage': classify(row, rx),
                    'reference_pair_probe_indices': sorted({p[k]['probe_index'] for p in pairs for k in ('first', 'second')}),
                    'reference_pair_count': len(pairs),
                    'reference_probe_zero_two_pairs': sum(
                        {p['first']['probe_index'], p['second']['probe_index']} == {0, 2} for p in pairs),
                })
    cpu = {m: sum(r['timings'][m]['process_cpu_ms'] for r in rows)
           for m in ('application', 'native_tracked', 'tone_rescue')}
    speedup = cpu['application'] / cpu['tone_rescue']
    assert abs(speedup - summary['methods']['tone_rescue']['aggregate_cpu_speedup_vs_application']) < 1e-10
    return {'rate_hz': int(rate), 'counts': counts, 'gates': document['gates'],
            'cpu_mean_ms': {m: t / len(rows) for m, t in cpu.items()},
            'aggregate_cpu_speedup': speedup,
            'additional_or_mismatched_routes': dict(extra_routes), 'misses': misses,
            'miss_stages': dict(Counter(m['failure_stage'] for m in misses))}


def main():
    lock = json.loads((HERE / 'source_lock.json').read_text())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in lock['files'].items())
    results = {}
    hashes = {}
    for rate in (2500000, 5000000):
        path = HERE / f'results.{rate}.json'
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        results[str(rate)] = audit(json.loads(path.read_text()))
    with (HERE / 'failure_audit.json').open('x') as stream:
        json.dump({'receipt_hashes': hashes, 'source_inventory_verified': True,
                   'scope': 'Recounts recorded assessments; does not independently recompute scientific association or read IQ.',
                   'by_rate': results}, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
