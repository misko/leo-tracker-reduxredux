import numpy as np
import pytest
from probe_algo07v3_nomination_points import candidate, nomination_grids, nomination_indices

from leo.analysis.localization_v3 import residual_screen
from tests.analysis.test_orbit_phase_geometry import bank


def test_indices_preserve_each_fold_selection_and_order():
    folds = [('full', np.ones(100, bool), None),
             ('random', np.random.default_rng(441).uniform(size=100) > .4, None)]
    query, columns = nomination_indices(folds)
    assert len(query) <= 32
    for name, mask, _ in folds:
        ix = np.flatnonzero(mask)
        expected = ix[np.unique(np.linspace(0, len(ix) - 1, min(16, len(ix))).astype(int))]
        np.testing.assert_array_equal(query[columns[name]], expected)


@pytest.mark.parametrize('times', [[0., .25, 1., 2., 5., 8.], [2., .25, 2., 8., 0., 5.]])
@pytest.mark.parametrize('phase', [-1., 0., 1.])
def test_selected_projection_values_are_exact(times, phase):
    sky, positions = bank(), [(37., -122.), (37.5, -122.5)]
    query = np.array([0, 2, 4])
    # Keep every full time in domain for all phases.
    t = np.asarray(times) + 2
    a = nomination_grids(sky, t, query, positions, phase_seconds=phase)
    b = residual_screen.phase_frequency_grids(sky, t, positions, phase_seconds=phase)
    for actual, expected in zip(a, b, strict=True):
        for x, y in zip(actual, expected, strict=True):
            assert x.tobytes() == y[:, query].tobytes()


@pytest.mark.parametrize('hidden', [np.nan, np.inf, 100.])
def test_unselected_invalid_times_still_raise(hidden):
    with pytest.raises(ValueError):
        nomination_grids(bank(), [0., hidden, 2.], [0, 2], [(37., -122.)], phase_seconds=0.)


def test_source_transformation_is_bounded():
    function, original, changed = candidate()
    assert callable(function)
    assert changed.count('_nomination_grids') == 1
    assert 'paired_phase_frequency(' in original and 'paired_phase_frequency(' in changed
