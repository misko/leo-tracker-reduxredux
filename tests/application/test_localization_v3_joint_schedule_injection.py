from dataclasses import replace
from types import SimpleNamespace

import pytest

from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from tests.application.test_localization_v3_engine import fixture


def test_engine_routes_joint_factory_only_to_predictive_and_numerical_recovery(monkeypatch):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    factory = object()
    engine.infer_prepared(prepared, region, catalogue,
                          identities=['scan'], collect_history=object(),
                          execution=replace(execution, joint_schedule_factory=factory))
    for name, _, kwargs in calls:
        if name in ('recover_predictive_checkpoint', 'recover_numerical_checkpoint'):
            assert kwargs['joint_schedule_factory'] is factory
        else:
            assert 'joint_schedule_factory' not in kwargs


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('mode', ['predictive', 'numerical'])
def test_checkpoint_preserves_factory_policy_only_when_enabled(monkeypatch, mode, enabled):
    factory, seen = SimpleNamespace(policy={'id': 'tiny'}), []
    method = 'recover_tracks' if mode == 'predictive' else 'replay_recovery'
    monkeypatch.setattr(application, method,
                        lambda *a, **kw: seen.append(kw) or {'selected': None})
    prepared = dict(status='track_recovery_prepared', recovery_context={}, inventory={})
    options = dict(run_stage=lambda name, operation: (True, operation()),
                   discovery_allowed=lambda: True, clock=lambda: 0.)
    if enabled:
        options['joint_schedule_factory'] = factory
    if mode == 'predictive':
        result = application.recover_predictive_checkpoint(
            prepared, inventory_seconds=0., **options)
        assert ('joint_schedule_policy' in result) is enabled
    else:
        predictive = dict(status='predictive_recovery_evaluated', recovery={}, completed_stages={})
        if enabled:
            predictive['joint_schedule_policy'] = factory.policy
        application.recover_numerical_checkpoint(
            prepared, predictive, charge_reused=lambda _: None, **options)
        assert ('completed_joint_schedule_policy' in seen[0]) is enabled
    assert (seen[0]['joint_schedule_factory'] is factory) if enabled else (
        'joint_schedule_factory' not in seen[0])
