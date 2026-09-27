"""Descriptive attribution of frozen transfer scores; no fitting or selection."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / '2026_09_27_roof_balanced_confirmation/association-transfer-summary.json'


def describe(row):
    normal = row['normal']
    p = normal['baseline_conditioning_posterior']
    q = normal['reception_conditioning_posterior']
    ids = row['candidate_ids']
    if p['candidate_ids'] != ids or q['candidate_ids'] != ids:
        raise ValueError('candidate alignment')
    gain = normal['improvement_baseline_minus_reception']
    if abs(normal['baseline_mean_nll'] - normal['reception_mean_nll'] - gain) > 1e-12:
        raise ValueError('gain mismatch')
    ceiling = normal['baseline_mean_nll'] + max(row['held_frequency_log_likelihood']) / row['held_count']
    if ceiling < -1e-10 or gain > ceiling + 1e-10:
        raise ValueError('oracle bound violated')
    return {'session_id': row['session_id'], 'track_id': row['track_id'],
            'direction': row['direction'], 'weight': row['weight_seconds'],
            'held_count': row['held_count'], 'gain': gain,
            'baseline_max_probability': max(p['probabilities']),
            'reception_max_probability': max(q['probabilities']),
            'total_variation': sum(abs(a-b) for a,b in zip(p['probabilities'], q['probabilities'])) / 2,
            'map_changed': p['map_candidate_id'] != q['map_candidate_id'],
            'baseline_map': p['map_candidate_id'], 'reception_map': q['map_candidate_id'],
            'held_best_candidate': ids[max(range(len(ids)), key=lambda i: row['held_frequency_log_likelihood'][i])],
            'held_oracle_gain': max(0., ceiling)}


def summarize(rows, denominator):
    weight = sum(r['weight'] for r in rows)
    numerator = math.fsum(r['weight'] * r['gain'] for r in rows)
    return {'count': len(rows), 'weight_seconds': weight,
            'weighted_gain': numerator / weight if weight else None,
            'contribution_to_full_gain': numerator / denominator,
            'map_changes': sum(r['map_changed'] for r in rows),
            'positive': sum(r['gain'] > 1e-10 for r in rows),
            'negative': sum(r['gain'] < -1e-10 for r in rows)}


def audit(records):
    if len({(r['session_id'], r['track_id'], r['direction']) for r in records}) != len(records):
        raise ValueError('duplicate record')
    details = [describe(r) for r in records]
    result = {}
    for direction in ('A_to_B', 'B_to_A'):
        rows = [r for r in details if r['direction'] == direction]
        total = sum(r['weight'] for r in rows)
        if not total: raise ValueError('missing direction')
        groups = {}
        # Fixed descriptive bins; no winner selection or hyperparameter tuning.
        for name, low, high in [('below_0.9', 0., .9), ('0.9_to_0.99', .9, .99), ('at_least_0.99', .99, 1.000001)]:
            groups[name] = summarize([r for r in rows if low <= r['baseline_max_probability'] < high], total)
        ordered = sorted(rows, key=lambda r: r['weight'] * r['gain'])
        def tops(selected):
            return [{**r, 'contribution_to_full_gain': r['weight'] * r['gain'] / total} for r in selected]
        result[direction] = {'all': summarize(rows, total), 'confidence_bins': groups,
            'map_changed': summarize([r for r in rows if r['map_changed']], total),
            'map_unchanged': summarize([r for r in rows if not r['map_changed']], total),
            'held_oracle_gain': math.fsum(r['weight'] * r['held_oracle_gain'] for r in rows) / total,
            'worst_five': tops(ordered[:5]), 'best_five': tops(ordered[-5:][::-1]),
            'leave_one_recording_out_descriptive': {
                sid: summarize([r for r in rows if r['session_id'] != sid],
                               sum(r['weight'] for r in rows if r['session_id'] != sid))
                for sid in sorted({r['session_id'] for r in rows})}}
    return result


def main():
    raw = SOURCE.read_bytes()
    source = json.loads(raw)
    if not source['complete'] or len(source['records']) != 688:
        raise ValueError('incomplete source')
    output = {'source_sha256': hashlib.sha256(raw).hexdigest(),
              'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Posthoc descriptive attribution, not independent validation. Held oracle uses outcomes and is not an estimator.',
              'results': audit(source['records'])}
    for direction, value in output['results'].items():
        expected = source['summary']['pooled_by_direction'][direction]['metrics']['normal']['improvement_baseline_minus_reception']['occupied_second_weighted']
        if abs(value['all']['weighted_gain'] - expected) > 1e-12:
            raise ValueError('pooled score parity')
    destination = HERE / 'results.json'
    with destination.open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: {n:v for n,v in value.items() if n not in ('worst_five','best_five')} for k,value in output['results'].items()}, indent=2))


if __name__ == '__main__':
    main()
