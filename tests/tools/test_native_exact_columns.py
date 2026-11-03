"""Sparse rescoring must preserve sample/prefix indexing and execution tiling."""

from types import SimpleNamespace

import numpy as np
import pytest
from native_exact_columns import ExactColumns


def prepared(frequency_count=21, epochs=100):
    values = np.arange(400).astype(complex)
    prefix = np.r_[0., np.cumsum(abs(values)**2)]
    calls = []

    def native(*args):
        calls.append(args)
        np.testing.assert_array_equal(args[0], values)
        np.testing.assert_array_equal(args[6], prefix)
        assert args[-1] == 1
        return (args[2] + args[5][0])[:, None]

    acquisition = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=.01, FRAME_RATE_HZ=10,
        _power_prefix=lambda _: prefix,
        _native_acquisition=SimpleNamespace(folded_anchor_score_grid=native),
        _folded_anchor_score_grid_backend=lambda: 'avx2_fma',
        _constant_grid_step=lambda _: 1.)
    frequencies = tuple(float(i) for i in range(frequency_count))
    args = (values, values * 2, 100., frequencies, (1, 3), epochs)
    def full(*args):
        return np.arange(frequency_count)[:, None] + np.arange(epochs)[None, :]

    return ExactColumns(acquisition, full, args), calls


@pytest.mark.parametrize('count', [1, 8, 11, 12, 21, 25])
def test_columns_match_full_geometry_at_start_middle_end(count):
    oracle, calls = prepared(count)
    selected = np.array([0, 50, 99])
    np.testing.assert_array_equal(oracle(selected), np.arange(count)[:, None] + selected[None, :])
    expected_tiles = (count + 11) // 12
    assert len(calls) == 3 * expected_tiles
    for j in range(3):
        for args in calls[j*expected_tiles:(j+1)*expected_tiles]:
            np.testing.assert_array_equal(args[5], np.arange(0, 400, 10) + selected[j])
    if count == 11:
        assert len(calls[0][2]) == 12 and calls[0][2][-1] == 11.


def test_dense_request_uses_complete_original_grid():
    oracle, calls = prepared(21, 200)
    selected = np.arange(150)
    np.testing.assert_array_equal(oracle(selected), np.arange(21)[:, None] + selected[None, :])
    assert not calls and oracle.dense_fallback_calls == 1


@pytest.mark.parametrize('columns', [[-1], [100], [1.5], [True], [[1]]])
def test_invalid_columns_rejected(columns):
    oracle, _ = prepared()
    with pytest.raises(ValueError):
        oracle(columns)
