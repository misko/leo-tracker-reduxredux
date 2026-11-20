"""Reuse bit-identical numeric acquisition work within one guarded receiver call."""

from functools import wraps
from time import process_time

import numpy as np

from .dense_q10 import DenseQ10Grid


def same_bytes(left, right):
    return (
        left.shape == right.shape
        and left.dtype == right.dtype
        and np.array_equal(np.ascontiguousarray(left).view(np.uint8), right.view(np.uint8))
    )


def frequency_key(frequencies):
    return tuple(float(value).hex() for value in frequencies)


class ReusedGrid(DenseQ10Grid):
    def __init__(self, library, control, fine_scores):
        super().__init__(library, control)
        self._fine_original = fine_scores
        self._scope = None
        self.reuse = []

    def guarded_acquisition(self, guarded):
        @wraps(guarded)
        def run(*args, **kwargs):
            previous = self._scope
            scope = dict(first=None, attempt=None, fine={}, fine_hits=0, coarse_hits=0)
            self._scope = scope
            try:
                return guarded(*args, **kwargs)
            finally:
                self._scope = previous
                self.reuse.append(
                    dict(fine_hits=scope["fine_hits"], coarse_hits=scope["coarse_hits"])
                )

        return run

    def score_grid(self, values, template, rate, frequencies, symbols, epochs):
        start = process_time()
        args = values, template, rate, frequencies, symbols, epochs
        scope = self._scope
        if scope is None:
            return super().score_grid(*args)
        key = rate, frequency_key(frequencies), tuple(symbols), epochs
        first = scope["first"]
        if (
            first is not None
            and first["scores"] is not None
            and key == first["geometry"]
            and same_bytes(values, first["values"])
            and same_bytes(template, first["template"])
        ):
            first["hit"] = True
            scope["attempt"] = args
            scope["coarse_hits"] += 1
            rows = tuple(row.copy() for row in first["scores"])
            self.receipts.append(dict(coarse_cpu_s=process_time() - start, reused=True))
            return rows
        rows = super().score_grid(*args)
        scope["attempt"] = args
        scope["fine"].clear()
        scope["first"] = dict(
            geometry=key,
            values=values.copy(),
            template=template.copy(),
            scores=None,
            hit=False,
        )
        self.receipts[-1]["coarse_cpu_s"] = process_time() - start
        return rows

    def retain_peaks(self, residuals, scores, count, epoch_separation, cfo_separation, epochs):
        start = process_time()
        selection = frequency_key(residuals), count, epoch_separation, cfo_separation, epochs
        scope = self._scope
        if scope is None or scope["first"] is None:
            return super().retain_peaks(residuals, scores, *selection[1:])
        first = scope["first"]
        if first["hit"] and selection == first["selection"]:
            self.receipts[-1]["repair_cpu_s"] = process_time() - start
            return first["peaks"]
        if first["hit"]:
            scope["coarse_hits"] -= 1
            exact_rows = super().score_grid(*scope["attempt"])
            peaks = super().retain_peaks(residuals, exact_rows, *selection[1:])
            for target, source in zip(scores, exact_rows, strict=True):
                target[:] = source
        else:
            peaks = super().retain_peaks(residuals, scores, *selection[1:])
        snapshots = tuple(row.copy() for row in scores)
        first.update(selection=selection, peaks=peaks, scores=snapshots, hit=False)
        retained_bytes = first["values"].nbytes + first["template"].nbytes
        retained_bytes += sum(a.nbytes for a in snapshots)
        self.receipts[-1].update(
            reuse_cache_bytes=retained_bytes, repair_cpu_s=process_time() - start
        )
        return peaks

    def fine_scores(self, values, template, rate, epoch, frequencies, symbols):
        scope = self._scope
        args = values, template, rate, epoch, frequencies, symbols
        if (
            scope is None
            or scope["attempt"] is None
            or values is not scope["attempt"][0]
            or template is not scope["attempt"][1]
        ):
            return self._fine_original(*args)
        key = rate, epoch, frequency_key(frequencies), tuple(symbols)
        rows = scope["fine"]
        if key in rows:
            scope["fine_hits"] += 1
            return rows[key]
        rows[key] = self._fine_original(*args)
        return rows[key]
