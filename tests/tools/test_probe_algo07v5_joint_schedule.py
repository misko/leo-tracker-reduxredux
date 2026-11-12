import copy
import itertools

import pytest
from probe_algo07v5_joint_schedule import ARMS, joint_passes, needs_factorized

from leo.analysis.localization_v3.joint_recovery import joint_numerical_only


def record(success=True, physical=True):
    return dict(trial=dict(result=dict(history=[dict(success=success)])),
                audit=dict(RF_qualified_arm=success and physical, incumbent_owner_changes=[],
                           phase_check=dict(phase_change_s=.001),
                           exact_incumbent_orbits=[dict(all_pass=True)],
                           checks=dict(incumbent_and_numerical=success,
                                       target_gates=physical)))


def test_deferred_decisions_match_all_4096_success_and_physical_gate_combinations():
    slots = [(method, arm) for method in ('control', 'joint', 'factorized') for arm in ARMS]
    for flags in itertools.product(range(4), repeat=6):
        experiment = {method: {} for method, _ in slots}
        for (method, arm), flag in zip(slots, flags, strict=True):
            experiment[method][arm] = record(bool(flag & 1), bool(flag & 2))
        before = copy.deepcopy(experiment)
        expected_pass = joint_passes(experiment)
        expected_retry = not expected_pass and joint_numerical_only(experiment)
        partial = {m: experiment[m] for m in ('control', 'joint')}
        need = needs_factorized(partial)
        actual_retry = bool(need and joint_numerical_only(experiment))
        assert (joint_passes(partial), actual_retry) == (expected_pass, expected_retry)
        assert experiment == before


@pytest.mark.parametrize('failure', ['owners', 'phase', 'orbit', 'other_check'])
@pytest.mark.parametrize('method', ['control', 'joint'])
@pytest.mark.parametrize('arm', ARMS)
def test_irreparable_partial_gate_eliminates_factorized_work(failure, method, arm):
    partial = {m: {a: record(success=False) for a in ARMS} for m in ('control', 'joint')}
    audit = partial[method][arm]['audit']
    if failure == 'owners':
        audit['incumbent_owner_changes'] = ['changed']
    elif failure == 'phase':
        audit['phase_check']['phase_change_s'] = .01000001
    elif failure == 'orbit':
        audit['exact_incumbent_orbits'][0]['all_pass'] = False
    else:
        audit['checks']['phase_resolution'] = False
    assert not needs_factorized(partial)


def test_numerical_failure_with_valid_physical_audits_requires_factorized():
    partial = {m: {a: record() for a in ARMS} for m in ('control', 'joint')}
    partial['joint']['c0'] = record(success=False)
    assert needs_factorized(partial)


def test_both_arms_required_before_deferral():
    with pytest.raises(ValueError, match='Both complete'):
        needs_factorized(dict(control=dict(c0=record()), joint={}))
