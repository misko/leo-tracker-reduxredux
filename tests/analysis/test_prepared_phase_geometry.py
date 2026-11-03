"""Prepared states preserve the exact location-dependent frequency calculation."""

import numpy as np
import pytest

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.prepared_phase_geometry import prepare_phase_geometry


def inputs():
    rng = np.random.default_rng(20261103)
    knots = np.arange(-40., 361., 5.)
    p = rng.normal(size=(2, len(knots), 3)) * 20 + [-2400., -4700., 4300.]
    v = rng.normal(size=p.shape)
    bank = dict(time_s=knots, position_km=p, velocity_km_s=v)
    modes = dict(time_s=knots, position_km=rng.normal(size=(6, len(knots), 3))*.02,
                 velocity_km_s=rng.normal(size=(6, len(knots), 3))*.001)
    return (bank, modes, np.array([3., 3., 70., 180., 300.]),
            np.array([1, 0, 0, 1, 0]), np.array([2.1, -3.7]))


@pytest.mark.parametrize('latitude,longitude,height', [
    (37., -122., 0.), (0., 45., 275.), (-60., 179., 800.)])
def test_exact_frequency_elevation_and_modes_at_multiple_sites(latitude, longitude, height):
    bank, modes, times, labels, phases = inputs()
    prepared = prepare_phase_geometry(bank, modes, times, labels, phases)
    f, e = paired_phase_frequency(
        bank, times, labels, phases, latitude, longitude, altitude_m=height)
    u = paired_frequency_modes(
        bank, modes, times, labels, phases, latitude, longitude, altitude_m=height)
    actuals = prepared.evaluate(latitude, longitude, altitude_m=height)
    for expected, actual in zip((f, e, u), actuals, strict=True):
        np.testing.assert_array_equal(actual, expected)


def test_prepared_states_are_immutable_snapshots_and_new_grid_has_new_states():
    bank, modes, times, labels, phases = inputs()
    prepared = prepare_phase_geometry(bank, modes, times, labels, phases)
    before = prepared.evaluate(37., -122.)
    bank['position_km'] += 3
    modes['velocity_km_s'] += .1
    phases += 1
    for expected, actual in zip(before, prepared.evaluate(37., -122.), strict=True):
        np.testing.assert_array_equal(actual, expected)
    newer = prepare_phase_geometry(bank, modes, times, labels, phases)
    assert not np.array_equal(before[0], newer.evaluate(37., -122.)[0])
    with pytest.raises(ValueError, match='read-only'):
        prepared.position_km[0, 0] = 0


def test_preparation_refuses_extrapolation_and_invalid_mode_count():
    bank, modes, times, labels, phases = inputs()
    with pytest.raises(ValueError, match='extrapolat'):
        prepare_phase_geometry(bank, modes, times+1000, labels, phases)
    modes['position_km'] = modes['position_km'][:5]
    with pytest.raises(ValueError, match='mode count'):
        prepare_phase_geometry(bank, modes, times, labels, phases)
