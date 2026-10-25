"""Freeze complete archived owners and full parent accepted-ID exclusion."""

import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
OWNERSHIP = Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')
CASES = tuple(f'DS24-{i:04d}' for i in range(10, 14))
ARMS = ('c0', 'fitted_c')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    began = time.monotonic()
    rows, cases, bindings = [], [], {}
    for case in CASES:
        paths = dict(tracks=SOURCE/case/'tracks.json',
                     parent=SOURCE/'family_cavity/position'/f'{case}.json',
                     ownership=OWNERSHIP/case/'parent.json')
        for path in paths.values():
            bindings[str(path)] = sha(path)
        tracks = read(paths['tracks'])
        lookup = {t['key']: (i, t) for i, t in enumerate(tracks)}
        assert len(lookup) == len(tracks)
        parent, ownership = read(paths['parent']), read(paths['ownership'])
        assert ownership['source_parent_sha256'] == sha(paths['parent'])
        assert ownership['source_tracks_sha256'] == sha(paths['tracks'])
        assert ownership['status'] == parent['status'] == 'complete'
        node = parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        entries = parent['selected']['entries'] if parent['accepted'] else parent['baseline_entries']
        accepted = {arm: set(ownership['coverage'][arm]['accepted_observation_ids']) for arm in ARMS}
        likelihood = {arm: set(ownership['coverage'][arm]['curved_observation_ids'] +
                               ownership['coverage'][arm]['predictive_observation_ids']) for arm in ARMS}
        occupied = set.union(*accepted.values())
        active = set(ownership['coverage']['c0']['active_curved_families']) | {e['candidate_index'] for e in entries}
        active_other = set(ownership['coverage']['fitted_c']['active_curved_families']) | {e['candidate_index'] for e in entries}
        assert active == active_other
        mask = parent['original_mask']
        cursor, eligible = 0, []
        for index, (row, alias) in enumerate(zip(node['seed']['rows'], node['aliases'], strict=True)):
            i, track = lookup[row['component']]
            ids = track['observation_ids']
            assert row['active_curvature'] and len(ids) == row['points'] == len(track['times'])
            assert len(ids) == len(set(ids))
            selected = mask[cursor:cursor+len(ids)]
            cursor += len(ids)
            assert len(selected) == len(ids)
            overlaps = {arm: sorted(set(ids) & accepted[arm]) for arm in ARMS}
            reasons = []
            if any(selected):
                reasons.append('contains parent curved likelihood IDs')
            if set(ids) & occupied:
                reasons.append('overlaps complete parent accepted IDs, including postfit extensions')
            rec = dict(case=case, component=track['key'], track_index=i, row_index=index,
                       candidate_index=row['candidate_index'], candidate_norad=row['candidate_norad'],
                       alias=alias, points=len(ids), span_s=max(track['times'])-min(track['times']),
                       start_s=min(track['times']), end_s=max(track['times']),
                       receiver=track['receiver'], channel=track['channel'], rf_hz=track['rf_hz'],
                       observation_ids=ids, archived_nomination_compatible=row['compatible'],
                       archived_feasible_candidates=row.get('feasible_candidates'),
                       family_has_parent_likelihood=row['candidate_index'] in active,
                       accepted_ID_overlap=overlaps,
                       likelihood_ID_overlap={a: sorted(set(ids) & likelihood[a]) for a in ARMS},
                       eligible=not reasons, exclusion_reasons=reasons,
                       identity_qualified=False)
            rows.append(rec)
            if rec['eligible']:
                eligible.append(rec)
        assert cursor == len(mask)
        graph_ids = [oid for rec in rows if rec['case'] == case for oid in rec['observation_ids']]
        assert len(graph_ids) == len(set(graph_ids))
        cases.append(dict(case=case, all_native_owners=len(tracks),
                          original_curved_graph_owners=len(node['seed']['rows']),
                          eligible_complete_curved_owners=len(eligible),
                          eligible_new_families=sorted({e['candidate_norad'] for e in eligible if not e['family_has_parent_likelihood']}),
                          parent_ownership_path=str(paths['ownership']),
                          parent_ownership_sha256=sha(paths['ownership']),
                          fixed_RF_endpoints={a: parent['policy_arms'][a]['endpoint_east_north_km'] for a in ARMS},
                          original_likelihood_counts={a:len(likelihood[a]) for a in ARMS},
                          complete_accepted_counts={a:len(accepted[a]) for a in ARMS}))
    result = dict(cases=cases, sources=rows, input_bindings=bindings,
                  pool_definition='all original curved graph owners with the unchanged canonical reference-node candidate/alias, minus any complete parent accepted-ID overlap in either arm; no trimming',
                  other_native_owners='retained in full tracks hash; no new catalogue nomination or curvature/label selection',
                  seconds=time.monotonic()-began, new_position_fits=0,
                  GPS_or_position_errors_used=False, identity_qualification=False)
    write(HERE/'inventory.json', result)
    print(json.dumps(dict(cases=cases, seconds=result['seconds']), indent=2))


if __name__ == '__main__':
    main()
