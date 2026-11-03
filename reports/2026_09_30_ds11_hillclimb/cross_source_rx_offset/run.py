"""Descriptive cross-source prediction of paired receiver CFO offsets."""
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / 'same_source_cfo_audit/results.json'
PERIOD = 1 / 4.4e-6


def wrap(x):
    return (x + PERIOD / 2) % PERIOD - PERIOD / 2


def medoid(values):
    values = sorted(wrap(v) for v in values)
    return min(values, key=lambda x: (sum(abs(wrap(v-x)) for v in values), x))


def verify_tree(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            actual = hashlib.sha256(Path(value['path']).read_bytes()).hexdigest()
            assert actual == value['sha256'].removeprefix('sha256:')
        else:
            for child in value.values():
                verify_tree(child)
    elif isinstance(value, list):
        for child in value:
            verify_tree(child)


def donor_prediction(target, pairs):
    donors = {}
    for other in pairs:
        if (other['scan_index'], other['rf_hz']) != (target['scan_index'], target['rf_hz']):
            continue
        if other['norad'] == target['norad']:
            continue
        if len(set(other['visits']) & set(target['visits'])) < 6:
            continue
        donors.setdefault(other['norad'], []).append(other['offset_hz'])
    centers = {key: medoid(values) for key, values in donors.items()}
    return centers, medoid(list(centers.values())) if len(centers) >= 3 else None


def main():
    data = json.loads(INPUT.read_text())
    verify_tree(data['source_sha256'])
    tracks = {(t['scan_index'], t['track_id']): t for t in data['track_rows']}
    pairs = []
    excluded = 0
    for row in data['cross_receiver_pair_rows']:
        a = tracks[row['scan_index'], row['track_a']]
        b = tracks[row['scan_index'], row['track_b']]
        assert {a['receiver_id'], b['receiver_id']} == {0, 1}
        assert a['unambiguous'] and b['unambiguous']
        visits = sorted(set(a['training_visits']) & set(b['training_visits']))
        if len(visits) < 6:
            excluded += 1
            continue
        sign = 1 if a['receiver_id'] == 1 else -1
        offset = wrap(sign * (a['native_cfo_hz'] - b['native_cfo_hz']))
        pairs.append(dict(scan_index=row['scan_index'], rf_hz=row['rf_hz'],
                          norad=a['norad'], track_a=row['track_a'], track_b=row['track_b'],
                          visits=visits, offset_hz=offset))
    results = []
    for target in pairs:
        donors, prediction = donor_prediction(target, pairs)
        result = dict(target, donor_centers_hz=donors, prediction_hz=prediction)
        if prediction is not None:
            result.update(zero_error_hz=abs(target['offset_hz']),
                          predicted_error_hz=abs(wrap(target['offset_hz']-prediction)))
        results.append(result)
    supported = [r for r in results if r['prediction_hz'] is not None]
    summary = dict(input_pairs=len(data['cross_receiver_pair_rows']),
                   excluded_under_six_shared_visits=excluded,
                   eligible_pairs=len(pairs), supported_pairs=len(supported),
                   supported_scans=len({r['scan_index'] for r in supported}))
    if supported:
        summary.update(wins=sum(r['predicted_error_hz'] < r['zero_error_hz'] for r in supported),
                       median_zero_error_hz=median(r['zero_error_hz'] for r in supported),
                       median_predicted_error_hz=median(r['predicted_error_hz'] for r in supported),
                       median_paired_gain_hz=median(r['zero_error_hz']-r['predicted_error_hz'] for r in supported))
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (INPUT, Path(__file__), HERE/'test_run.py', HERE/'PROTOCOL.md')}
    output = dict(schema='conditional-cross-source-rx-offset/v1', summary=summary,
                  rows=results, sources=sources, position_fits=0,
                  held_observations_used=False, reference_used=False)
    (HERE/'outcome.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
