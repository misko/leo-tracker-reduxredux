from copy import deepcopy
from types import SimpleNamespace

import pytest
from probe_algo07v3_deferred_joint import DeferredJointFits, JointPairFailure

from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.operations.localization_v3_parallel import _ordered


def operation(context, probe, arm, method, *, optimizer):
    policy = context.get('numerical_policy')
    if policy:
        policy.receipt['problem_count'] += 5
        policy.receipt['reference_updates'].append({'fit': arm})
        policy.receipt['optimizer_calls'].append({'fit': arm, 'optimizer': optimizer})
    return dict(arm=arm, method=method, optimizer=optimizer, result=[1., 2.])


def audit(context, arm):
    if context.get('numerical_policy'):
        receipt = context['numerical_policy'].receipt
        receipt['reference_updates'].append({'audit': arm})
        receipt['problem_count'] += 1


@pytest.mark.parametrize('method', ['control', 'factorized', 'joint'])
@pytest.mark.parametrize('optimizer', ['lbfgsb', 'powell'])
@pytest.mark.parametrize('numerical', [False, True])
def test_complete_fit_audit_order_matches_original(method, optimizer, numerical):
    context = {'numerical_policy': NumericalPolicy()} if numerical else {}
    reference = deepcopy(context)
    values = []
    for arm in ('c0', 'fitted_c'):
        values.append(operation(reference, {}, arm, method, optimizer=optimizer))
        audit(reference, arm)
    paired = DeferredJointFits(context, {}, method, optimizer, operation,
                               lambda fn, arms: _ordered(fn, arms, workers=2))
    actual = [paired.fit('c0')]
    audit(context, 'c0')
    actual.append(paired.fit('fitted_c'))
    audit(context, 'fitted_c')
    assert actual == values
    if numerical:
        assert context['numerical_policy'].receipt == reference['numerical_policy'].receipt


@pytest.mark.parametrize('fault', [
    'missing', 'order', 'mutated_child', 'parent', 'between', 'replaced', 'nonfinite'])
def test_invalid_execution_cannot_publish_receipts(fault):
    context = {'numerical_policy': NumericalPolicy()}
    before = deepcopy(context['numerical_policy'].receipt)

    def mapper(fn, arms):
        results = [fn(arm) for arm in arms]
        if fault == 'missing':
            results.pop()
        if fault == 'order':
            results.reverse()
        if fault == 'mutated_child':
            results[1][2]['reference_limit_s'] = 15
        if fault == 'parent':
            context['numerical_policy'].receipt['problem_count'] = -1
        if fault == 'replaced':
            context['numerical_policy'] = NumericalPolicy()
        if fault == 'nonfinite':
            results[1][2]['reference_limit_s'] = float('nan')
        return results

    paired = DeferredJointFits(context, {}, 'joint', 'lbfgsb', operation, mapper)
    with pytest.raises(JointPairFailure):
        paired.fit('c0')
        assert fault == 'between'
        context['numerical_policy'].receipt['reference_updates'].clear()
        paired.fit('fitted_c')
    if fault in ('missing', 'order', 'mutated_child'):
        assert context['numerical_policy'].receipt == before


@pytest.mark.parametrize('custom', ['factory', 'policy'])
def test_unknown_context_keeps_original_serial_execution(custom):
    context = {'problem_factory': object()} if custom == 'factory' else {
        'numerical_policy': SimpleNamespace(receipt=deepcopy(NumericalPolicy().receipt))}

    def forbidden(*args):
        pytest.fail('custom context must not use process pairing')

    paired = DeferredJointFits(context, {}, 'joint', 'lbfgsb', operation, forbidden)
    assert paired.fit('c0')['arm'] == 'c0'
    assert paired.fit('fitted_c')['arm'] == 'fitted_c'


def test_real_stage_runner_can_replace_policy_before_each_fit_and_audit():
    context = {'numerical_policy': NumericalPolicy(reference_limit_s=15)}
    paired = DeferredJointFits(context, {}, 'joint', 'lbfgsb', operation,
                               lambda fn, arms: _ordered(fn, arms, workers=2))
    baseline_receipts, actual_receipts = {}, {}
    for arm in ('c0', 'fitted_c'):
        baseline = {'numerical_policy': NumericalPolicy()}
        operation(baseline, {}, arm, 'joint', optimizer='lbfgsb')
        baseline_receipts[arm] = deepcopy(baseline['numerical_policy'].receipt)
        context['numerical_policy'] = NumericalPolicy()
        assert paired.fit(arm)['arm'] == arm
        actual_receipts[arm] = deepcopy(context['numerical_policy'].receipt)
        context['numerical_policy'] = NumericalPolicy()
        audit(context, arm)
        assert context['numerical_policy'].receipt['optimizer_calls'] == []
    assert actual_receipts == baseline_receipts


def test_replacement_policy_must_have_the_exact_original_stage_configuration():
    context = {'numerical_policy': NumericalPolicy()}
    paired = DeferredJointFits(context, {}, 'joint', 'lbfgsb', operation,
                               lambda fn, arms: [fn(arm) for arm in arms])
    paired.fit('c0')
    context['numerical_policy'] = NumericalPolicy(reference_limit_s=15)
    with pytest.raises(JointPairFailure, match='Unexpected stage'):
        paired.fit('fitted_c')
