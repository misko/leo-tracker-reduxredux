"""Research sparse-epoch scoring using the unmodified deployed FP64 kernel.

Shift each frame base by the requested epoch and evaluate one epoch, retaining
the original samples, energy prefix, CFO tiling and symbol/frame accumulation.
This avoids any new arithmetic implementation, but repeats native validation and
template preparation per column. Dense requests use the original complete grid.
"""

import numpy as np


class ExactColumns:
    def __init__(self, acquisition, full_grid, args):
        self.acquisition = acquisition
        self.full_grid = full_grid
        self.args = args
        values, template, rate, frequencies, symbols, epochs = args
        self.values = np.asarray(values, np.complex128)
        self.template = np.asarray(template, np.complex128)
        self.rate = float(rate)
        self.epochs = epochs
        self.frequencies = frequencies
        self.starts = np.asarray([round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S)
                                  for s in symbols], dtype=np.intp)
        self.stops = np.asarray([round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S)
                                 for s in symbols], dtype=np.intp)
        period = rate / acquisition.FRAME_RATE_HZ
        offsets, frame = [], 0
        while (offset := round(frame * period)) < self.values.size:
            offsets.append(offset)
            frame += 1
        self.offsets = np.asarray(offsets, np.intp)
        self.prefix = acquisition._power_prefix(self.values)
        self.native = acquisition._native_acquisition.folded_anchor_score_grid
        if acquisition._folded_anchor_score_grid_backend() != 'avx2_fma':
            raise ValueError('This exact-column prototype requires the deployed AVX2/FMA backend')
        self.tiles = []
        if len(frequencies) > 12:
            for start in range(0, len(frequencies), 12):
                tile = frequencies[start:start + 12]
                self.tiles.append((np.asarray((*tile, *((tile[-1],) * (12-len(tile)))), float),
                                   len(tile)))
        elif frequencies:
            step = acquisition._constant_grid_step(frequencies)
            execution = ((*frequencies, frequencies[-1] + step)
                         if len(frequencies) == 11 and step is not None else frequencies)
            self.tiles.append((np.asarray(execution, float), len(frequencies)))
        self.native_calls = 0
        self.dense_fallback_calls = 0

    def __call__(self, columns):
        columns = np.asarray(columns)
        if (columns.ndim != 1 or not np.issubdtype(columns.dtype, np.integer)
                or np.any(columns < 0) or np.any(columns >= self.epochs)):
            raise ValueError('Exact epoch columns must be in-range integers')
        if len(columns) > 128:
            self.dense_fallback_calls += 1
            return np.asarray(self.full_grid(*self.args))[:, columns]
        result = np.empty((len(self.frequencies), len(columns)), dtype=float)
        for j, epoch in enumerate(columns):
            shifted_offsets = self.offsets + epoch
            start = 0
            for frequencies, count in self.tiles:
                scores = self.native(self.values, self.template, frequencies,
                                     self.starts, self.stops, shifted_offsets, self.prefix,
                                     self.rate, 1)
                result[start:start + count, j] = scores[:count, 0]
                start += count
                self.native_calls += 1
        return result
