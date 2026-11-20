"""Exact gated reuse inside one original physical probe evaluation."""

from collections import Counter, OrderedDict
from contextlib import contextmanager
from struct import pack
from unittest.mock import patch

import numpy as np

from . import fine_batch, fine_search


class EpochBatch(fine_batch.FineBatch):
    """Share the original unrotated weighted aperture at repeated epochs."""

    def __init__(self, library, acquisition):
        super().__init__(library, acquisition)
        self.apertures = OrderedDict()
        self.hits = 0
        self.retained_bytes = 0
        self.probe = None

    def score(self, values, template, rate, epoch, frequencies, symbols, *, transform_size):
        fine = fine_search
        if not (
            values is self.probe
            and self.compatible
            and rate == fine.RATE
            and transform_size == fine.FFT_SIZE
            and symbols == fine.SYMBOLS
            and values.shape == (fine.SAMPLES,)
            and template.shape == (fine.EPOCHS,)
            and values.dtype == template.dtype == np.complex128
            and 0 <= epoch < fine.EPOCHS
            and 2 <= len(frequencies) <= fine.MAX_BINS
            and self.acquisition._constant_grid_step(frequencies) == fine.RATE / fine.FFT_SIZE
            and np.isfinite(frequencies[0])
        ):
            return super().score(
                values, template, rate, epoch, frequencies, symbols, transform_size=transform_size
            )
        key = id(template), epoch
        cached = self.apertures.pop(key, None)
        if cached is None:
            starts = epoch + fine.FRAME_BASE
            frames = int(np.searchsorted(starts, fine.SAMPLES - fine.STOP, side="right"))
            received = np.stack(
                [
                    values[start + fine.FIRST : start + fine.STOP]
                    .reshape(-1, fine.TAPS)[::2]
                    .ravel()
                    for start in starts[:frames]
                ]
            )
            references = template[fine.PILOTS]
            energy = float(np.vdot(references, references).real)
            denominator = np.sqrt(energy * np.sum(np.abs(received) ** 2, axis=1))
            weights = received * np.conj(references)[None, :]
            del received
            cached = template, weights, denominator
            if len(self.apertures) == 2:
                self.apertures.popitem(last=False)
        else:
            self.hits += 1
        self.apertures[key] = cached
        self.retained_bytes = max(
            self.retained_bytes, sum(w.nbytes + d.nbytes for _, w, d in self.apertures.values())
        )
        _, weights, denominator = cached
        frames = len(weights)
        selected = self._selected(weights * fine._rotation(frequencies[0]), len(frequencies)).T
        normalized = np.divide(
            np.abs(selected),
            denominator[None, :],
            out=np.zeros_like(selected.real),
            where=denominator[None, :] > 0,
        )
        self.calls += 1
        self.frames += frames
        self.bins += frames * len(frequencies)
        return tuple(float(v) for v in np.mean(normalized, axis=1))

    @contextmanager
    def bind(self, detector):
        evaluate = detector._evaluate_probe

        def scoped(probe, *args, **kwargs):
            self.probe = probe
            try:
                return evaluate(probe, *args, **kwargs)
            finally:
                self.apertures.clear()
                self.probe = None

        with patch.object(detector, "_evaluate_probe", scoped), self.route():
            yield self


class GuardReuse:
    """Reuse pure inputs during the producer's existing direct conditioned recheck."""

    def __init__(self, acquisition, detector, grid, bank):
        self.acquisition, self.detector, self.grid, self.bank = acquisition, detector, grid, bank
        self.probe = None
        self.templates = []
        self.values = {}
        self.hits = Counter()
        self.retained_bytes = 0
        self._bytes = 0

    def template_key(self, template):
        for i, t in enumerate(self.templates):
            if template is t or (
                template.dtype == t.dtype
                and template.shape == t.shape
                and memoryview(template).cast("B") == memoryview(t).cast("B")
            ):
                return i
        self.templates.append(template)
        return len(self.templates) - 1

    def record(self, kind, values, template, fields, function):
        if values is not self.probe or not template.flags.c_contiguous:
            return function()
        key = (kind, self.template_key(template), fields)
        if self.bank._direct_only:
            if key in self.values:
                self.hits[kind] += 1
                return self.values[key]
            return function()
        result = function()
        if key not in self.values:
            size = sum(x.nbytes for x in result) if kind == "coarse" else 40 + 32 * len(result)
            self._bytes += size
            self.retained_bytes = max(self.retained_bytes, self._bytes)
        self.values[key] = result
        return result

    @contextmanager
    def route(self):
        acquisition, detector, grid = self.acquisition, self.detector, self.grid
        evaluate, stock_coarse = detector._evaluate_probe, grid.score_grid
        stock_fine, stock_verify = (
            acquisition._normalized_frame_scores_fft,
            acquisition.normalized_frame_score,
        )

        def scope(probe, *args, **kwargs):
            self.probe = probe
            try:
                return evaluate(probe, *args, **kwargs)
            finally:
                self.values.clear()
                self.templates.clear()
                self._bytes = 0
                self.probe = None

        def coarse(acq, original, values, template, rate, frequencies, symbols, epochs):
            fields = (rate, np.asarray(frequencies, dtype=np.float64).tobytes(), symbols, epochs)
            return self.record(
                "coarse",
                values,
                template,
                fields,
                lambda: stock_coarse(
                    acq, original, values, template, rate, frequencies, symbols, epochs
                ),
            )

        def fine(values, template, rate, epoch, frequencies, symbols, *, transform_size):
            fields = (
                rate,
                epoch,
                np.asarray(frequencies, dtype=np.float64).tobytes(),
                symbols,
                transform_size,
            )
            return self.record(
                "fine",
                values,
                template,
                fields,
                lambda: stock_fine(
                    values,
                    template,
                    rate,
                    epoch,
                    frequencies,
                    symbols,
                    transform_size=transform_size,
                ),
            )

        def verify(values, template, rate, epoch, cfo, symbols):
            fields = (rate, epoch, pack("=d", cfo), symbols)
            return self.record(
                "verify",
                values,
                template,
                fields,
                lambda: stock_verify(values, template, rate, epoch, cfo, symbols),
            )

        with (
            patch.object(detector, "_evaluate_probe", scope),
            patch.object(grid, "score_grid", coarse),
            patch.object(acquisition, "_normalized_frame_scores_fft", fine),
            patch.object(acquisition, "normalized_frame_score", verify),
        ):
            yield self
