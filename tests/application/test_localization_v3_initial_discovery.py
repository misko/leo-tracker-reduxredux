from dataclasses import replace
from types import SimpleNamespace

import pytest

from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from leo.contracts.localization_v5 import initial_discovery_policy
from tests.application.test_localization_v3_engine import fixture


@pytest.mark.parametrize('seed,ranking', [('legacy', 'legacy'),
    ('anchor-round-robin-v1', 'legacy'), ('legacy', 'warm-center-v1'),
    ('anchor-round-robin-v1', 'warm-center-v1')])
def test_engine_scopes_initial_policy_to_initial_fit(monkeypatch, seed, ranking):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    policy = initial_discovery_policy(seed, ranking)
    engine.infer_prepared(prepared, region, catalogue, identities=['scan'],
        collect_history=object(), execution=replace(execution, initial_discovery_policy=policy))
    for name, _, kwargs in calls:
        if name == 'fit_initial_position':
            assert kwargs['initial_discovery_policy'] == policy
        else:
            assert 'initial_discovery_policy' not in kwargs


@pytest.mark.parametrize('policy', [None, initial_discovery_policy(),
    initial_discovery_policy('anchor-round-robin-v1', 'warm-center-v1')])
def test_application_forwards_explicit_policy_without_changing_fit_budgets(monkeypatch, policy):
    scan = SimpleNamespace(radio_sigma_hz=150.)
    monkeypatch.setattr(application, '_context', lambda *args, **kwargs: scan)

    def search(actual, sigma, **kwargs):
        assert actual is scan and sigma == 150.
        expected = dict(on_branch=None)
        if policy is not None:
            expected.update(seed_policy=policy['seed_policy'],
                            ranking_policy=policy['ranking_policy'])
        assert kwargs == expected
        return {'complete': True}

    monkeypatch.setattr(application, 'initial_search', search)
    result = application.fit_initial_position(dict(status='inputs_prepared'), object(),
                                              initial_discovery_policy=policy)
    assert result['initial_fit'] == {'complete': True}
