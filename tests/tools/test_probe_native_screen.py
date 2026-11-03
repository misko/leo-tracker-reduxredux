"""Screen execution padding must preserve every scientific grid row and input."""

from types import SimpleNamespace

import numpy as np
from probe_native_screen import screen_grid


def test_tiles_keep_scientific_rows_and_do_not_modify_iq():
    calls = []
    values = np.arange(40, dtype=float).astype(complex)
    saved = values.copy()
    reference = values * 2
    frequencies = tuple(float(i) for i in range(29))

    def native(*args):
        calls.append(args)
        assert len(args[2]) == 24
        np.testing.assert_array_equal(args[0], saved)
        np.testing.assert_array_equal(args[1], reference)
        return np.repeat(args[2][:, None], args[-1], axis=1)

    acquisition = SimpleNamespace(OFDM_SYMBOL_DURATION_S=.01, FRAME_RATE_HZ=10,
                                  _power_prefix=lambda x: np.r_[0., np.cumsum(abs(x)**2)])
    result = screen_grid(SimpleNamespace(folded_anchor_score_grid=native), acquisition,
                         values, reference, 100., frequencies, (1, 3), 10)
    assert len(calls) == 2 and len(result) == 29
    np.testing.assert_array_equal(np.asarray(result)[:, 0], frequencies)
    np.testing.assert_array_equal(calls[1][2][5:], np.full(19, 28.))
    np.testing.assert_array_equal(values, saved)
    np.testing.assert_array_equal(calls[0][3], [1, 3])
    np.testing.assert_array_equal(calls[0][4], [2, 4])
    np.testing.assert_array_equal(calls[0][5], [0, 10, 20, 30])
