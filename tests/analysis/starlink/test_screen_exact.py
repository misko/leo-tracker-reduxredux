"""Sparse batching preserves original frame coordinates, CFO tiling and request order."""

from types import SimpleNamespace

import numpy as np

from leo.analysis.starlink._screen_exact import ExactColumns


def test_component_batch_uses_original_coordinates_and_keeps_duplicate_columns():
    calls = []
    x = np.ones(500, complex)
    prefix = np.r_[0., np.cumsum(abs(x)**2)]

    def batch(*args):
        calls.append(args)
        np.testing.assert_array_equal(args[5], np.arange(0, 500, 10))
        np.testing.assert_array_equal(args[6], prefix)
        assert args[8] == 100
        return args[2][:, None]+args[9][None, :]

    g = SimpleNamespace(_power_prefix=lambda x: prefix, OFDM_SYMBOL_DURATION_S=.01,
                        FRAME_RATE_HZ=10, _folded_anchor_score_grid_backend=lambda: 'avx2_fma',
                        _constant_grid_step=lambda f: 1.,
                        _native_acquisition=SimpleNamespace(folded_anchor_score_grid=None))
    args = x, x, 100., tuple(range(21)), (0,), 100
    oracle = ExactColumns(g, None, args, columns_native=batch)
    columns = np.array([99, 0, 50, 99], dtype=np.intp)
    np.testing.assert_array_equal(oracle(columns), np.arange(21)[:, None]+columns[None, :])
    assert len(calls) == 2
    assert oracle.native_calls == 2
