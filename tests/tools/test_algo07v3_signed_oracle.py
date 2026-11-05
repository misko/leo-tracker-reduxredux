import sys
from types import ModuleType, SimpleNamespace

from algo07v3_signed_oracle import reference_signed_context


def _original_context(case, root=None, signed=True):
    root = forbidden(root)  # noqa: F821
    algo.bind_run_directory(root)  # noqa: F821
    old = read(root/case/'family.json')  # noqa: F821
    if old['status'] != 'accepted':
        raise ValueError('no incumbent')
    original = read(root/case/'result.json')  # noqa: F821
    scan = load(root, case)  # noqa: F821
    history = root/'history'
    forecast_path = root/'forecast'
    raw, forecast = read(history), read(forecast_path)  # noqa: F821
    algo.validate_history(raw, forecast, scan, sha(history))  # noqa: F821
    return dict(case=case, scan=scan, old=old, node=original['node'], signed=signed,
                binding=str(root), observations=read(root/case/'observations.json'))  # noqa: F821


def test_reference_context_retains_validation_without_old_storage(monkeypatch):
    module = ModuleType('fast_graph_engine')
    module.__file__ = __file__
    module.context = _original_context
    monkeypatch.setitem(sys.modules, 'fast_graph_engine', module)
    raw, forecast, scan, observations = {}, {}, object(), ['native']
    calls = []
    monkeypatch.setitem(_original_context.__globals__, 'algo',
        SimpleNamespace(validate_history=lambda *args: calls.append(args)))
    result = reference_signed_context(scan, {'node': 123}, {'status': 'accepted'},
        raw, forecast, observations, case='SCAN', history_sha256='bound')
    assert calls == [(raw, forecast, scan, 'bound')]
    assert result['node'] == 123 and result['observations'] is observations
    assert 'binding' not in result and result['signed']
