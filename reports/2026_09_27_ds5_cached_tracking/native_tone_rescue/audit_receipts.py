"""Independent receipt arithmetic and chronological cache opportunities; no IQ."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def associates(pair, reference, rate):
    if pair is None or pair['receiver'] != reference['receiver']:
        return False
    period = rate / 750
    return all(
        abs((pair[name]['dwell_epoch_sample'] - reference[name]['dwell_epoch_sample']
             + period / 2) % period - period / 2) <= rate * 2e-6
        and abs(pair[name]['tracking_cfo_hz'] - reference[name]['tracking_cfo_hz']) <= 8000
        for name in ('first', 'second')
    )


def run():
    files = ['results.controls.json', 'results.reporting_fix.diagnostic.json',
             'results.reporting_fix.real.json', 'source_lock.json', 'reporting_fix_lock.json']
    hashes = {name: digest(HERE / name) for name in files}
    for name in files[-2:]:
        lock = json.loads((HERE / name).read_text())
        for source, expected in lock['files'].items():
            assert digest(source) == expected, source
    receipts = [json.loads((HERE / name).read_text()) for name in files[:3]]
    for receipt in receipts:
        assert receipt['complete'] and receipt['source_lock_stable']
        assert not receipt['holdout_opened'] and not receipt['validation_opened']
        assert all(row['input_immutable'] for row in receipt['rows'])
    for receipt in receipts[:2]:
        for section in ('rows', 'supplemental_mirrored_negative_rows'):
            for row in receipt.get(section, []):
                for method in ('native_tracked', 'tone_rescue'):
                    assert all(a['activity_policy_passed'] is not False
                               for a in row['native_assessments'][method])
    rows = receipts[2]['rows']
    recovered, totals, opportunities = [], {}, []
    last_rescue = {}
    for row in rows:
        rate = row['rate_hz']
        total = totals.setdefault(str(rate), {'reference': 0, 'baseline_retained': 0,
            'rescued_retained': 0, 'baseline_extras': 0, 'rescue_extras': 0,
            'application_cpu_ms': 0., 'rescue_cpu_ms': 0., 'calls_over_120ms': 0})
        total['application_cpu_ms'] += row['timings']['application']['process_cpu_ms']
        total['rescue_cpu_ms'] += row['timings']['tone_rescue']['process_cpu_ms']
        total['calls_over_120ms'] += row['timings']['tone_rescue']['wall_ms'] > 120
        assert row['tone_rescue_result']['primary_decisions'] == row['native_decisions']['native_tracked']
        for receiver in (0, 1):
            baseline = row['native_decisions']['native_tracked'][receiver]
            actual = row['native_decisions']['tone_rescue'][receiver]
            reference = [p for p in row['application_pair_inventory'] if p['receiver'] == receiver]
            bmatch = any(associates(baseline['pair'], p, rate) for p in reference)
            amatch = any(associates(actual['pair'], p, rate) for p in reference)
            assert bmatch == row['native_assessments']['native_tracked'][receiver]['matched_reference']
            assert amatch == row['native_assessments']['tone_rescue'][receiver]['matched_reference']
            total['reference'] += bool(reference)
            total['baseline_retained'] += bmatch
            total['rescued_retained'] += amatch
            total['baseline_extras'] += baseline['active'] and not bmatch
            total['rescue_extras'] += actual['active'] and not amatch
            if baseline['active']:
                assert actual == baseline
            key = (row['session_id'], row['channel'], row['edge'], rate, receiver)
            prior = last_rescue.get(key)
            if prior is not None and row['tone_rescue_result']['rescue_receiver'] == receiver:
                gap = (row['source_counter'] - prior['source_counter']) / rate
                opportunities.append({'case_id': row['case_id'], 'receiver': receiver,
                    'prior_case_id': prior['case_id'], 'elapsed_seconds': gap,
                    'within_2s': 0 < gap <= 2,
                    'current_rescue_accepted': actual['route'] == 'rescue_probe0_probe2'})
            if actual['route'] != 'rescue_probe0_probe2':
                continue
            pair = actual['pair']
            for name in ('first', 'second'):
                point = pair[name]
                assert point['receiver'] == receiver and point['status'] == 0
                assert point['supported'] and point['valid_bounds'] and point['fractional_complete']
                assert point['support_frames'] >= 2 and point['margin'] >= .025
                whole = int(point['local_epoch_sample'])
                assert point['source_epoch_counter'] == row['source_counter'] + point['probe_start_sample'] + whole
                assert point['source_epoch_fraction'] == point['local_epoch_sample'] - whole
            assert pair['first']['probe_index'] == 0 and pair['second']['probe_index'] == 2
            assert pair['second']['probe_start_sample'] - pair['first']['probe_start_sample'] == rate // 50
            assert abs(pair['first']['tracking_cfo_hz'] - pair['second']['tracking_cfo_hz']) <= 8000
            assert amatch and not bmatch
            recovered.append({'case_id': row['case_id'], 'receiver': receiver})
            last_rescue[key] = row
    for total in totals.values():
        total['aggregate_cpu_speedup'] = total['application_cpu_ms'] / total['rescue_cpu_ms']
    assert len(recovered) == 11
    assert sum(v['rescued_retained'] for v in totals.values()) == 78
    assert hashes == {name: digest(HERE / name) for name in files}
    return {'receipt_hashes': hashes, 'independent_arithmetic_passed': True,
            'recovered_receivers': recovered, 'by_rate': totals,
            'posthoc_cache_opportunities': opportunities,
            'cache_caveat': 'Metadata only; no predicted point was scored. Tuning/calibration continuity must also be checked before reuse.',
            'saved_iq_opened': False}


if __name__ == '__main__':
    with (HERE / 'receipt_audit.json').open('x') as stream:
        json.dump(run(), stream, indent=2)
        stream.write('\n')
