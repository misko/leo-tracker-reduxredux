"""Reuse and batch the uniform GLRT spectra for both original references."""

from functools import lru_cache

import numpy as np

SYMBOLS = 64
FRAMES = 15
SHORT = 128
SIZE = 512
SYMBOL_INDEX = np.arange(SYMBOLS)


@lru_cache(maxsize=128)
def frequency_grid(step):
    return np.fft.fftfreq(SIZE, d=step)


class Workspace:
    def __init__(self):
        self.values = np.empty((2, FRAMES, SYMBOLS), dtype=np.complex128)
        self.short = np.empty((2, FRAMES, SHORT), dtype=np.complex128)
        self.power = np.empty((2, FRAMES, SHORT), dtype=float)
        self.summed = np.empty((2, SHORT), dtype=float)
        self.lags = np.empty((2, SHORT), dtype=np.complex128)
        self.packed = np.zeros((2, SIZE), dtype=np.complex128)
        self.spectrum = np.empty_like(self.packed)

    @property
    def nbytes(self):
        return sum(value.nbytes for value in vars(self).values())

    def spectra(self, exact, control, step):
        count = exact.shape[0]
        values = self.values[:, :count]
        short = self.short[:, :count]
        power = self.power[:, :count]
        values[0], values[1] = exact, control
        np.fft.fft(values, n=SHORT, axis=-1, out=short)
        np.abs(short, out=power)
        np.square(power, out=power)
        np.sum(power, axis=1, out=self.summed)
        np.fft.ifft(self.summed, axis=-1, out=self.lags)
        self.packed[:, :SYMBOLS] = self.lags[:, :SYMBOLS]
        self.packed[:, -(SYMBOLS - 1) :] = self.lags[:, -(SYMBOLS - 1) :]
        np.fft.fft(self.packed, axis=-1, out=self.spectrum)
        normalized = self.spectrum.real
        grid = frequency_grid(step)
        fits = []
        for i, branch in enumerate((exact, control)):
            denom = float(np.sum(np.sum(np.abs(branch), axis=1) ** 2))
            if denom > 0:
                np.divide(normalized[i], denom, out=normalized[i])
            best = int(np.argmax(normalized[i]))
            fits.append((float(normalized[i, best]), float(grid[best])))
        return tuple(fits)


class PairSpectrum:
    def __init__(self, producer, split_component, *, batched=True):
        self.workspace = Workspace() if batched else None
        self.original = producer._glrt_pair
        self.validate = producer._validate_glrt_pair
        self.component = split_component

    def supported(self, exact, *, size):
        return (
            size == SIZE
            and exact.values.ndim == 2
            and exact.values.shape[1] == SYMBOLS
            and 0 < exact.values.shape[0] <= FRAMES
            and exact.values.shape == exact.times_s.shape
        )

    def uniform_step(self, exact):
        step = exact.symbol_step_s
        lags = exact.times_s - exact.times_s[:, :1]
        expected = SYMBOL_INDEX * step
        return step if np.allclose(lags, expected, rtol=0, atol=1e-15) else None

    def scores(self, exact, control, *, size=SIZE):
        if self.supported(exact, size=size):
            self.validate(exact, control)
            step = self.uniform_step(exact)
            if step is not None:
                if self.workspace is None:
                    grid = frequency_grid(step)
                    return self.component(exact.values, grid), self.component(control.values, grid)
                return self.workspace.spectra(exact.values, control.values, step)
        return self.original(exact, control, size=size)
