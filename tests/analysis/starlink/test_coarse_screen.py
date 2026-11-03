"""The integrated adapter restores exact neighbors and uses complete fallback."""

import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink import coarse_screen
from leo.analysis.starlink._screen_selection import retain


@pytest.fixture
def setup(monkeypatch):
    truth = np.zeros((2, 100))
    truth[0, [20, 50, 80]] = [4., 3., 2.]
    approximate = truth + 1e-7
    calls = []

    def full(*args):
        calls.append('full')
        return tuple(truth.copy())

    def retain_original(residuals, rows, count, epoch_separation, cfo_separation, epochs):
        assert epochs == 100
        return retain(np.asarray(rows), residuals, count, epoch_separation, cfo_separation)

    acquisition = SimpleNamespace(_folded_anchor_score_grid=full,
                                  _retain_score_map_peaks=retain_original,
                                  _folded_anchor_score_grid_backend=lambda: 'avx2_fma')
    package = ModuleType('leo.analysis.starlink._screen_native')
    package._native_acquisition = object()
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setattr(coarse_screen, 'bound',
                        lambda *args: dict(eligible=True, absolute_error=1e-5))
    monkeypatch.setattr(coarse_screen, 'screen_grid', lambda *args: tuple(approximate))

    class Exact:
        native_calls = 0
        dense_fallback_calls = 0

        def __init__(self, *args):
            pass

        def __call__(self, columns):
            calls.append(tuple(columns))
            self.native_calls += 1
            return truth[:, columns]

    monkeypatch.setattr(coarse_screen, 'ExactColumns', Exact)
    return acquisition, truth, approximate, calls


def run(acquisition):
    diagnostics = []
    rows, selected = coarse_screen.acquire(acquisition, (None, None, 1., (0., 1.), (0,), 100),
                                           (-1., 1.), 3, 3, 2, observer=diagnostics.append)
    return np.asarray(rows), selected, diagnostics


def test_selected_scores_and_all_refinement_neighbors_exact(setup):
    acquisition, truth, approximate, calls = setup
    saved = approximate.copy()
    rows, selected, diagnostics = run(acquisition)
    assert 'full' not in calls
    assert selected == retain(truth, (-1., 1.), 3, 3, 2)
    for _, epoch, _ in selected:
        np.testing.assert_array_equal(rows[:, epoch-1:epoch+2].view(np.uint64),
                                      truth[:, epoch-1:epoch+2].view(np.uint64))
    np.testing.assert_array_equal(approximate, saved)
    assert diagnostics[0]['path'] == 'screened'


@pytest.mark.parametrize('reason', ['unsupported', 'broad', 'nonfinite', 'bound_violation'])
def test_complete_fallback_has_original_grid_and_selection(setup, monkeypatch, reason):
    acquisition, truth, approximate, calls = setup
    if reason == 'unsupported':
        monkeypatch.setattr(coarse_screen, 'bound', lambda *a: dict(eligible=False, reason='test'))
    elif reason == 'broad':
        monkeypatch.setattr(coarse_screen, 'bound',
                            lambda *a: dict(eligible=True, absolute_error=.1))
    elif reason == 'nonfinite':
        approximate[0, 0] = np.nan
    else:
        approximate[0, 20] = 10.
    rows, selected, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows.view(np.uint64), truth.view(np.uint64))
    assert selected == retain(truth, (-1., 1.), 3, 3, 2)
    assert calls.count('full') == 1
    assert diagnostics[0]['path'] == 'full'


def test_unavailable_backend_uses_complete_original_path(setup):
    acquisition, truth, _, calls = setup
    acquisition._folded_anchor_score_grid_backend = lambda: 'portable'
    rows, _, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows, truth)
    assert calls == ['full']
    assert diagnostics[0]['reason'] == 'unsupported backend'


def test_missing_screen_extension_uses_original_path(setup, monkeypatch):
    acquisition, truth, _, calls = setup
    monkeypatch.setitem(sys.modules, 'leo.analysis.starlink._screen_native', None)
    rows, _, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows, truth)
    assert calls == ['full']
    assert diagnostics[0]['reason'] == 'screen extension unavailable'


def test_malformed_screen_shape_uses_original_path(setup, monkeypatch):
    acquisition, truth, _, calls = setup
    monkeypatch.setattr(coarse_screen, 'screen_grid', lambda *args: np.zeros((1, 100)))
    rows, _, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows, truth)
    assert calls == ['full']
    assert diagnostics[0]['reason'] == 'invalid screen scores'


def test_dense_oracle_full_result_is_cached_and_returned(setup, monkeypatch):
    acquisition, truth, _, calls = setup

    class Dense:
        native_calls = 0
        dense_fallback_calls = 0

        def __init__(self, acquisition, full, args):
            self.full = full

        def __call__(self, columns):
            self.dense_fallback_calls += 1
            return np.asarray(self.full())[:, columns]

    monkeypatch.setattr(coarse_screen, 'ExactColumns', Dense)
    rows, selected, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows, truth)
    assert selected == retain(truth, (-1., 1.), 3, 3, 2)
    assert calls == ['full']
    assert diagnostics[0]['dense_calls'] > 0


def test_integer_screen_rejects_fractional_iq_before_native_call(setup, monkeypatch):
    from leo.analysis.starlink import _screen_integer

    acquisition, truth, _, calls = setup
    package = sys.modules['leo.analysis.starlink._screen_native']
    package.SCREEN_KIND = 'integer_vnni'
    package._native_acquisition = SimpleNamespace(
        folded_anchor_score_grid_backend=lambda: 'avx2_fma')
    monkeypatch.setattr(_screen_integer, 'floating_bound',
                        lambda *a: dict(eligible=True, max_sample_component=1.))
    diagnostics = []
    args = (np.full(100, .5+1j), np.ones(20, complex), 1., (0., 1.), (0,), 100)
    rows, _ = coarse_screen.acquire(acquisition, args, (-1., 1.), 3, 3, 2,
                                   observer=diagnostics.append)
    np.testing.assert_array_equal(rows, truth)
    assert calls == ['full']
    assert diagnostics[0]['reason'] == 'integer screen requires signed integer IQ'


def test_integer_screen_without_vnni_falls_back(setup):
    acquisition, truth, _, calls = setup
    package = sys.modules['leo.analysis.starlink._screen_native']
    package.SCREEN_KIND = 'integer_vnni'
    package._native_acquisition = SimpleNamespace(
        folded_anchor_score_grid_backend=lambda: 'portable')
    rows, _, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows, truth)
    assert calls == ['full']
    assert diagnostics[0]['reason'] == 'integer screen hardware unavailable'


def test_unknown_screen_kind_falls_back(setup):
    acquisition, truth, _, calls = setup
    sys.modules['leo.analysis.starlink._screen_native'].SCREEN_KIND = 'unsupported'
    rows, _, diagnostics = run(acquisition)
    np.testing.assert_array_equal(rows, truth)
    assert calls == ['full']
    assert diagnostics[0]['reason'] == 'unknown screen kind'
