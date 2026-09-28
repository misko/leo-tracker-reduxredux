"""Independently audit provenance and tally receiver-order evidence."""
from collections import Counter, defaultdict
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORECAST = HERE.parent / '2026_09_28_rx_training_forecast'
mapping = json.loads((HERE / 'alias-mapping.json').read_text())
bank = json.loads((FORECAST / 'candidate-bank.json').read_text())
parts = json.loads((FORECAST / 'partitions.json').read_text())
windows = {row['source_window_id']: row for row in parts['windows']}
frozen = {(r['session_id'], r['track_id']): r for r in bank['tracks']}
assert len(mapping['tracks']) == len(frozen) == 30
point_count = vote_count = 0
for row in mapping['tracks']:
    original = frozen[(row['session_id'], row['track_id'])]
    assert [p['observation_id'] for p in row['training_alias_points']] == original['training_observation_ids']
    for point in row['training_alias_points']:
        window = windows[point['source_window_id']]
        assert window['role'] == 'train' and window['session_id'] == row['session_id']
        value = (point['raw_cfo_hz'] - point['relative_alias_index'] * row['raw_alias_spacing_hz']) * row['canonical_scale']
        assert abs(value - point['normalized_dealiased_cfo_hz']) < 1e-6
        point_count += 1
for lane in mapping['receiver_calibrations']:
    votes = lane['training_window_votes']
    assert len(votes) == lane['distinct_training_windows']
    assert len({v['source_window_id'] for v in votes}) == len(votes)
    for vote in votes:
        window = windows[vote['source_window_id']]
        assert window['role'] == 'train'
        assert all(window[k] == lane[k] for k in ('session_id', 'channel', 'edge'))
        vote_count += 1
summary = {'mapped_tracks': len(frozen), 'verified_training_points': point_count,
           'verified_training_calibration_votes': vote_count,
           'calibration_lanes': len(mapping['receiver_calibrations']),
           'qualified_calibration_lanes': sum(x['qualified'] for x in mapping['receiver_calibrations'])}
qualified = {(x['session_id'], x['channel'], x['edge'], x['actual_rf_hz']) for x in mapping['receiver_calibrations'] if x['qualified']}
summary['mapped_tracks_with_qualified_transfer'] = sum((x['session_id'], x['channel'], x['edge'], x['actual_rf_hz']) in qualified for x in mapping['tracks'])
if (HERE / 'sequences.json').exists():
    result = json.loads((HERE / 'sequences.json').read_text())
    counts = Counter()
    by_role = defaultdict(Counter)
    raw_claims = defaultdict(set)
    exclusions = Counter()
    row_count = 0
    with (HERE / 'matched-opportunities.jsonl').open() as handle:
        for line in handle:
            row = json.loads(line)
            row_count += 1
            assert windows[row['source_window_id']]['role'] == row['role']
            counts[row['status']] += 1
            by_role[row['role']][row['status']] += 1
            if row.get('exclusion_reason'):
                exclusions[row['exclusion_reason']] += 1
            if row['status'] == 'unique_hit':
                assert len(row['matches']) == 1 and not row['colliding_hypothesis_ids']
                match = row['matches'][0]
                assert abs(match['residual_hz']) <= 2500
                raw_claims[(row['source_window_id'], row['receiver_id'], match['candidate_id'])].add(row['hypothesis_id'])
    assert all(len(x) == 1 for x in raw_claims.values())
    expected = 2 * sum(len(c['window_predictions']) for t in bank['tracks'] for c in t['top_candidates'])
    assert row_count == expected == result['accounting']['opportunity_rows']
    assert dict(counts) == result['accounting']['status_counts']
    summary.update({'receiver_hypothesis_rows': row_count, 'status_counts_by_role': dict(by_role),
                    'distinct_unique_raw_hits': len(raw_claims),
                    'exclusion_reasons': dict(exclusions),
                    'sequences': len(result['sequences']),
                    'recorded_orders': dict(Counter(s['recorded_proxy_order'] or 'unavailable_or_tied' for s in result['sequences'])),
                    'endpoint_censoring': dict(Counter(e['censoring'] for s in result['sequences'] for e in s['receivers'].values()))})
    summary['lag_sequences'] = [s for s in result['sequences'] if s['uncensored_lag_rx1_minus_rx0_s'] is not None]
summary['checks_passed'] = True
with (HERE / 'audit.json').open('w') as handle:
    json.dump(summary, handle, indent=2)
print(json.dumps(summary, indent=2))
