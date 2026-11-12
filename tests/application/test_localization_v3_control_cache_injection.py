from dataclasses import replace
from types import SimpleNamespace

import pytest

from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from tests.application.test_localization_v3_engine import fixture


def test_engine_scopes_control_factory_to_predictive_and_numerical(monkeypatch):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    factory = object()
    engine.infer_prepared(prepared, region, catalogue,
                          identities=['scan'], collect_history=object(),
                          execution=replace(execution, inclusion_control_factory=factory))
    for name, _, kwargs in calls:
        if name in ('recover_predictive_checkpoint', 'recover_numerical_checkpoint'):
            assert kwargs['inclusion_control_factory'] is factory
        else:
            assert 'inclusion_control_factory' not in kwargs


@pytest.mark.parametrize('injected', [False, True])
@pytest.mark.parametrize('mode', ['predictive', 'numerical'])
def test_checkpoint_forwards_factory_and_retains_policy_only_when_enabled(
    monkeypatch, mode, injected
):
    factory = SimpleNamespace(policy={'id': 'tiny'})
    seen = []
    method = 'recover_tracks' if mode == 'predictive' else 'replay_recovery'
    monkeypatch.setattr(application, method,
                        lambda *args, **kwargs: seen.append(kwargs) or {'selected': None})
    prepared = dict(status='track_recovery_prepared', recovery_context={}, inventory={})
    kwargs = dict(run_stage=lambda name, operation: (True, operation()),
                  discovery_allowed=lambda: True, clock=lambda: 0.0)
    if injected:
        kwargs['inclusion_control_factory'] = factory
    if mode == 'predictive':
        result = application.recover_predictive_checkpoint(prepared, inventory_seconds=0., **kwargs)
        assert ('inclusion_control_policy' in result) is injected
    else:
        predictive = dict(status='predictive_recovery_evaluated', recovery={}, completed_stages={})
        if injected:
            predictive['inclusion_control_policy'] = factory.policy
        application.recover_numerical_checkpoint(
            prepared, predictive, charge_reused=lambda _: None, **kwargs)
        assert ('completed_inclusion_control_policy' in seen[0]) is injected
    assert (seen[0]['inclusion_control_factory'] is factory) if injected else (
        'inclusion_control_factory' not in seen[0])
