"""Repeated predictive requests cannot mutate or contaminate curved calibration."""

from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.position_calculation_cache import copying_position_cache


def test_exact_keys_bounded_eviction_and_independent_nested_outputs():
    calls = []

    def calculate(x):
        calls.append(x.copy())
        return dict(coefficient=x, objective=float(x.sum()), nested=[dict(values=x)])

    cached = copying_position_cache(calculate, maxsize=2)
    x = np.array([1., 2.])
    first = cached(x)
    first['objective'] += 100
    first['coefficient'][:] = -999
    first['nested'].append('changed')
    second = cached(x.copy())
    assert second['objective'] == 3 and len(second['nested']) == 1 and len(calls) == 1
    np.testing.assert_array_equal(second['coefficient'], x)
    assert second['nested'][0]['values'] is second['coefficient']
    changed = x.copy()
    changed[0] = np.nextafter(changed[0], np.inf)
    cached(changed)
    cached(x.astype(np.float32))
    assert len(calls) == 3  # No rounded coordinates or dtype conflation.
    cached(x)
    assert len(calls) == 4 and cached.cache_info().currsize == 2
    cached.cache_clear()
    cached(x)
    assert len(calls) == 5


def test_errors_are_not_cached_and_separate_models_do_not_share_results():
    attempts = 0

    def calculate(x):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError('failed model')
        return dict(objective=3.)

    first = copying_position_cache(calculate)
    with pytest.raises(ValueError, match='failed model'):
        first([0., 0.])
    assert first([0., 0.]) == {'objective': 3.} and attempts == 2
    second = copying_position_cache(lambda x: dict(objective=9.))
    assert second([0., 0.]) == {'objective': 9.}


@pytest.mark.parametrize('kind', ['linear', 'event'])
def test_predictive_attachment_reuses_curved_fit_without_adding_prediction_twice(monkeypatch, kind):
    import ds23_frequency_events as event
    import ds23_predictive_linear as linear

    module = linear if kind == 'linear' else event
    calls = []

    def calculate(x):
        calls.append(x.copy())
        return dict(coefficient=np.array([.5]), coefficient_prior_precision=np.ones(1),
                    features=np.ones((2, 1)), noise_precision=np.ones(1),
                    negative_twice_elbo=10., normalization_constant=2., residual=np.ones(2))

    p = SimpleNamespace(calculate=calculate, keep=np.ones(2, bool),
                        noise_groups=np.zeros(2, int), point_noise=np.ones(2), events=[],
                        labels=[0], scan=SimpleNamespace(tracks=[dict(
                            times=np.array([0., 1.]), receiver=1, channel=1)]))
    view = SimpleNamespace(q=np.ones(2), flat_times=np.array([0., 1.]),
                           flat_labels=np.zeros(2, int))
    entries = [dict(track_index=0)]
    monkeypatch.setattr(module, 'linear_geometry', lambda *a: (
        view, np.array([4., 5.]), np.ones(2), np.zeros(2, int), [slice(0, 2)]))
    monkeypatch.setattr(module, 'geometry_features', lambda *a: dict(
        intercept=np.ones(2), features=np.ones((2, 1)), elevation=np.ones(2)))
    attach = linear.attach_predictive_linear if kind == 'linear' else event.attach_event_predictive
    attach(p, entries, np.ones(1))
    a, b = p.calculate(np.zeros(2)), p.calculate(np.zeros(2))
    curved = p.curved_calculate(np.zeros(2))
    assert len(calls) == 1
    assert a['negative_twice_elbo'] == b['negative_twice_elbo']
    assert a['negative_twice_elbo'] > curved['negative_twice_elbo'] == 10.
    assert curved['normalization_constant'] == 2. and 'linear_predictive_objective' not in curved
    a['coefficient'][:] = 200
    np.testing.assert_array_equal(p.curved_calculate(np.zeros(2))['coefficient'], [.5])
    p.calculate(np.array([0., .1]))
    assert len(calls) == 2
