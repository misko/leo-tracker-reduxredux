import multiprocessing

import pytest
from probe_algo07v3_native_gradients import position, routing

from leo.operations.localization_v3_parallel import _ordered


def test_child_fits_never_use_parallel_gradient_route(monkeypatch):
    import probe_algo07v3_native_gradients as probe

    def original(*args, **kwargs):
        return dict(evaluations=1, route='serial')
    def candidate(*args, **kwargs):
        return dict(evaluations=1, route='parallel')
    monkeypatch.setattr(position, 'bounded_gauss_newton', original)
    monkeypatch.setattr(probe, 'transform', lambda: (candidate, '', ''))
    rows = []
    with routing(True, rows):
        assert position.bounded_gauss_newton(None, [0, 0], [], [])['route'] == 'parallel'
        values = _ordered(lambda _: position.bounded_gauss_newton(None, [0, 0], [], []), [0, 1])
        assert [v['route'] for v in values] == ['serial', 'serial']
    assert len(rows) == 1 and rows[0]['parallel']
    assert position.bounded_gauss_newton is original


def test_owner_with_existing_children_remains_serial(monkeypatch):
    import probe_algo07v3_native_gradients as probe

    monkeypatch.setattr(position, 'bounded_gauss_newton', lambda *a, **k: dict(evaluations=1))
    monkeypatch.setattr(probe, 'transform', lambda: (lambda *a, **k: pytest.fail('nested'), '', ''))
    monkeypatch.setattr(multiprocessing, 'active_children', lambda: [object()])
    rows = []
    with routing(True, rows):
        position.bounded_gauss_newton(None, [0, 0], [], [])
    assert not rows[0]['parallel']


def test_failure_restores_runtime_aliases_and_records_incomplete_fit(monkeypatch):
    from probe_algo07v3_native_gradients import engine

    old, timing = position.bounded_gauss_newton, engine._Timing.run
    rows = []
    def fail(x):
        raise ValueError('invalid residual')
    with pytest.raises(ValueError, match='invalid residual'), routing(True, rows):
        position.bounded_gauss_newton(fail, [0, 0], [-1, -1], [1, 1])
    assert position.bounded_gauss_newton is old and engine._Timing.run is timing
    assert len(rows) == 1 and not rows[0]['complete']
