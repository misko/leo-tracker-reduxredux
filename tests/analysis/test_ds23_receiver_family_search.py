import numpy as np
import pytest

from ds23_receiver_family_search import (
    apply_proposals, curve_blocks, fine_receiver_basis, replacement_penalty, orphan_predictive_labels,
)
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def test_finer_receiver_covariance_preserves_pointwise_prior_variance_budget():
    grid = np.linspace(0., 300., 301)
    old = projected_receiver_basis(grid)
    new = fine_receiver_basis(grid)
    assert new.shape[1] > old.shape[1]
    np.testing.assert_allclose(np.mean(np.sum(new**2, axis=1)),
                               np.mean(np.sum(old**2, axis=1)), rtol=1e-13)


def test_blocks_require_active_curvature_on_multiple_channels_of_the_same_receiver():
    rows = [dict(candidate_index=2) for _ in range(4)]
    tracks = [dict(receiver=1, channel=1), dict(receiver=1, channel=5),
              dict(receiver=2, channel=1), dict(receiver=2, channel=5)]
    mask = np.r_[np.ones(12, bool), np.ones(12, bool), np.ones(12, bool), np.zeros(12, bool)]
    groups = curve_blocks(rows, list(range(4)), [slice(i*12, (i+1)*12) for i in range(4)], mask, tracks)
    assert len(groups) == 1 and groups[0]['receiver'] == 1
    assert groups[0]['points'] == 24 and groups[0]['row_indices'] == [0, 1]


def test_block_identity_change_preserves_measurements_and_other_receiver():
    node = dict(seed=dict(rows=[dict(candidate_index=2, candidate_norad=100),
                               dict(candidate_index=2, candidate_norad=100)]), aliases=[0, 1])
    entries = [dict(candidate_index=2, norad=100, track_index=i, observation_ids=[str(i)], alias=0)
               for i in range(2)]
    tracks = [dict(receiver=1), dict(receiver=2)]
    proposal = dict(block=dict(row_indices=[0], original_index=2, receiver=1),
                    candidate_index=7, norad=200, aliases=[-1])
    changed, predictive = apply_proposals(node, entries, tracks, [proposal])
    assert changed['seed']['rows'][0]['candidate_norad'] == 200
    assert changed['seed']['rows'][1]['candidate_norad'] == 100
    assert changed['aliases'] == [-1, 1] and node['aliases'] == [0, 1]
    assert [r['norad'] for r in predictive] == [200, 100]
    assert [r['observation_ids'] for r in predictive] == [['0'], ['1']]
    assert entries[0]['norad'] == 100
    with pytest.raises(ValueError, match='overlapping'):
        apply_proposals(node, entries, tracks, [proposal, proposal])


def test_discrete_search_cost_increases_with_catalogue_and_extra_replacements():
    assert replacement_penalty(100, 2, 4) > replacement_penalty(100, 1, 4) > replacement_penalty(10, 1, 4)
    assert replacement_penalty(100, 0, 0) == pytest.approx(2*np.log(2))


def test_two_family_swap_does_not_cascade_predictive_replacements():
    node = dict(seed=dict(rows=[dict(candidate_index=j, candidate_norad=j) for j in (2, 7)]), aliases=[0, 0])
    entries = [dict(candidate_index=j, norad=j, track_index=i) for i, j in enumerate((2, 7))]
    proposals = [dict(block=dict(row_indices=[i], original_index=j, receiver=1),
                      candidate_index=k, norad=k, aliases=[0])
                 for i, (j, k) in enumerate(((2, 7), (7, 2)))]
    _, predictive = apply_proposals(node, entries, [dict(receiver=1), dict(receiver=1)], proposals)
    assert [r['candidate_index'] for r in predictive] == [7, 2]


def test_missing_predictive_family_is_detected_without_deleting_its_measurements():
    node=dict(seed=dict(rows=[dict(candidate_index=7)]))
    entries=[dict(candidate_index=2,observation_ids=['retained']),dict(candidate_index=7)]
    assert orphan_predictive_labels(node,entries)==[2]
    assert entries[0]['observation_ids']==['retained']
