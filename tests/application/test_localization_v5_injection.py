from dataclasses import replace

from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from tests.application.test_localization_v3_engine import fixture


def test_initial_control_execution_port_reaches_only_initial_policy(monkeypatch):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    callback = object()
    engine.infer_prepared(prepared, region, catalogue, identities=['scan'],
        collect_history=object(), execution=replace(execution, initial_control=callback))
    for name, _, kwargs in calls:
        expected = callback if name == 'fit_initial_position' else None
        assert kwargs.get('initial_control') is expected


def test_application_forwards_initial_control_without_changing_budgets(monkeypatch):
    from types import SimpleNamespace

    callback, region = object(), object()
    scan = SimpleNamespace(radio_sigma_hz=150.)
    monkeypatch.setattr(application, '_context', lambda *args, **kwargs: scan)

    def search(actual, sigma, **kwargs):
        assert actual is scan and sigma == 150.
        assert kwargs == dict(on_branch=None, initial_control=callback)
        return {'complete': True}

    monkeypatch.setattr(application, 'initial_search', search)
    result = application.fit_initial_position(dict(status='inputs_prepared'), region,
                                              initial_control=callback)
    assert result['initial_fit'] == {'complete': True}
