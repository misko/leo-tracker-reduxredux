import numpy as np
import pytest

from reports.ALGO08.v3.whole_group_receiver_bound import (
    CARRIER_TAPS,
    CODE_LEN,
    LAGS,
    MODE_WIDTH,
    carrier_tail_floor,
    prunable_cells,
    timing_tail_floor,
)


def test_whole_block_requires_a_strict_finite_bound_on_every_member():
    upper = [0, 1, 0, 0, 0, np.nan, 0]
    assert prunable_cells(upper, 1, 2) == 3
    assert prunable_cells(upper, 1, 1) == 5
    assert prunable_cells(upper, np.inf, 1) == 0


def test_carrier_tail_bound_contains_two_modes_at_every_signed_bin():
    rng = np.random.default_rng(3203)
    modes = rng.normal(size=(2, MODE_WIDTH)) + 1j * rng.normal(size=(2, MODE_WIDTH))
    code = rng.normal(size=CODE_LEN) + 1j * rng.normal(size=CODE_LEN)
    code = code.astype(np.complex64)
    modes = modes.astype(np.complex64)
    epochs = [0, 3332]
    floor = carrier_tail_floor(modes, code, epochs)
    assert (np.diff(floor, axis=0) <= 0).all()
    for index, epoch in enumerate(epochs):
        x = modes[:, epoch:epoch + CARRIER_TAPS]
        for part in (0, 4, 7):
            start = CARRIER_TAPS * part // 8
            z = x[:, start:] * code[None, start:CARRIER_TAPS].conj()
            exact = np.sum(abs(np.fft.fft(z, n=4096, axis=1)) ** 2, axis=0) / np.sum(abs(x) ** 2)
            assert max(exact) < floor[part, index]


def test_timing_tail_uses_each_lags_window_energy_and_preserves_edges():
    rng = np.random.default_rng(3204)
    modes = rng.normal(size=(2, MODE_WIDTH)) + 1j * rng.normal(size=(2, MODE_WIDTH))
    code = rng.normal(size=CODE_LEN) + 1j * rng.normal(size=CODE_LEN)
    floor = timing_tail_floor(modes, code)
    assert (np.diff(floor, axis=0) <= 0).all()
    for epoch in (0, 3332):
        assert floor[0, epoch] == pytest.approx(8)
        timed = 0.
        for lag in LAGS:
            h = code[lag:] * code[:-lag].conj()
            h -= h.mean()
            x = np.sum(modes[:, lag:] * modes[:, :-lag].conj(), axis=0)[epoch:epoch + len(h)]
            start = len(h) * 7 // 8
            timed += abs(np.vdot(h[start:], x[start:])) ** 2 / (sum(abs(x) ** 2) * sum(abs(h) ** 2))
        assert timed < floor[7, epoch]
