"""Endpoint reuse retains all state bits and unusual empty-bank behavior."""

import numpy as np
import pytest
from probe_algo07v3_endpoint_reuse import operations, projection

from leo.analysis.localization_v3 import screen_geometry
from leo.analysis.research.orbit_phase_geometry import FrozenOrbitBank


@pytest.mark.parametrize('count', [0, 1, 19])
@pytest.mark.parametrize('layout', ['C', 'F', 'strided'])
@pytest.mark.parametrize('phase', [-30., -0., 0., 30., 'per_satellite'])
@pytest.mark.parametrize('frozen', [False, True])
def test_all_state_bits_equal(count, layout, phase, frozen):
    rng = np.random.default_rng(514377)
    knots = np.arange(-40., 341.)
    bank = dict(time_s=knots,
                position_km=rng.normal(size=(count, len(knots), 3))*7000,
                velocity_km_s=rng.normal(size=(count, len(knots), 3))*7)
    if layout == 'F':
        bank = {k: np.asfortranarray(v) for k, v in bank.items()}
    elif layout == 'strided':
        bank = {k: v[::2] if k == 'time_s' else v[:, ::2] for k, v in bank.items()}
    if frozen:
        bank = FrozenOrbitBank(bank)
    before = {k: bank[k].tobytes() for k in ('time_s', 'position_km', 'velocity_km_s')}
    if phase == 'per_satellite':
        phase = np.linspace(-5., 5., count)
    functions, _ = operations()
    for times in (np.array([]), rng.uniform(0, 300, 37), np.array([2., 2., 1., -0., 0.])):
        expected = functions['baseline'](bank, times, phase)
        actual = functions['candidate'](bank, times, phase)
        for a, b in zip(actual, expected, strict=True):
            assert a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()
        assert all(bank[k].tobytes() == value for k, value in before.items())


def test_empty_catalogue_keeps_its_original_empty_phase_semantics():
    bank = dict(time_s=np.arange(3.), position_km=np.empty((0, 3, 3)),
                velocity_km_s=np.empty((0, 3, 3)))
    functions, _ = operations()
    for phase in (0., np.nan, np.inf):
        expected = functions['baseline'](bank, [-999., 999.], phase)
        actual = functions['candidate'](bank, [-999., 999.], phase)
        assert all(a.shape == b.shape and a.tobytes() == b.tobytes()
                   for a, b in zip(actual, expected, strict=True))


def test_projection_substitution_restores_after_failure():
    old = screen_geometry.phase_shifted_states
    with pytest.raises(RuntimeError), projection(lambda *args: None):
        raise RuntimeError('deliberate')
    assert screen_geometry.phase_shifted_states is old


@pytest.mark.parametrize('times,phase', [([np.nan], 0), ([[1]], 0), ([20], 1),
                                      ([0], np.inf), ([0], [0, 0, 0])])
def test_errors_keep_original_type_and_message(times, phase):
    from tests.analysis.test_orbit_phase_geometry import bank
    functions, _ = operations()
    errors = []
    for function in functions.values():
        with pytest.raises(ValueError) as error:
            function(bank(), times, phase)
        errors.append((type(error.value), str(error.value)))
    assert errors[0] == errors[1]
