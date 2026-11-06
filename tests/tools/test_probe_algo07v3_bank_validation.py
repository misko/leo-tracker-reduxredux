"""The external snapshot owns immutable data and retains phase/input errors."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from probe_algo07v3_bank_validation import KEYS, FrozenOrbitBank, candidate, replace_once

from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from tests.analysis.test_orbit_phase_geometry import bank


@pytest.mark.parametrize('phase', [-1., 0., 1., [1., -1.]])
@pytest.mark.parametrize('times', [[], [2., .25, 2., 8., 0., 5.]])
def test_original_states_exact_and_inputs_unchanged(phase, times):
    original, frozen = bank(), FrozenOrbitBank(bank())
    before = {key: original[key].tobytes() for key in KEYS}
    _, operation, _, _ = candidate()
    expected = phase_shifted_states(original, times, phase)
    for source in (original, frozen):
        actual = operation(source, times, phase)
        for a, b in zip(actual, expected, strict=True):
            assert a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()
    for key in KEYS:
        assert original[key].tobytes() == before[key]
        assert np.asarray(original[key], float).tobytes() == frozen[key].tobytes()


def test_snapshot_is_owned_and_buffers_cannot_be_made_writeable():
    original = bank()
    frozen = FrozenOrbitBank(original)
    for key in KEYS:
        expected = frozen[key].tobytes()
        original[key].flat[0] += 10
        assert frozen[key].tobytes() == expected
        with pytest.raises(ValueError):
            frozen[key].setflags(write=True)
        with pytest.raises(ValueError):
            frozen[key].flat[0] = 0
    with pytest.raises(FrozenInstanceError):
        frozen._entries = ()
    with pytest.raises(KeyError):
        frozen['unknown']


def test_returned_array_metadata_cannot_modify_the_snapshot():
    frozen = FrozenOrbitBank(bank())
    for key in KEYS:
        expected = frozen[key].shape
        returned = frozen[key]
        returned.shape = (returned.size,)
        assert frozen[key].shape == expected


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('bad', [np.nan, np.inf])
def test_constructor_rejects_bad_bank(key, bad):
    original = bank()
    original[key] = np.asarray(original[key], float)
    original[key].flat[0] = bad
    with pytest.raises(ValueError):
        FrozenOrbitBank(original)


def test_constructor_rejects_unordered_knots_and_state_shapes():
    original = bank()
    original['time_s'][1] = original['time_s'][0]
    with pytest.raises(ValueError):
        FrozenOrbitBank(original)
    original = bank()
    original['velocity_km_s'] = original['velocity_km_s'][:, :-1]
    with pytest.raises(ValueError):
        FrozenOrbitBank(original)


@pytest.mark.parametrize('times,phase', [([np.nan], 0), ([[1]], 0), ([20], 1),
                                      ([0], np.inf), ([0], [0, 0, 0])])
def test_snapshot_does_not_bypass_per_call_validation(times, phase):
    _, operation, _, _ = candidate()
    with pytest.raises(ValueError):
        operation(FrozenOrbitBank(bank()), times, phase)


def test_general_mutable_callers_still_validate_every_call():
    original = bank()
    _, operation, _, _ = candidate()
    operation(original, [0], 0)
    original['position_km'][0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        operation(original, [0], 0)


def test_extraction_requires_one_exact_boundary():
    for text in ('', 'xx'):
        with pytest.raises(ValueError):
            replace_once(text, 'x', 'y')


@pytest.mark.parametrize('count', [0, 1, 19])
@pytest.mark.parametrize('layout', ['C', 'F', 'strided'])
def test_realistic_float_states_keep_every_bit_across_layouts(count, layout):
    rng = np.random.default_rng(48312)
    knots = np.arange(-40., 341.)
    source = dict(time_s=knots,
                  position_km=rng.normal(size=(count, len(knots), 3))*7000,
                  velocity_km_s=rng.normal(size=(count, len(knots), 3))*7)
    if layout == 'F':
        source = {k: np.asfortranarray(v) for k, v in source.items()}
    elif layout == 'strided':
        source = {k: v[::2] if k == 'time_s' else v[:, ::2] for k, v in source.items()}
    _, operation, _, _ = candidate()
    frozen = FrozenOrbitBank(source)
    times = rng.uniform(0, 300, 31)
    for phase in (-30, -15, 0, 15, 30):
        expected = phase_shifted_states(source, times, phase)
        actual = operation(frozen, times, phase)
        assert all(a.tobytes() == b.tobytes() for a, b in zip(actual, expected, strict=True))
