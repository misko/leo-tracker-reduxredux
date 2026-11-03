"""Stratify the existing frozen matches by reference-segment duration."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0, str(HERE.parent / '2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def main():
    observations = m.read_observations(BASE / 'server-observations.tsv')
    tracks = m.read_tracks(BASE / 'server-tracks.tsv', observations).values
    buckets = {'short': set(), 'medium': set(), 'long': set()}
    durations = {}
    for track in tracks:
        if track.index == 10:
            continue
        seconds = (track.end_ns - track.start_ns) / 1e9
        key = 'short' if seconds < 15 else 'medium' if seconds < 30 else 'long'
        buckets[key].add(track.index)
        durations[track.index] = seconds
    assert sum(map(len, buckets.values())) == 62
    methods = ['rolling', 'kalman-v2', 'linking-v2', 'coarse-seeded-curvature']
    rows = []
    for side in ['arm', 'server']:
        for method in methods:
            path = (HERE / ('baseline-hybrid.json' if side == 'arm' else 'baseline-hybrid-server.json')
                    if method == 'coarse-seeded-curvature' else
                    HERE / 'qualification' / method / f'{side}-evaluation.json')
            evaluation = json.loads(path.read_text())
            matched = set(evaluation['primary']['reference_segments_with_any_complete_output_indexes']) - {10}
            limited = set(evaluation['primary']['input_unsupported_reference_indexes']) - {10}
            counts = {key: {'matched': len(matched & indexes), 'total': len(indexes),
                            'matched_indexes': sorted(matched & indexes),
                            'input_limited': len(limited & indexes)}
                      for key, indexes in buckets.items()}
            assert sum(value['matched'] for value in counts.values()) == len(matched)
            assert len(matched) == evaluation['reviewed']['represented_count']
            rows.append({'input': side, 'method': method, 'buckets': counts, 'total_matched': len(matched),
                         'evaluation_path': str(path), 'evaluation_sha256': m.digest(path)})
    report = {'definition': 'Reference support end minus support start; short <15s, medium >=15s and <30s, long >=30s',
              'scope': 'Existing represented-segment criterion; ref10 excluded; no matching thresholds changed',
              'reference_sha256': m.digest(BASE / 'server-tracks.tsv'),
              'reference_durations_s': durations, 'rows': rows}
    (HERE / 'duration-breakdown.json').write_text(json.dumps(report, indent=2) + '\n')
    for row in rows:
        print(row['input'], row['method'],
              ' '.join(f'{key}={value["matched"]}/{value["total"]}' for key, value in row['buckets'].items()),
              'total', row['total_matched'])
    print('ARM input-limited buckets:', {k: v['input_limited'] for k, v in rows[0]['buckets'].items()})


if __name__ == '__main__':
    main()
