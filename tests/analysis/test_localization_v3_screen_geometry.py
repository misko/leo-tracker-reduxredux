import copy

import numpy as np
import pytest

from leo.analysis.localization_v3 import screen_geometry as owned
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from tests.analysis.test_orbit_phase_geometry import bank


@pytest.mark.parametrize('phase', [0., 3., -2., [1.2, -0.3]])
@pytest.mark.parametrize('times', [[], [0.0], [0.25, 2.5, 9.0], [2.5, 0.25, 2.5]])
def test_all_projection_bits_match_independent_original_calls(phase, times):
    sky = bank()
    sites = [(37.8, -122.5), (37.9, -122.6), (90., 180.), (-90., -180.)]
    actual = owned.phase_frequency_grids(sky, times, sites, phase_seconds=phase,
                                        altitude_m=127., rf_hz=12.1e9)
    for site, pair in zip(sites, actual, strict=True):
        expected = phase_frequency_grid(sky, times, *site, phase_seconds=phase,
                                        altitude_m=127., rf_hz=12.1e9)
        for a, b in zip(pair, expected, strict=True):
            assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def test_interpolates_once_and_returned_arms_do_not_alias(monkeypatch):
    original, calls = owned.phase_shifted_states, []

    def interpolate(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(owned, 'phase_shifted_states', interpolate)
    result = owned.phase_frequency_grids(bank(), [0., 1.], [(37., -122.)] * 2)
    assert len(calls) == 1
    before = [a.copy() for a in result[1]]
    result[0][0][:] = 123
    result[0][1][:] = 456
    for a, b in zip(result[1], before, strict=True):
        np.testing.assert_array_equal(a, b)


def test_mutated_bank_is_revalidated_and_recomputed_without_stale_cache():
    sky = bank()
    args = ([0., 1.], [(37., -122.), (37.1, -122.1)])
    before = owned.phase_frequency_grids(sky, *args)
    sky['position_km'] += 1
    after = owned.phase_frequency_grids(sky, *args)
    assert not np.array_equal(before[0][0], after[0][0])
    sky['position_km'][0, 0, 0] = np.nan
    with pytest.raises(ValueError, match='finite satellite states'):
        owned.phase_frequency_grids(sky, *args)


@pytest.mark.parametrize('kwargs', [
    dict(phase_seconds=30), dict(phase_seconds=[0, 1, 2]), dict(phase_seconds=np.nan),
    dict(altitude_m=np.inf), dict(rf_hz=0), dict(rf_hz=np.nan),
])
def test_original_validation_still_applies(kwargs):
    with pytest.raises(ValueError):
        owned.phase_frequency_grids(bank(), [0.], [(37., -122.)] * 2, **kwargs)


@pytest.mark.parametrize('sites', [[], [(91., 0.)], [(0., -181.)], [(np.nan, 0.)]])
def test_invalid_receiver_position_fails(sites):
    with pytest.raises(ValueError):
        owned.phase_frequency_grids(bank(), [0.], sites)


@pytest.mark.parametrize('fault', ['times', 'shape', 'velocity'])
def test_bank_validation_is_not_removed(fault):
    sky = copy.deepcopy(bank())
    if fault == 'times':
        sky['time_s'][1] = sky['time_s'][0]
    elif fault == 'shape':
        sky['velocity_km_s'] = sky['velocity_km_s'][:, :-1]
    else:
        sky['velocity_km_s'] = sky['velocity_km_s'].astype(float)
        sky['velocity_km_s'][0, 0, 0] = np.inf
    with pytest.raises(ValueError):
        owned.phase_frequency_grids(sky, [0.], [(37., -122.)] * 2)
