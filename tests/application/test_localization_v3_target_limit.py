from dataclasses import replace

import pytest

from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from tests.application.test_localization_v3_engine import fixture


@pytest.mark.parametrize('limit', [None, 0, 4, 8])
def test_engine_applies_target_limit_only_to_inventory_selection(monkeypatch, limit):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    engine.infer_prepared(prepared, region, catalogue,
                          identities=['scan'], collect_history=object(),
                          execution=replace(execution, recovery_target_limit=limit))
    for name, _, kwargs in calls:
        if name == 'prepare_track_recovery' and limit is not None:
            assert kwargs['recovery_target_limit'] == limit
        else:
            assert 'recovery_target_limit' not in kwargs


@pytest.mark.parametrize('limit', [None, 0, 4])
def test_application_passes_limit_and_binds_it_to_the_numerical_checkpoint(monkeypatch, limit):
    seen = []

    def prepare(*args, **kwargs):
        seen.append(kwargs)
        return {}, {} if limit is None else {'target_limit': limit}

    monkeypatch.setattr(application, 'prepare_recovery', prepare)
    prepared = application.prepare_track_recovery(
        {'tracks': {'observations': []}}, {'signed_context': {'scan': object()}},
        {'cavity_fit': {'status': 'complete'}}, identities=['scan'], recovery_target_limit=limit)
    assert seen[0] == dict(identities=['scan'], **({'target_limit': limit}
                                                if limit is not None else {}))
    monkeypatch.setattr(application, 'recover_tracks', lambda *a, **kw: {'selected': None})
    predictive = application.recover_predictive_checkpoint(prepared,
        run_stage=lambda n, operation: (True, operation()), discovery_allowed=lambda: True,
        clock=lambda: 0., inventory_seconds=0.)
    assert ('recovery_target_limit' in predictive) is (limit is not None)
    monkeypatch.setattr(application, 'replay_recovery',
                        lambda *a, **kw: seen.append(kw) or {'selected': None})
    application.recover_numerical_checkpoint(prepared, predictive,
        run_stage=lambda n, operation: (True, operation()), discovery_allowed=lambda: True,
        clock=lambda: 0., charge_reused=lambda _: None)
    assert ('completed_target_limit' in seen[-1]) is (limit is not None)
    if limit is not None:
        assert seen[-1]['completed_target_limit'] == limit


def test_incomplete_inventory_retains_legacy_checkpoint_failure_status():
    prepared = dict(status='cavity_incomplete', inventory=None)
    result = application.recover_predictive_checkpoint(prepared,
        run_stage=lambda n, operation: (True, operation()), discovery_allowed=lambda: True,
        clock=lambda: 0., inventory_seconds=0.)
    assert result['status'] == 'cavity_incomplete'
    assert 'recovery_target_limit' not in result
