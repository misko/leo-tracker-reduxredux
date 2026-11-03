"""Interpolation reuse must preserve the original per-position arithmetic."""

import numpy as np
import pytest

from leo.analysis.starlink.fast_scan_fractional import fractional_take


def reference(values, locations, half_width=8):
    locations = np.asarray(locations, dtype=float)
    indexes = np.floor(locations).astype(np.int64)[..., None] + np.arange(
        -half_width + 1, half_width + 1, dtype=np.int64)
    distance = locations[..., None] - indexes
    weights = np.sinc(distance) * np.sinc(distance / half_width)
    weights /= np.sum(weights, axis=-1, keepdims=True)
    return np.sum(values[indexes] * weights, axis=-1)


@pytest.mark.parametrize("half_width", [2, 8, 17])
@pytest.mark.parametrize("offset", [.25, -.31, np.nextafter(.5, 1.), 1e-10])
def test_repeated_offset_is_bit_exact_across_integer_boundaries(half_width, offset):
    rng = np.random.default_rng(20261103)
    samples = rng.normal(size=20000) + 1j * rng.normal(size=20000)
    positions = np.arange(32, 8192, dtype=float).reshape(120, 68) + offset
    actual = fractional_take(samples, positions, half_width=half_width)
    np.testing.assert_array_equal(actual, reference(samples, positions, half_width))


@pytest.mark.parametrize("shape", [(), (1,), (31,), (32,), (4, 8), (2, 3, 40)])
def test_arbitrary_offsets_and_shapes_preserve_original_result(shape):
    rng = np.random.default_rng(20261103)
    samples = rng.normal(size=1000) + 1j * rng.normal(size=1000)
    positions = rng.uniform(10, 990, size=shape)
    np.testing.assert_array_equal(
        fractional_take(samples, positions), reference(samples, positions))


def test_common_offset_computes_only_one_weight_row(monkeypatch):
    original = np.sinc
    shapes = []

    def measured(x):
        shapes.append(x.shape)
        return original(x)

    monkeypatch.setattr(np, "sinc", measured)
    values = np.arange(2000).astype(complex)
    positions = np.arange(32, 1200).reshape(16, 73) + .25
    fractional_take(values, positions)
    assert shapes == [(16,), (16,)]


def test_integer_and_empty_paths_are_unchanged():
    values = np.arange(100).astype(complex)
    np.testing.assert_array_equal(fractional_take(values, np.arange(100)), values)
    assert fractional_take(values, np.empty((0, 3))).shape == (0, 3)


@pytest.mark.parametrize("positions", [np.arange(32)+.25, np.arange(70, 102)+.25,
                                      np.array([np.nan])])
def test_unsupported_positions_still_fail(positions):
    with pytest.raises(ValueError):
        fractional_take(np.ones(100), positions)
