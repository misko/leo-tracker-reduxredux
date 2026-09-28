"""Audit frozen confirmation identities, group roles, mappings and scores."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for stage in ('bank', 'mapping', 'dataset', 'score'):
    receipt = json.loads((HERE / f'{stage}-launch.json').read_text())
    for name, expected in receipt['sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
    assert (HERE / f'{stage}-exit-code.txt').read_text().strip() == '0'
parts = json.loads((HERE / 'partitions.json').read_text())
bank = json.loads((HERE / 'candidate-bank.json').read_text())
mapping = json.loads((HERE / 'alias-mapping.json').read_text())
dataset = json.loads((HERE / 'dataset.json').read_text())
result = json.loads((HERE / 'results.json').read_text())
windows = {w['source_window_id']: w for w in parts['windows']}
groups = {}
for w in windows.values():
    assert w['recording_split'] == 'evaluation'
    assert groups.setdefault(w['group_id'], w['role']) == w['role']
assert len(bank['tracks']) == len(mapping['tracks']) == 12
frozen = {(t['session_id'], t['track_id']): t for t in bank['tracks']}
points = 0
for t in mapping['tracks']:
    source = frozen[(t['session_id'], t['track_id'])]
    assert [p['observation_id'] for p in t['training_alias_points']] == source['training_observation_ids']
    for p in t['training_alias_points']:
        assert windows[p['source_window_id']]['role'] == 'train'
        predicted = (p['raw_cfo_hz'] - p['relative_alias_index'] * t['raw_alias_spacing_hz']) * t['canonical_scale']
        assert abs(predicted - p['normalized_dealiased_cfo_hz']) < 1e-6
        points += 1
for lane in mapping['receiver_calibrations']:
    for vote in lane['training_window_votes']:
        assert windows[vote['source_window_id']]['role'] == 'train'
seen = set()
for lane in dataset['lanes']:
    a = lane['accounting']
    for role, total in a['forecast_windows_by_role'].items():
        assert total == a['windows_by_role'].get(role, 0) + a['excluded_windows_by_role'].get(role, 0)
    for w in lane['windows']:
        assert w['source_window_id'] not in seen
        seen.add(w['source_window_id'])
        assert windows[w['source_window_id']]['role'] == w['role']
assert result['overlapping_sessions'] == []
denominators = []
for arm, evaluation in result['evaluations'].items():
    denominators.append({s: r['held_windows'] for s, r in evaluation['recordings'].items()})
    for lane in evaluation['lane_posteriors']:
        for key in ('prior_log_weights', 'reception_log_weights', 'held_log_weights'):
            assert abs(sum(math.exp(x) for x in lane[key] if x is not None) - 1) < 1e-8
    for sid, row in evaluation['recordings'].items():
        total = sum(sum(l['held_window_log_scores']) for l in evaluation['lane_posteriors'] if l['lane']['session_id'] == sid)
        assert abs(total - row['held_log_score']) < 1e-8
assert all(d == denominators[0] for d in denominators)
report = {'checks_passed': True, 'recordings': len(parts['recordings']),
          'mapped_tracks': len(mapping['tracks']), 'training_alias_points': points,
          'unique_scored_windows': len(seen), 'held_windows_by_record': denominators[0],
          'no_pilot_overlap': True, 'static_positive_vs_clutter_records': sum(v > 0 for v in result['arm_minus_clutter_per_record']['S'].values()),
          'static_mean_vs_clutter': result['arm_minus_clutter_equal_record_mean']['S'],
          'static_default_promotion': False}
(HERE / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
