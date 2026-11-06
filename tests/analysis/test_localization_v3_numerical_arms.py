from copy import deepcopy

import pytest

from leo.analysis.localization_v3.numerical_policy import NumericalPolicy, map_calibration_arms
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms


@pytest.mark.parametrize('mapper', [None, map, map_initial_arms])
def test_ordered_receipts_and_result_match_serial_execution(mapper):
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
    assert map_calibration_arms(context, operation, ('c0', 'fitted_c'), mapper) == [
        'c0-complete', 'fitted_c-complete']
    assert context['numerical_policy'] is policy and policy.receipt == expected


def test_child_failure_aborts_without_partial_receipt():
    policy = NumericalPolicy()
    original = deepcopy(policy.receipt)
    context = dict(numerical_policy=policy)

    def operation(arm):
        context['numerical_policy'].receipt['problem_count'] += 2
        if arm == 'fitted_c':
            raise ValueError('incomplete fit')
        return arm

    with pytest.raises(ParallelFitFailure, match='incomplete fit'):
        map_calibration_arms(context, operation, ('c0', 'fitted_c'), map_initial_arms)
    assert context['numerical_policy'] is policy and policy.receipt == original


@pytest.mark.parametrize('kind', ['constant', 'prefix', 'count', 'signed_zero'])
def test_invalid_receipt_cannot_change_parent(kind):
    policy = NumericalPolicy()
    policy.receipt['reference_updates'].append({'old': 0.0})
    original = deepcopy(policy.receipt)
    context = dict(numerical_policy=policy)

    def operation(arm):
        receipt = context['numerical_policy'].receipt
        if kind == 'constant':
            receipt['reference_limit_s'] = 15
        elif kind == 'prefix':
            receipt['reference_updates'][0]['old'] = 1.0
        elif kind == 'signed_zero':
            receipt['reference_updates'][0]['old'] = -0.0
        else:
            receipt['problem_count'] = -1

    with pytest.raises(ValueError):
        map_calibration_arms(context, operation, ('c0', 'fitted_c'), map_initial_arms)
    assert context['numerical_policy'] is policy and policy.receipt == original


@pytest.mark.parametrize('kind', ['reverse', 'missing', 'extra'])
def test_transport_order_and_completeness_required_before_commit(kind):
    policy = NumericalPolicy()
    original = deepcopy(policy.receipt)
    context = dict(numerical_policy=policy)

    def operation(arm):
        context['numerical_policy'].receipt['problem_count'] += 1
        return arm

    def mapper(operation, arms):
        rows = list(map(operation, arms))
        return rows[::-1] if kind == 'reverse' else rows[:1] if kind == 'missing' else rows + rows

    with pytest.raises(ValueError):
        map_calibration_arms(context, operation, ('c0', 'fitted_c'), mapper)
    assert policy.receipt == original
