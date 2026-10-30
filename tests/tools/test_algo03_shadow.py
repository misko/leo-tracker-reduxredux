"""Shadow admission must remain deterministic and preserve paired ownership."""
import copy
import json
import os
import sys

import pytest

from algo03_shadow_worker import select_targets, scoped_pair, run, joint_pair
from run_algo03_shadow import check_read_audit
from algo03_inventory import publication_support


def test_ranking_ignores_position_error_and_requires_both_arms():
    rows = []
    for arm in ('c0', 'fitted_c'):
        for tid, n in [('z', 31), ('b', 30), ('a', 30), ('partial', 80)]:
            ids = [tid + str(i) for i in range(n)]
            rows.append(dict(arm=arm, track_id=tid, current_large=True,
                             current=dict(wholly_unassociated=tid != 'partial'),
                             observation_ids=ids, all_track_observation_ids=ids + (['already_owned'] if tid == 'partial' else []),
                             evaluation_error_km=0 if tid == 'partial' else 10))
    chosen, total = select_targets(dict(tracks=rows), limit=2)
    assert total == 4
    assert [r['track_id'] for r in chosen] == ['partial', 'z']
    assert chosen[0]['inactive_fragment'] is True
    rows[-3]['observation_ids'] = ['mismatched-arm']
    chosen, total = select_targets(dict(tracks=rows))
    assert total == 3


def test_joint_selection_excludes_partial_shared_same_family_and_overlap():
    def candidate(norad, ids, **kw):
        return dict(kind='new_family', targets=[dict(norad=norad, observation_ids=ids)], **kw)
    a = candidate(1, ['a', 'b'])
    b = candidate(2, ['c'])
    overlap = candidate(3, ['a', 'x'])
    partial = candidate(4, list('defghi'), inactive_fragment=True)
    same = candidate(1, ['j'])
    pair = joint_pair([a, b, overlap, partial, same])
    assert sum(len(t['observation_ids']) for q in pair for t in q['targets']) == 3
    assert len({q['targets'][0]['norad'] for q in pair}) == 2
    assert partial not in pair
    assert not (a in pair and overlap in pair)


def test_only_scored_targets_count_and_ownership_must_match():
    inv = dict(policy={a: dict(proposed_associated_ids=['old']) for a in ('c0', 'fitted_c')})
    arms = {a: dict(endpoint_east_north_km=[0, 0], endpoint_latlon=[37.906, -122.545],
                   negative_twice_elbo=123) for a in inv['policy']}
    owners = {a: {'old': 1, 'target': 2, 'incidental': 3} for a in arms}
    target = dict(observation_ids=['target'], norad=2)
    result = scoped_pair(inv, arms, owners, [target])
    assert result['c0']['associated_ids'] == ['old', 'target']
    assert result['fitted_c']['added_points'] == 1
    broken = copy.deepcopy(owners)
    broken['fitted_c']['old'] = 3
    with pytest.raises(ValueError, match='Paired'):
        scoped_pair(inv, arms, broken, [target])
    with pytest.raises(ValueError, match='Duplicate'):
        scoped_pair(inv, arms, owners, [target, target])
    del broken['c0']['old']
    with pytest.raises(ValueError, match='Lost'):
        scoped_pair(inv, arms, broken, [target])


def test_published_baseline_uses_replayed_owners_and_excludes_unreported_extensions():
    baseline = dict(arms={a: dict(gates=dict(tracks=[dict(observation_ids=['old'])]),
                                 linear_gates=[dict(observation_ids=['linear'], norad=2)])
                         for a in ('c0', 'fitted_c')})
    replayed = {a: dict(old=1, linear=2, incidental=3) for a in baseline['arms']}
    support = publication_support(baseline, replayed)
    assert support['c0']['owners'] == dict(old=1, linear=2)
    assert support['c0']['unreported_postfit_ids'] == ['incidental']
    replayed['fitted_c']['linear'] = 5
    with pytest.raises(ValueError, match='original ownership'):
        publication_support(baseline, replayed)


def test_corrupt_snapshot_falls_back_without_launching_science(tmp_path):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'descriptor.json').write_text(json.dumps(dict(
        root=str(snapshot), terminal={'position': {'latitude_deg': 1}}, job_id='j',
        files={'missing': 'sha256:wrong'})))
    result = run(tmp_path, 10)
    assert result['decision'] == 'ALGO02_fallback'
    assert result['selected'] is None
    assert result['stages'] == []
    assert (tmp_path / 'decision.json').exists()


def test_read_audit_requires_every_child_and_no_denials(tmp_path):
    directory = tmp_path / 'read_receipts'
    directory.mkdir()
    parent = dict(pid=100, parent_pid=os.getpid(), python_spawns=[sys.executable], denied_paths=[])
    (directory / '100.json').write_text(json.dumps(parent))
    assert not check_read_audit(tmp_path, 100)['verified']
    child = dict(pid=101, parent_pid=100, python_spawns=[], denied_paths=[])
    (directory / '101.json').write_text(json.dumps(child))
    assert check_read_audit(tmp_path, 100)['verified']
    child['denied_paths'] = ['/some/other/report.json']
    (directory / '101.json').write_text(json.dumps(child))
    assert not check_read_audit(tmp_path, 100)['verified']
