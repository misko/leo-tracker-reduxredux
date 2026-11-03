"""Audit source exclusivity and common-probe coverage of saved track hypotheses."""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    freeze = HERE/'vectorized-proposals-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    inputs, rows = {}, []
    for unit, arm in frozen['pairs']:
        if arm != 'candidate':
            continue
        path = HERE/'source-split-expansion-v1'/(unit+'.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        inputs[str(path)] = digest(path)
        source = json.loads(path.read_text())
        tracks = {t['track_id']: t for t in source['training_tracks']}
        used, baseline = set(), []
        for t in sorted(tracks.values(),
                        key=lambda t: (t['times_s'][-1], t['times_s'][0], t['track_id'])):
            visits = {(t['receiver_id'], t['channel'], v) for v in t['visits']}
            if used.intersection(visits) or len(t['visits']) < 3:
                continue
            used.update(visits)
            baseline.append(t['track_id'])
        points = defaultdict(list)
        for p in source['checking_points']:
            points[p['source_group_id']].append(p)
        groups = []
        for key, members in sorted(points.items()):
            p = members[0]
            groups.append((key, p['receiver_id'], p['channel'], p['actual_rf_hz'],
                float(np.median([(q['support_center_utc_ns']-source['start_utc_ns'])/1e9
                                  for q in members]))))
        coverage = {}
        for identity, track in tracks.items():
            coverage[identity] = {key for key, rx, channel, rf, epoch in groups
                if rx == track['receiver_id'] and channel == track['channel']
                and rf == track['rf_hz'] and track['times_s'][0] <= epoch <= track['times_s'][-1]}

        def covered(identities, coverage=coverage):
            return set().union(*(coverage[i] for i in identities))

        original = covered(baseline)
        proposals, union, common = [], set(), None
        for index, hypothesis in enumerate(source['training_hypotheses']):
            ids = hypothesis['track_ids']
            assert len(set(ids)) == len(ids) and set(ids) <= tracks.keys()
            source_counts, candidate_counts, visit_counts = Counter(), Counter(), Counter()
            for identity in ids:
                track = tracks[identity]
                source_counts.update(set(track['source_group_ids']))
                candidate_counts.update(set(track['candidate_ids']))
                visit_counts.update({(track['receiver_id'], track['channel'], v)
                                     for v in track['visits']})
            selected = covered(ids)
            union |= selected
            common = selected if common is None else common & selected
            proposals.append(dict(index=index, tracks=len(ids),
                repeated_source_groups=sum(n > 1 for n in source_counts.values()),
                repeated_candidate_ids=sum(n > 1 for n in candidate_counts.values()),
                repeated_receiver_channel_visits=sum(n > 1 for n in visit_counts.values()),
                checking_groups_covered=len(selected),
                groups_added_vs_baseline=len(selected-original),
                groups_lost_vs_baseline=len(original-selected),
                tracks_added_vs_baseline=len(set(ids)-set(baseline)),
                tracks_removed_vs_baseline=len(set(baseline)-set(ids))))
        rows.append(dict(unit=unit, reconstructed_tracks=len(tracks),
            baseline_tracks=len(baseline), checking_groups=len(groups),
            baseline_geometric_coverage=len(original),
            all_reconstructed_geometric_coverage=len(covered(tracks)),
            hypotheses=proposals, union_hypothesis_coverage=len(union),
            common_hypothesis_coverage=len(common or set()),
            union_added_vs_baseline=len(union-original)))
    verify_sources(inputs)
    summary = {key: sum(r[key] for r in rows) for key in [
        'checking_groups', 'baseline_geometric_coverage', 'all_reconstructed_geometric_coverage',
        'union_hypothesis_coverage', 'common_hypothesis_coverage', 'union_added_vs_baseline']}
    hypotheses = [h for r in rows for h in r['hypotheses']]
    summary.update(hypotheses=len(hypotheses),
        source_disjoint_hypotheses=sum(h['repeated_source_groups'] == 0 for h in hypotheses),
        visit_disjoint_hypotheses=sum(h['repeated_receiver_channel_visits'] == 0
                                      for h in hypotheses),
        hypotheses_with_more_coverage=sum(h['groups_added_vs_baseline']
                                         > h['groups_lost_vs_baseline'] for h in hypotheses))
    result = dict(rows=rows, summary=summary, input_sha256=inputs,
        source_sha256=frozen['source_sha256'], auditor_sha256=digest(__file__),
        elapsed_s=time.monotonic()-started,
        qualification='Read-only training-hypothesis and checking-metadata coverage audit. '
        'No GPS, frequency-based selection, satellite assignments or fitting. Geometric '
        'coverage ignores clutter and does not establish correct prediction. Source-group '
        'disjointness is checked separately from conservative whole-visit disjointness; '
        'neither proves statistical independence. Union is alternative coverage, not one '
        'valid joint track set, and overlapping hypotheses must not be multiplied.')
    output = HERE/'trajectory-hypothesis-coverage-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(summary=summary, elapsed_s=result['elapsed_s']), indent=2))


if __name__ == '__main__':
    main()
