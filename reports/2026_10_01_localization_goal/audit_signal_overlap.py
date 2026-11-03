"""Audit frozen visit exclusions against recovered detector support; no fitting."""
import json
from pathlib import Path

import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent


def comparison(left, right):
    """Count shared detector identities and overlapping same-receiver samples."""
    candidates = {p['candidate_id'] for p in right}
    groups = {p['source_group_id'] for p in right}
    return dict(
        shared_candidates=sum(p['candidate_id'] in candidates for p in left),
        shared_source_groups=sum(p['source_group_id'] in groups for p in left),
        overlapping_sample_points=sum(any(
            p['receiver_id'] == q['receiver_id']
            and max(p['source_sample_start'], q['source_sample_start'])
            < min(p['source_sample_end'], q['source_sample_end'])
            for q in right) for p in left))


def main():
    provenance = HERE/'signal-provenance-v1.json'
    assert digest(provenance) == provenance.with_suffix('.sha256').read_text().strip()
    rows = []
    for source in json.loads(provenance.read_text())['rows']:
        assert source['status'] == 'bound'
        unit = source['unit']
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(parent_path) == json.loads(parent_path.with_suffix('.seal.json').read_text())[
            'prediction_sha256']
        parent = json.loads(parent_path.read_text())
        paths = [Path(p) for p in parent['inputs'] if p.endswith('observations.json')]
        assert len(paths) == 1
        observations_path = paths[0]
        assert digest(observations_path) == source['observation_sha256']
        assert digest(observations_path) == parent['inputs'][str(observations_path)]
        observations = json.loads(observations_path.read_text())
        by_id = {t['track_id']: t['points'] for t in source['tracks']}
        consumed, retained, excluded, alias_errors = set(), [], [], []
        for t in sorted(observations['tracks'], key=lambda t: (
                t['times_s'][-1], t['times_s'][0], t['track_id'])):
            points = by_id[t['track_id']]
            assert len(points) == len(t['measured_hz'])
            for p, measured, visit, time in zip(
                    points, t['measured_hz'], t['visits'], t['times_s'], strict=True):
                assert p['visit_index'] == visit
                assert abs((p['support_center_utc_ns']-observations['start_utc_ns'])/1e9
                           - time) < 1e-9
                alias = (measured*p['actual_rf_hz']/11.2e9-p['measured_cfo_hz'])*4.4e-6
                alias_errors.append(abs(alias-round(alias)))
            ids = {(t['receiver_id'], t['channel'], v) for v in t['visits']}
            if ids & consumed or len(points) < 3:
                conflicts = comparison(points, [p for r in retained for p in by_id[r]])
                excluded.append(dict(track_id=t['track_id'], points=len(points), **conflicts))
            else:
                retained.append(t['track_id'])
                consumed.update(ids)
        assert len(retained) == len(parent['observations'])
        retained_points = [p for t in retained for p in by_id[t]]
        assert len({p['candidate_id'] for p in retained_points}) == len(retained_points)
        rows.append(dict(
            unit=unit, exported_tracks=len(by_id), retained_tracks=len(retained),
            excluded_tracks=len(excluded), excluded=excluded,
            exclusions_without_shared_candidates=sum(not x['shared_candidates'] for x in excluded),
            exclusions_without_shared_source_groups=sum(not x['shared_source_groups']
                                                       for x in excluded),
            exclusions_without_sample_overlap=sum(not x['overlapping_sample_points']
                                                   for x in excluded),
            maximum_alias_integer_discrepancy=max(alias_errors),
            retained_margin_quantiles=np.quantile(
                [p['margin'] for p in retained_points], [0, .1, .5, .9, 1]).tolist(),
            parent_sha256=digest(parent_path), observation_sha256=digest(observations_path)))
    result = dict(rows=rows, provenance_sha256=digest(provenance), source_sha256=digest(__file__),
                  qualification='Three development pilots; exact source/time binding and frozen '
                  'visit exclusion reproduced. Different candidates on shared samples are not '
                  'independent observations. Margins are not satellite identity probabilities. '
                  'No GPS, RF collection, model fitting or benchmark changes.')
    output = HERE/'signal-overlap-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps([{k: v for k, v in row.items() if k != 'excluded'} for row in rows], indent=2))


if __name__ == '__main__':
    main()
