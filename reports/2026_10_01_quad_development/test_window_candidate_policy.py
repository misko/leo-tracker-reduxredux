from copy import deepcopy
import pytest
from window_candidate_policy import eligible_indices, choose, rank_targets


def example():
    specs = [('A', ['a']), ('B', ['b']), ('C', ['c']), ('AB', ['a', 'b']),
             ('CD', ['c', 'd']), ('Q', ['a', 'b', 'c', 'd'])]
    return [dict(unit=u, scans=s, block='block', policy='first') for u, s in specs]


def test_single_and_pair_never_borrow_future_or_sibling_scans():
    candidates = example()
    a = dict(unit_id='A', scans=['a'], block_id='block')
    ab = dict(unit_id='AB', scans=['a', 'b'], block_id='block')
    assert eligible_indices(candidates, a) == [0]
    assert eligible_indices(candidates, ab) == [0, 1, 3]
    assert eligible_indices(candidates, ab, True) == [3]
    wrong = deepcopy(candidates[0]); wrong['block'] = 'another'
    assert eligible_indices([wrong], a) == []


def test_ties_prefer_baseline_then_frozen_order_and_reject_missing_data():
    assert choose([1., 1.+5e-7, 1.], [0, 1, 2], 2) == 2
    assert choose([3., 3., 1.], [0, 1, 2], 2) == 0
    for scores, indices, baseline in (([1.], [], 0), ([1.], [0], 1), ([float('nan')], [0], 0)):
        with pytest.raises(ValueError): choose(scores, indices, baseline)


def test_rankings_ignore_reference_metadata_and_sum_only_target_scans():
    candidates = example()
    targets = [dict(unit_id='AB', scans=['a', 'b'], block_id='block', size=2)]
    matrix = [[3, 0, 100, 1, 100, 100], [0, 1, 100, 1, 100, 100], [0]*6, [0]*6]
    original = rank_targets(candidates, ['a', 'b', 'c', 'd'], matrix, targets)
    assert original[0]['contained'] == 0 and original[0]['target_only'] == 3
    for i, c in enumerate(candidates): c['error_m'] = 1e9 if i == 0 else 0
    assert rank_targets(candidates, ['a', 'b', 'c', 'd'], matrix, targets) == original
