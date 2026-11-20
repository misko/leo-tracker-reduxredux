from dataclasses import dataclass

import numpy as np
import pytest

from leo.analysis.research.track_catalogue_geometry import interpolate_states
from tools.pipeline_eval.variants import v5_catalogue_memory as memory


@dataclass
class Catalogue:
    names: tuple
    satellite_numbers: tuple
    satellites: tuple

    def __len__(self):
        return len(self.satellites)


@pytest.mark.parametrize("n, sizes", [(0, [0]), (256, [256]), (517, [256, 256, 5])])
def test_bounded_propagation_preserves_catalogue_order_full_grid_and_errors(n, sizes):
    numbers = tuple(range(n + 1000, 1000, -1))
    catalogue = Catalogue(tuple(map(str, numbers)), numbers, numbers)
    offsets = np.array([-40.0, 0.0, 1.0, 340.0])
    calls = []

    def propagate(batch, origin, times):
        assert batch.names == tuple(map(str, batch.satellite_numbers))
        assert batch.satellites == batch.satellite_numbers
        assert times is offsets and origin == 1790000000123456789
        calls.append(len(batch))
        number = np.asarray(batch.satellites)[:, None, None]
        position = number * 100 + times[None, :, None] + np.arange(3)
        velocity = position / 3.0
        usable = number[:, 0, 0].astype(int) % 7 != 0
        return position, velocity, usable

    expected = propagate(catalogue, 1790000000123456789, offsets)
    calls.clear()
    actual = memory.bounded_states(propagate, catalogue, 1790000000123456789, offsets)
    assert calls == sizes
    for candidate, control in zip(actual, expected, strict=True):
        assert candidate.dtype == control.dtype
        np.testing.assert_array_equal(candidate, control)


class CopyingBank:
    keys = ("time_s", "position_km", "velocity_km_s")

    def __init__(self, bank):
        arrays = [np.asarray(bank[key], float) for key in self.keys]
        self._entries = tuple((a.tobytes(), a.shape) for a in arrays)
        interpolate_states(self, np.empty(0))

    def __getitem__(self, key):
        data, shape = self._entries[self.keys.index(key)]
        return np.frombuffer(data, dtype=float).reshape(shape)


def bank_values():
    return dict(
        time_s=np.array([-1.0, 0.0, 1.0]),
        position_km=np.zeros((2, 3, 3)),
        velocity_km_s=np.ones((2, 3, 3)),
    )


def test_fresh_state_owners_are_retained_through_read_only_buffers():
    usage = dict(retained=0, copied=0)
    bank_type = memory.residual_bank_type(CopyingBank, interpolate_states, usage)
    source = bank_values()
    expected = CopyingBank(source)
    bank = bank_type(source)
    assert usage == {"retained": 1, "copied": 0}
    assert not np.shares_memory(bank["time_s"], source["time_s"])
    for key in memory.STATE_KEYS:
        assert np.shares_memory(bank[key], source[key])
        assert not source[key].flags.writeable
        with pytest.raises(ValueError):
            bank[key].setflags(write=True)
    for a, b in zip(
        interpolate_states(bank, [0.5]), interpolate_states(expected, [0.5]), strict=True
    ):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("alias_style", ["same_object", "external_view", "input_view"])
def test_writable_aliases_use_the_independent_legacy_copy(alias_style):
    usage = dict(retained=0, copied=0)
    bank_type = memory.residual_bank_type(CopyingBank, interpolate_states, usage)
    source = bank_values()
    if alias_style == "same_object":
        alias = source["position_km"]
    elif alias_style == "external_view":
        alias = source["position_km"].view()
    else:
        alias = source["position_km"]
        source["position_km"] = alias.view()
    bank = bank_type(source)
    assert usage == {"retained": 0, "copied": 1}
    alias[0, 0, 0] = 123
    assert bank["position_km"][0, 0, 0] == 0


@pytest.mark.parametrize(
    "malformed, message",
    [
        (lambda: np.zeros((2, 3, 2)), "state arrays"),
        (lambda: np.full((2, 3, 3), np.inf), "finite satellite states"),
    ],
)
def test_copy_free_bank_retains_shape_and_finiteness_validation(malformed, message):
    usage = dict(retained=0, copied=0)
    bank_type = memory.residual_bank_type(CopyingBank, interpolate_states, usage)
    source = bank_values()
    source["position_km"] = malformed()
    with pytest.raises(ValueError, match=message):
        bank_type(source)
