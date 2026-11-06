"""Phase optimizations preserve complete states, layout and empty-bank errors."""

import algo07v3_prescalar_phase_oracle as oracle
import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import FrozenOrbitBank, phase_shifted_states
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles


@pytest.mark.parametrize('count', [0, 1, 19])
@pytest.mark.parametrize('frozen', [False, True])
@pytest.mark.parametrize('phase', [-30., -0., 0., 30., 'per_satellite'])
@pytest.mark.parametrize('layout', ['C', 'F', 'strided'])
def test_states_layout_and_orbital_projection_remain_exact(count, frozen, phase, layout):
    rng = np.random.default_rng(54917)
    knots = np.arange(-40., 341.)
    source = dict(time_s=knots,
                  position_km=rng.normal(size=(count, len(knots), 3))*7000,
                  velocity_km_s=rng.normal(size=(count, len(knots), 3))*7)
    if layout == 'F':
        source = {k: np.asfortranarray(v) for k, v in source.items()}
    elif layout == 'strided':
        source = {k: v[::2] if k == 'time_s' else v[:, ::2] for k, v in source.items()}
    before = {k: v.tobytes() for k, v in source.items()}
    actual_bank = FrozenOrbitBank(source) if frozen else source
    if phase == 'per_satellite':
        phase = np.linspace(-4, 4, count)
    times = np.r_[rng.uniform(0, 300, 17), 2., 2., -0., 0.]
    expected = oracle.phase_shifted_states(source, times, phase)
    actual = phase_shifted_states(actual_bank, times, phase)
    for a, b in zip(actual, expected, strict=True):
        assert (a.shape, a.strides, a.dtype, a.tobytes()) == (
            b.shape, b.strides, b.dtype, b.tobytes())
    for site in [(37., -122.), (90., 180.)]:
        observer, rotation = geodetic_to_ecef_km(*site, 0.), ecef_to_enu_matrix(*site)
        a = look_angles(*actual, observer, rotation)
        b = look_angles(*expected, observer, rotation)
        assert all(x.tobytes() == y.tobytes() for x, y in zip(a, b, strict=True))
    assert {k: v.tobytes() for k, v in source.items()} == before


@pytest.mark.parametrize('phase', [0., np.nan, np.inf])
def test_empty_catalogue_preserves_non_extrapolation_behavior(phase):
    source = dict(time_s=np.arange(3.), position_km=np.empty((0, 3, 3)),
                  velocity_km_s=np.empty((0, 3, 3)))
    expected = oracle.phase_shifted_states(source, [-999., 999.], phase)
    actual = phase_shifted_states(FrozenOrbitBank(source), [-999., 999.], phase)
    assert all(a.shape == b.shape and a.tobytes() == b.tobytes()
               for a, b in zip(actual, expected, strict=True))
