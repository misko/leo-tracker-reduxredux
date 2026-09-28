"""Check completed source receipts and independently summarize case endpoints."""
import hashlib
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for stage in ('leverage', 'cases'):
    receipt = json.loads((HERE / f'{stage}-launch.json').read_text())
    for name, value in receipt['sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value, name
    assert (HERE / f'{stage}-exit-code.txt').read_text().strip() == '0'
cases = json.loads((HERE / 'cases.json').read_text())
prior = json.loads((HERE.parent / '2026_09_28_rx_receiver_order/sequences.json').read_text())
expected = {(s['hypothesis_id'], s['role']) for s in prior['sequences']
            if all(e['first_hit_utc_ns'] is not None for e in s['receivers'].values())}
assert {(c['sequence']['hypothesis_id'], c['sequence']['role']) for c in cases['cases']} == expected
assert cases['case_count'] == len(expected) == 17
common = [w for c in cases['cases'] for w in c['common_dual_unique_hit_windows']]
sole, = [c for c in cases['cases'] if c['sequence']['uncensored_lag_rx1_minus_rx0_s'] is not None]
intervals = [sole['receivers'][rx]['first_hit_interval'] for rx in ('rx0', 'rx1')]
assert all(i['valid'] for i in intervals)
bounds = [(intervals[1]['lower_exclusive_utc_ns'] - intervals[0]['upper_inclusive_utc_ns']) / 1e9,
          (intervals[1]['upper_inclusive_utc_ns'] - intervals[0]['lower_exclusive_utc_ns']) / 1e9]
forecast = HERE.parent / '2026_09_28_rx_training_forecast'
bank = json.loads((forecast / 'candidate-bank.json').read_text())
parts = json.loads((forecast / 'partitions.json').read_text())
splits = {r['session_id']: r['recording_split'] for r in parts['recordings']}
gaps = []
for t in bank['tracks']:
    scores = sorted([c['training_log_likelihood'] for c in t['top_candidates']], reverse=True)
    assert all(math.isfinite(x) for x in scores)
    gaps.append({'track_id': t['track_id'], 'session_id': t['session_id'],
                 'recording_split': splits[t['session_id']], 'top_vs_second_gap_nats': scores[0] - scores[1]})
result = {'checks_passed': True, 'audited_cases': len(expected),
          'dual_unique_windows': len(common),
          'epoch_compatible_dual_unique_windows': sum(w['proxy_epoch_compatible'] is True for w in common),
          'sole_lag_transition_bracket_s': bounds,
          'sole_lag_training_gap_nats': next(r['top_vs_second_gap_nats'] for r in gaps if r['track_id'] == sole['sequence']['track_id']),
          'evaluation_median_training_gap_nats': statistics.median(r['top_vs_second_gap_nats'] for r in gaps if r['recording_split'] == 'evaluation'),
          'training_log_likelihood_gaps': gaps}
(HERE / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'training_log_likelihood_gaps'}, indent=2))
