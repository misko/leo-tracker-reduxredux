from dataclasses import fields

import numpy as np
import pytest

from leo.analysis.localization_v3.geometry import ScanGeometry
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry


def bank():
    times = np.arange(-10., 21.)
    p = np.stack([7000 + 0*times, 7*times, 200 + 0*times], axis=1)
    v = np.broadcast_to([0., 7., 0.], p.shape).copy()
    return dict(time_s=times, position_km=np.stack([p, p + [100, 0, 100]]),
                velocity_km_s=np.stack([v, v]))


def exact(a, b):
    assert type(a) is type(b)
    for f in fields(a):
        x, y = getattr(a, f.name), getattr(b, f.name)
        if isinstance(x, np.ndarray):
            assert x.dtype == y.dtype and x.shape == y.shape
            assert x.tobytes() == y.tobytes()
        else:
            exact(x, y)


@pytest.mark.parametrize('phases', [0., np.array([.2, -.1]), np.array([.2, -.1], np.float32)])
def test_cold_and_cached_queries_are_bitwise_equal_to_original(phases):
    source = bank()
    times = np.array([.4, 4.4, 10.4])
    context = ScanGeometry(source)
    expected = prepare_phase_geometry(source, times, phases)
    first = context.prepare(times, phases)
    exact(expected, first)
    assert context.prepare(times.copy(), np.asarray(phases).copy()) is first
    assert (context.hits, context.misses) == (1, 1)


def test_bank_and_returned_arrays_cannot_be_mutated_into_a_stale_hit():
    source = bank()
    context = ScanGeometry(source)
    first = context.prepare([0., 1.])
    source['position_km'][:] = 0
    assert context.prepare([0., 1.]) is first
    for array in [first.geometry.position_km, first.position_derivative]:
        with pytest.raises(ValueError):
            array.setflags(write=True)
        with pytest.raises(ValueError):
            array.flat[0] = 0


def test_changed_times_phases_and_derivative_step_recompute():
    context = ScanGeometry(bank())
    times = np.array([0., 1.])
    phases = np.array([0., 0.])
    first = context.prepare(times, phases)
    times[0] = .1
    assert context.prepare(times, phases) is not first
    phases[0] = .1
    assert context.prepare(times, phases) is not first
    context.prepare(times, phases, derivative_step_s=.1)
    assert (context.hits, context.misses) == (0, 4)


def test_cache_budget_evicts_and_zero_budget_bypasses():
    source = bank()
    unlimited = ScanGeometry(source)
    unlimited.prepare([0., 1.])
    context = ScanGeometry(source, maximum_cache_bytes=unlimited.cached_bytes)
    first = context.prepare([0., 1.])
    context.prepare([2., 3.])
    replay = context.prepare([0., 1.])
    assert replay is not first
    exact(replay, first)
    assert context.cached_bytes <= context.maximum_cache_bytes
    uncached = ScanGeometry(source, maximum_cache_bytes=0)
    exact(uncached.prepare([0., 1.]), uncached.prepare([0., 1.]))
    assert uncached.cached_bytes == 0 and uncached.hits == 0


def test_query_domain_errors_are_never_cached():
    context = ScanGeometry(bank())
    for _ in range(2):
        with pytest.raises(ValueError, match='extrapolates'):
            context.prepare([100.])
    assert context.cached_bytes == 0
    with pytest.raises(ValueError, match='finite'):
        context.prepare([float('nan')])
    with pytest.raises(ValueError, match='scalar'):
        context.prepare([0.], derivative_step_s=[.1])


def test_invalid_bank_rejected_at_construction():
    source = bank()
    source['position_km'][0, 0, 0] = float('nan')
    with pytest.raises(ValueError, match='finite satellite'):
        ScanGeometry(source)
