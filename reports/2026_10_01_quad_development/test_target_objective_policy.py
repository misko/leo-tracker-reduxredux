from copy import deepcopy
import pytest
from target_objective_policy import select


def fixture():
    target = dict(unit_id='AB', block_id='b', scans=['a', 'b'], size=2)
    candidates = [dict(unit='A', block='b', scans=['a'], size=1, policy='first'),
                  dict(unit='AB', block='b', scans=['a', 'b'], size=2, policy='first'),
                  dict(unit='AB', block='b', scans=['a', 'b'], size=2, policy='original_winner')]
    return candidates, target


def test_smaller_constituent_objective_cannot_win_target_selection():
    candidates, target = fixture()
    assert select(candidates, [-1e20, 100, 90], target) == dict(baseline=1, eligible=[1, 2], selected=2)


def test_tie_keeps_first_fit_and_error_metadata_does_not_change_choice():
    candidates, target = fixture()
    assert select(candidates, [0, 100, 100-5e-7], target)['selected'] == 1
    original = select(candidates, [0, 100, 90], target)
    for c in candidates: c['error_m'] = 0 if c['policy'] == 'first' else 1e9
    assert select(candidates, [0, 100, 90], target) == original


def test_inconsistent_target_binding_and_nonfinite_objective_fail():
    candidates, target = fixture()
    wrong = deepcopy(candidates); wrong[2]['scans'] = ['a']
    with pytest.raises(ValueError): select(wrong, [0, 100, 90], target)
    with pytest.raises(ValueError): select(candidates, [0, 100, float('nan')], target)
