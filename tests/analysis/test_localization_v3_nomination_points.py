"""Owned nomination geometry keeps all used values and full-time validation."""

import numpy as np
import pytest

from leo.analysis.localization_v3 import residual_screen as screen
from tests.analysis.test_orbit_phase_geometry import bank


def test_fold_columns_are_the_original_selected_observations():
    folds = [('full', np.ones(100, bool), None),
             ('random', np.random.default_rng(441).uniform(size=100) > .4, None)]
    query, columns = screen._nomination_indices(folds)
    assert len(query) <= 32
    for name, mask, _ in folds:
        ix = np.flatnonzero(mask)
        expected = ix[np.unique(np.linspace(0, len(ix) - 1, min(16, len(ix))).astype(int))]
        np.testing.assert_array_equal(query[columns[name]], expected)


@pytest.mark.parametrize('times', [[0., .25, 1., 2., 5., 8.], [2., .25, 2., 8., 0., 5.]])
@pytest.mark.parametrize('phase', [-1., 0., 1.])
def test_projection_preserves_all_selected_bits(times, phase):
    sky, positions = bank(), [(37., -122.), (37.5, -122.5)]
    t, query = np.asarray(times) + 2, np.array([0, 2, 4])
    actual = screen._nomination_grids(sky, t, query, positions, phase_seconds=phase)
    expected = screen.phase_frequency_grids(sky, t, positions, phase_seconds=phase)
    for a, b in zip(actual, expected, strict=True):
        for reduced, full in zip(a, b, strict=True):
            assert reduced.tobytes() == full[:, query].tobytes()


@pytest.mark.parametrize('hidden', [np.nan, np.inf, 100.])
def test_unselected_bad_times_retain_original_validation(hidden):
    with pytest.raises(ValueError):
        screen._nomination_grids(bank(), [0., hidden, 2.], [0, 2],
                                 [(37., -122.)], phase_seconds=0.)


def test_nomination_requests_only_selected_points(monkeypatch):
    calls, result = [], object()
    def project(_bank, t, _positions, **kwargs):
        calls.append(np.asarray(t).copy())
        return result
    monkeypatch.setattr(screen, 'phase_frequency_grids', project)
    t = np.arange(8.)
    assert screen._nomination_grids(bank(), t, [0, 3, 7], [(37., -122.)],
                                   phase_seconds=0.) is result
    np.testing.assert_array_equal(calls[0], [0., 3., 7.])
