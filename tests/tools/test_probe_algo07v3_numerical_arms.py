from copy import deepcopy

import pytest
from probe_algo07v3_numerical_arms import NumericalPolicy, receipt_map, transform

from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms


@pytest.mark.parametrize('mapper', [map, map_initial_arms])
def test_complete_receipts_merge_in_original_arm_order(mapper):
    policy = NumericalPolicy()
    policy.receipt.update(problem_count=7, reference_updates=[{'old': True}],
                          optimizer_calls=[{'prior': 2}])
    context = dict(numerical_policy=policy)
    expected = deepcopy(policy.receipt)

    def operation(arm):
        local = context['numerical_policy']
        local.receipt['problem_count'] += 3
        local.receipt['reference_updates'].append({'arm': arm})
        local.receipt['optimizer_calls'].extend([{'arm': arm, 'round': i} for i in range(2)])
        return arm + '-complete'

    for arm in ('c0', 'fitted_c'):
        expected['problem_count'] += 3
        expected['reference_updates'].append({'arm': arm})
        expected['optimizer_calls'].extend([{'arm': arm, 'round': i} for i in range(2)])
    assert receipt_map(context, operation, ('c0', 'fitted_c'), mapper) == [
        'c0-complete', 'fitted_c-complete']
    assert context['numerical_policy'] is policy
    assert policy.receipt == expected


def test_failed_child_does_not_commit_partial_receipts():
    policy = NumericalPolicy()
    original = deepcopy(policy.receipt)
    context = dict(numerical_policy=policy)

    def operation(arm):
        context['numerical_policy'].receipt['problem_count'] += 2
        if arm == 'fitted_c':
            raise ValueError('incomplete fit')
        return arm

    with pytest.raises(ParallelFitFailure, match='incomplete fit'):
        receipt_map(context, operation, ('c0', 'fitted_c'), map_initial_arms)
    assert context['numerical_policy'] is policy and policy.receipt == original


@pytest.mark.parametrize('kind', ['constant', 'prefix', 'count'])
def test_invalid_child_receipt_cannot_change_parent(kind):
    policy = NumericalPolicy()
    policy.receipt['reference_updates'].append({'old': True})
    original = deepcopy(policy.receipt)
    context = dict(numerical_policy=policy)

    def operation(arm):
        receipt = context['numerical_policy'].receipt
        if kind == 'constant':
            receipt['reference_limit_s'] = 15
        elif kind == 'prefix':
            receipt['reference_updates'][0]['old'] = False
        else:
            receipt['problem_count'] = -1

    with pytest.raises(ValueError):
        receipt_map(context, operation, ('c0', 'fitted_c'), map_initial_arms)
    assert context['numerical_policy'] is policy and policy.receipt == original


@pytest.mark.parametrize('name', ['fit_new', 'fit_shared'])
def test_transform_only_changes_execution_mapper(name):
    candidate, original, changed = transform(name)
    assert candidate.__name__ == name
    assert original.replace(
        'mapper = map if d.get("numerical_policy") is not None else (map_arms or map)',
        'mapper = lambda operation, arms: _receipt_map(d, operation, arms, map_arms)',
    ) == changed
