from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import recovery_controller as controller
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.analysis.localization_v5.joint_schedule import JointScheduleFailure
from leo.contracts.localization_v5 import joint_schedule_policy
from leo.operations.localization_v3_parallel import _ordered
from leo.operations.localization_v5_joint import JointScheduleFactory
from tests.analysis.test_localization_v3_recovery_controller import setup
from tests.analysis.test_localization_v5_control_reuse import fixture


@pytest.mark.parametrize('numerical', [False, True])
@pytest.mark.parametrize('paired', [False, True])
@pytest.mark.parametrize('mode', ['passed', 'irreparable', 'retry', 'factorized_blocks', 'failed'])
def test_schedule_preserves_selection_and_each_remaining_owned_receipt(
    monkeypatch, numerical, paired, mode
):
    evidence = setup(monkeypatch)
    monkeypatch.setattr(controller, 'probe_joint', lambda *a: {})

    def fit(context, probe, arm, method, *, optimizer):
        policy = context.get('numerical_policy')
        if policy:
            policy.receipt['problem_count'] += 5
            policy.receipt['reference_updates'].append(dict(fit=arm, method=method))
            policy.receipt['optimizer_calls'].append(dict(fit=arm, method=method))
        success = not (mode in ('retry', 'factorized_blocks') and optimizer == 'lbfgsb'
                       and method == 'control' and arm == 'fitted_c')
        return dict(protocol=dict(method=method, arm=arm, optimizer=optimizer),
                    result=dict(history=[dict(success=success)], endpoint_east_north_km=[0., 0.],
                                endpoint_latlon=[37., -122.], negative_twice_elbo=100.))

    def audit(context, inventory, trial, control, **kwargs):
        pr = trial['protocol']
        if context.get('numerical_policy'):
            receipt = context['numerical_policy'].receipt
            receipt['problem_count'] += 1
            receipt['reference_updates'].append(dict(audit=pr['arm'], method=pr['method']))
        success = trial['result']['history'][-1]['success']
        physical = not ((mode == 'irreparable' and pr['method'] == 'joint')
                        or (mode == 'factorized_blocks' and pr['method'] == 'factorized'))
        return dict(RF_qualified_arm=success and physical,
                    owners={'old': 1, 'n0': 2, 'n1': 3}, incumbent_owner_changes=[],
                    phase_check=dict(phase_change_s=.001),
                    exact_incumbent_orbits=[dict(all_pass=True)],
                    checks=dict(incumbent_and_numerical=success, phase_resolution=physical))

    monkeypatch.setattr(controller, 'fit_joint', fit)
    monkeypatch.setattr(controller, 'audit_joint', audit)

    def run(enabled):
        context, _, bound = fixture()
        factory = JointScheduleFactory(bound, joint_schedule_policy())
        receipts, states, stages = {}, [], []

        def stage(name, operation):
            stages.append(name)
            if numerical:
                context['numerical_policy'] = NumericalPolicy()
            if mode == 'failed' and name == 'joint-fitted_c-audit':
                return False, None
            value = operation()
            if numerical:
                receipts[name] = deepcopy(context['numerical_policy'].receipt)
            return True, value

        options = {'joint_schedule_factory': factory} if enabled else {}
        if paired:
            options['map_joint_arms'] = lambda fn, arms: _ordered(fn, arms, workers=2)
        result = controller.recover_tracks(context, evidence, run_stage=stage,
                                          discovery_allowed=lambda: True,
                                          on_selection=states.append, **options)
        return result, receipts, states, stages, factory.provenance()

    baseline, old_receipts, old_states, _, _ = run(False)
    candidate, receipts, states, stages, work = run(True)
    assert {k: v for k, v in candidate.items() if k != 'stages'} == {
        k: v for k, v in baseline.items() if k != 'stages'}
    assert states == old_states
    assert all(receipt == old_receipts[name] for name, receipt in receipts.items())
    assert work['counts']['in_progress'] == 0
    if mode in ('passed', 'irreparable'):
        assert not any('factorized-' in name for name in stages)
        assert work['counts']['factorized_omitted'] == 1
    elif mode == 'retry':
        assert 'factorized-c0' in stages and 'retry-factorized-c0' not in stages
        assert work['counts']['factorized_computed'] == 1
        assert work['counts']['factorized_omitted'] == 1
    elif mode == 'factorized_blocks':
        assert 'factorized-c0' in stages and not any(n.startswith('retry-') for n in stages)
        assert work['counts']['factorized_computed'] == 1
    else:
        assert work['counts']['failed'] == work['counts']['factorized_not_reached'] == 1


def test_manifest_integrity_fault_escapes_scientific_fallback(monkeypatch):
    evidence = setup(monkeypatch)
    context, _, bound = fixture()
    factory = JointScheduleFactory(bound, joint_schedule_policy())

    def probe(*args):
        bound.manifest['changed'] = True
        return {}

    monkeypatch.setattr(controller, 'probe_joint', probe)
    with pytest.raises(JointScheduleFailure, match='manifest binding'):
        controller.recover_tracks(context, evidence,
                                  run_stage=lambda n, operation: (True, operation()),
                                  discovery_allowed=lambda: True, joint_schedule_factory=factory)
