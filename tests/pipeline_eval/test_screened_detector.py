from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants.screened_detector import FractionalRows, route


def exact(samples, locations, *, half_width=8):
    """Direct fractional row construction without a cache or a common-phase path."""
    locations = np.asarray(locations, dtype=float)
    rounded = np.rint(locations)
    if np.all(np.abs(locations - rounded) <= 1e-12):
        indexes = rounded.astype(np.int64)
        if np.any(indexes < 0) or np.any(indexes >= len(samples)):
            raise ValueError("integer bounds")
        return np.asarray(samples, dtype=np.complex128)[indexes]
    offsets = np.arange(1 - half_width, half_width + 1)
    indexes = np.floor(locations).astype(np.int64)[..., None] + offsets
    if np.any(indexes < 0) or np.any(indexes >= len(samples)):
        raise ValueError("fractional bounds")
    distance = locations[..., None] - indexes
    weights = np.sinc(distance) * np.sinc(distance / half_width)
    return np.sum(samples[indexes] * (weights / weights.sum(axis=-1, keepdims=True)), axis=-1)


def samples():
    rng = np.random.default_rng(287210)
    return rng.normal(size=200000) + 1j * rng.normal(size=200000)


@pytest.mark.parametrize("phase", [0.25, 0.11397238121742, -0.374191781, 0.0, 4e-13])
def test_fractional_rows_exact_across_sample_binades(phase):
    offsets = np.array([17, 31, 63, 121, 511, 1023, 4090, 8191, 16384, 65536, 131078])
    positions = (offsets[:, None] + np.arange(15)).astype(float) + phase
    values = samples()
    rows = FractionalRows(exact)
    assert rows(values, positions).tobytes() == exact(values, positions).tobytes()
    assert rows(values, positions).tobytes() == exact(values, positions).tobytes()
    if phase == 0.25:
        assert rows.receipts()["uniform_calls"] == 2
        assert rows.receipts()["weight_rows"] == 1
    if phase == 0.11397238121742:
        assert 0 < rows.receipts()["weight_rows"] <= 8
        assert rows.receipts()["fallback_calls"] == 0


def test_caps_and_scope_restore_original():
    values = samples()
    positions = np.arange(38) + 200.3
    module = SimpleNamespace(fractional_take=exact)
    with route(module) as rows:
        for i in range(540):
            module.fractional_take(values, positions + i / 1024)
        assert rows.receipts()["cache"]["currsize"] == 512
        wide = np.linspace(20.1, 21.9, 48)
        np.testing.assert_array_equal(module.fractional_take(values, wide), exact(values, wide))
        assert rows.receipts()["fallback_calls"] == 1
        with pytest.raises(ValueError, match="bounds"):
            module.fractional_take(values, positions + len(values))
    assert module.fractional_take is exact
