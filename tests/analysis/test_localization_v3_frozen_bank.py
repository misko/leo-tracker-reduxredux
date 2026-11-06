"""An internal immutable bank validates once; ordinary mutable banks do not."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from leo.analysis.research import orbit_phase_geometry as owned
from tests.analysis.test_orbit_phase_geometry import bank


def test_snapshot_owns_immutable_values_and_metadata():
    original = bank()
    frozen = owned.FrozenOrbitBank(original)
    for key in original:
        expected = np.asarray(original[key], float)
        shape, content = expected.shape, expected.tobytes()
        original[key].flat[0] += 5
        returned = frozen[key]
        assert returned.tobytes() == content
        with pytest.raises(ValueError):
            returned.setflags(write=True)
        with pytest.raises(ValueError):
            returned.flat[0] = 0
        with pytest.warns(DeprecationWarning):
            returned.shape = (returned.size,)
        assert frozen[key].shape == shape and frozen[key].tobytes() == content
    with pytest.raises(FrozenInstanceError):
        frozen._entries = ()


def test_validation_occurs_once_for_snapshot_and_each_mutable_call(monkeypatch):
    validate, calls = owned.interpolate_states, []
    def observed(*args):
        calls.append(args[0])
        return validate(*args)
    monkeypatch.setattr(owned, 'interpolate_states', observed)
    mutable = bank()
    frozen = owned.FrozenOrbitBank(mutable)
    assert len(calls) == 1
    for phase in (-1, 0, 1):
        before = len(calls)
        actual = owned.phase_shifted_states(frozen, [0, 1.25, 2], phase)
        assert len(calls) == before
        expected = owned.phase_shifted_states(mutable, [0, 1.25, 2], phase)
        assert all(a.tobytes() == b.tobytes() for a, b in zip(actual, expected, strict=True))
    assert len(calls) == 4
    mutable['position_km'][0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        owned.phase_shifted_states(mutable, [0], 0)


@pytest.mark.parametrize('key', ['time_s', 'position_km', 'velocity_km_s'])
@pytest.mark.parametrize('bad', [np.nan, np.inf])
def test_invalid_snapshot_fails_full_validation(key, bad):
    source = bank()
    source[key] = np.asarray(source[key], float)
    source[key].flat[0] = bad
    with pytest.raises(ValueError):
        owned.FrozenOrbitBank(source)


@pytest.mark.parametrize('times,phase', [([np.nan], 0), ([[1]], 0), ([20], 1),
                                      ([0], np.inf), ([0], [0, 0, 0])])
def test_prepared_bank_keeps_per_call_validation(times, phase):
    with pytest.raises(ValueError):
        owned.phase_shifted_states(owned.FrozenOrbitBank(bank()), times, phase)
