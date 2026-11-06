from collections import defaultdict

import pytest
from profile_algo07v3_screen_parts import PARTS, observe, residual_screen


def test_wrapper_keeps_results_arguments_and_restores_on_failure(monkeypatch):
    value, called = object(), []
    def sample(*args, **kwargs):
        called.append((args, kwargs))
        return value
    monkeypatch.setattr(residual_screen, 'profile_rate', sample)
    originals = [getattr(residual_screen, name) for name in PARTS]
    rows = defaultdict(lambda: dict(seconds=0., calls=0))
    with pytest.raises(RuntimeError), observe(rows):
        assert residual_screen.profile_rate(1, option=2) is value
        raise RuntimeError('failure')
    assert called == [((1,), {'option': 2})]
    assert rows['profile_rate']['calls'] == 1
    assert rows['profile_rate']['seconds'] >= 0
    assert [getattr(residual_screen, name) for name in PARTS] == originals


def test_failed_operation_stays_a_failure_and_is_counted(monkeypatch):
    def fail():
        raise ValueError('incomplete')
    monkeypatch.setattr(residual_screen, 'components', fail)
    rows = defaultdict(lambda: dict(seconds=0., calls=0))
    with observe(rows), pytest.raises(ValueError, match='incomplete'):
        residual_screen.components()
    assert rows['components']['calls'] == 1
