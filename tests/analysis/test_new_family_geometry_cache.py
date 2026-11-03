"""An endpoint audit must not inherit the integrated family's cached geometry."""

import numpy as np
import predictive_new_family as module
import pytest
from audit_two_predictive_families import at_phases

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def family():
    rng = np.random.default_rng(20261103)
    f = object.__new__(module.NewFamily)
    knots = np.arange(-40., 361., 5.)
    f.times = np.array([3., 70., 180., 300.])
    f.phases = np.array([-2., 0., 2.])
    f.grid_times = np.tile(f.times, len(f.phases))
    f.grid_labels = np.repeat(np.arange(len(f.phases)), len(f.times))
    p = rng.normal(size=(1, len(knots), 3))*20+[-2400., -4700., 4300.]
    v = rng.normal(size=p.shape)
    f.bank = dict(time_s=knots, position_km=np.tile(p, (3, 1, 1)),
                  velocity_km_s=np.tile(v, (3, 1, 1)))
    f.modes = dict(time_s=knots,
                   position_km=rng.normal(size=(9, len(knots), 3))*.02,
                   velocity_km_s=rng.normal(size=(9, len(knots), 3))*.001)
    return f


def assert_oracle(f):
    freq, elev = paired_phase_frequency(
        f.bank, f.grid_times, f.grid_labels, f.phases, 37., -122.)
    modes = paired_frequency_modes(
        f.bank, f.modes, f.grid_times, f.grid_labels, f.phases, 37., -122.)
    for actual, expected in zip(f.geometry(37., -122.), (freq, elev, modes), strict=True):
        np.testing.assert_array_equal(actual, expected)


def test_actual_endpoint_audit_copy_rebuilds_geometry_and_preserves_parent():
    f = family()
    assert_oracle(f)
    original = f._prepared_geometry_cache
    endpoint, = at_phases([f], [1.25])
    assert_oracle(endpoint)
    assert endpoint.geometry(37., -122.)[0].shape == f.times.shape
    assert endpoint._prepared_geometry_cache is not original
    assert_oracle(f)
    assert f._prepared_geometry_cache is original


@pytest.mark.parametrize('change', ['phase', 'times', 'labels', 'bank', 'modes'])
def test_same_shape_edits_invalidate_cache(change):
    f = family()
    assert_oracle(f)
    original = f._prepared_geometry_cache
    if change == 'phase':
        f.phases[0] += .5
    elif change == 'times':
        f.grid_times[0] += 1
    elif change == 'labels':
        f.grid_labels[0] = 1
    else:
        bank = getattr(f, change)
        bank['position_km'] = bank['position_km']+.1
    assert_oracle(f)
    assert f._prepared_geometry_cache is not original


def test_unchanged_geometry_prepares_once_across_locations(monkeypatch):
    f = family()
    assert_oracle(f)
    original = f._prepared_geometry_cache

    def unexpected(*args):
        raise AssertionError('Unchanged orbit/grid should reuse prepared geometry')

    monkeypatch.setattr(module, 'prepare_phase_geometry', unexpected)
    f.geometry(35., -120.)
    assert_oracle(f)
    assert f._prepared_geometry_cache is original
