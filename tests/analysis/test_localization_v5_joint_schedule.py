from copy import deepcopy
from itertools import product

import pytest

from leo.analysis.localization_v3.joint_recovery import joint_numerical_only
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.analysis.localization_v5.joint_schedule import (
    ARMS,
    JointSchedule,
    JointScheduleFailure,
    omission_reason,
)
from tests.analysis.test_localization_v5_control_reuse import fixture


def record(success=True, physical=True):
    return dict(trial=dict(result=dict(history=[dict(success=success)])),
                audit=dict(RF_qualified_arm=success and physical, incumbent_owner_changes=[],
                           phase_check=dict(phase_change_s=.001),
                           exact_incumbent_orbits=[dict(all_pass=True)],
                           checks=dict(incumbent_and_numerical=success, target_gates=physical)))


def experiment(success=True, physical=True):
    return {m: {a: record(success, physical) for a in ARMS}
            for m in ('control', 'joint', 'factorized')}


def test_original_decision_matches_all_4096_success_and_physical_combinations():
    slots = [(m, a) for m in ('control', 'joint', 'factorized') for a in ARMS]
    for flags in product(range(4), repeat=6):
        values = {m: {} for m, _ in slots}
        for (m, a), flag in zip(slots, flags, strict=True):
            values[m][a] = record(bool(flag & 1), bool(flag & 2))
        before = deepcopy(values)
        passed = all(values[m][a]['audit']['RF_qualified_arm']
                     for m in ('control', 'joint') for a in ARMS)
        original_retry = not passed and joint_numerical_only(values)
        reason = omission_reason({m: values[m] for m in ('control', 'joint')})
        assert bool(reason is None and joint_numerical_only(values)) == original_retry
        assert values == before


@pytest.mark.parametrize('physical', [True, False])
def test_omission_is_bound_to_complete_unchanged_paired_evidence(physical):
    context, _, bound = fixture()
    policy = JointSchedule(context, 'lbfgsb', bound, lambda: 'binding')
    values = experiment(physical=physical)
    assert policy.methods == ('control', 'joint', 'factorized')
    assert policy.omit_factorized(values)
    values['factorized'] = {}
    policy.finish(values, True)
    assert not policy.numerical_only(values)
    row = policy.snapshot()
    assert row['completed_arms'] == 0 and row['factorized'] == 'omitted'
    assert row['reason'] == ('joint_already_qualified' if physical else 'numerical_retry_ruled_out')
    row['state'] = 'changed'
    assert policy.snapshot()['state'] == 'completed'
    for m in ('control', 'joint'):
        for a in ARMS:
            values[m][a] = record(success=False)
    with pytest.raises(JointScheduleFailure, match='evidence changed'):
        policy.numerical_only(values)


@pytest.mark.parametrize('change', ['callback', 'factory', 'policy', 'policy_callback',
                                   'scan', 'bound'])
def test_unknown_context_retains_original_schedule(change):
    context, _, bound = fixture()
    if change == 'callback':
        context['scan'].callback = lambda: None
    elif change == 'factory':
        context['problem_factory'] = lambda: None
    elif change == 'policy':
        context['numerical_policy'] = object()
    elif change == 'policy_callback':
        context['numerical_policy'] = NumericalPolicy()
        context['numerical_policy'].minimize = lambda: None
    elif change == 'scan':
        context['scan'] = object()
    else:
        context['scan'].bound = object()
    policy = JointSchedule(context, 'lbfgsb', bound, lambda: 'binding')
    assert policy.methods == ('control', 'factorized', 'joint')
    assert not policy.omit_factorized({})
    policy.finish(experiment(), True)
    assert policy.snapshot()['eligible'] is False


def test_known_stage_policies_can_be_replaced_and_numerical_failure_keeps_factorized():
    context, _, bound = fixture()
    context['numerical_policy'] = NumericalPolicy()
    policy = JointSchedule(context, 'lbfgsb', bound, lambda: 'binding')
    context['numerical_policy'] = NumericalPolicy()
    values = experiment()
    values['control']['fitted_c'] = record(success=False)
    assert not policy.omit_factorized(values)
    policy.finish(values, True)
    assert policy.numerical_only(values)
    assert policy.snapshot()['completed_arms'] == 2


@pytest.mark.parametrize('phase', ['not_reached', 'incomplete', 'computed'])
def test_failure_accounting_does_not_turn_partial_work_into_complete_work(phase):
    context, _, bound = fixture()
    policy = JointSchedule(context, 'lbfgsb', bound, lambda: 'binding')
    values = experiment(success=False)
    if phase != 'not_reached':
        assert not policy.omit_factorized(values)
    if phase == 'not_reached':
        values['factorized'] = {}
    elif phase == 'incomplete':
        values['factorized'].pop('fitted_c')
    policy.finish(values, False)
    assert policy.snapshot()['state'] == 'failed'
    assert policy.snapshot()['factorized'] == phase


@pytest.mark.parametrize('change', ['identity', 'context', 'missing_arm', 'missing_audit'])
def test_execution_integrity_failures_are_explicit(change):
    context, _, bound = fixture()
    identity = ['binding']
    policy = JointSchedule(context, 'lbfgsb', bound, lambda: identity[0])
    values = experiment()
    if change == 'identity':
        identity[0] = 'other'
    elif change == 'context':
        context['numerical_policy'] = object()
    elif change == 'missing_arm':
        values['joint'].pop('c0')
    else:
        del values['joint']['c0']['audit']
    with pytest.raises(JointScheduleFailure):
        policy.omit_factorized(values)
