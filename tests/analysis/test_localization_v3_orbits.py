from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import orbits
from leo.sky.propagation import ElementSetCatalogue


def catalogue():
    return ElementSetCatalogue(('A', 'B', 'C'), (1, 2, 3), (object(), object(), object()))


def test_screening_preserves_catalogue_indices_and_original_grid(monkeypatch):
    cat = catalogue()
    calls = []

    def states(selected, origin, times):
        calls.append((selected, origin, times.copy()))
        values = np.ones((len(selected), len(times), 3))
        return values, values.copy(), np.array([True, False, True]) \
            if len(selected) == 3 else np.ones(len(selected), bool)

    monkeypatch.setattr(orbits, 'ecef_states', states)
    monkeypatch.setattr(orbits, 'look_angles', lambda *args: (
        None, np.array([[-12.], [40.], [-12.01]]), None, None))
    result = orbits.regional_bank(cat, 123, 301.25,
                                  screen_latitude_deg=0., screen_longitude_deg=0.)
    assert result['source_indices'].tolist() == [0]
    assert result['catalogue'].satellite_numbers == (1,)
    np.testing.assert_array_equal(calls[0][2], np.arange(0., 306.25, 5.))
    np.testing.assert_array_equal(result['bank']['time_s'], np.arange(-17., 320.))
    assert result['bank']['phase_sigma_s'].tolist() == [1.]


def test_time_rounding_and_rotation_receive_the_original_sampling_instants(monkeypatch):
    captured = []

    def propagate(cat, grid):
        captured.append(grid.utc_ns)
        a = np.zeros((3, 3, 3))
        return SimpleNamespace(position_teme_km=a, velocity_teme_km_s=a,
                               usable=np.ones(3, bool))

    monkeypatch.setattr(orbits, 'propagate_grid', propagate)
    orbits.ecef_states(catalogue(), 1_700_000_000_000_000_000,
                       np.array([0., .1234567894, .1234567906]))
    assert captured == [(1_700_000_000_000_000_000, 1_700_000_000_123_456_789,
                         1_700_000_000_123_456_791)]


def test_no_visible_candidates_is_explicit(monkeypatch):
    monkeypatch.setattr(orbits, 'ecef_states', lambda *args: (
        np.zeros((3, 61, 3)), np.zeros((3, 61, 3)), np.zeros(3, bool)))
    with pytest.raises(ValueError, match='no regional'):
        orbits.regional_bank(catalogue(), 0, 100.,
                             screen_latitude_deg=0., screen_longitude_deg=0.)


@pytest.mark.parametrize('duration', [-1, float('nan'), float('inf')])
def test_invalid_duration_cannot_create_unbounded_bank(duration):
    with pytest.raises(ValueError, match='duration'):
        orbits.regional_bank(catalogue(), 0, duration,
                             screen_latitude_deg=0., screen_longitude_deg=0.)
