"""Reuse a receiver's folded 12-anchor sum during a nested 22-anchor retry."""

import ctypes as ct
import os
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from . import capture_batched_fft, capture_fft, original_kernel

SECOND = tuple(range(2, 302, 14))
PRIMARY = tuple(SECOND[(i * 21 + 5) // 11] for i in range(12))
ADDITION = tuple(s for s in SECOND if s not in PRIMARY)
MODES = ("original", "recompute", "reuse")


def build(work):
    """Build the same prepared bank with an opt-in unnormalized sum return."""
    wrapper = capture_fft.SOURCE.read_text()
    anchor = "#define LEO_GRID_FUNCTION capture_fft_fold"
    if wrapper.count(anchor) != 1:
        raise ValueError("prepared FFT port changed")
    wrapper = wrapper.replace(
        anchor,
        """static _Thread_local int retain_folded_sums;
void capture_fft_retain_sums(int enabled) { retain_folded_sums = enabled; }
"""
        + anchor,
    )
    source = work / "capture_fft.c"
    source.write_text(wrapper)
    bank = capture_fft.SOURCE.with_name("folded_bank.c").read_text()
    bank = original_kernel.kernel(capture_batched_fft.fft_bank(bank))
    normalization = "    for (int f = 0; f < nf; ++f) {\n        double *row = k->scores"
    if bank.count(normalization) != 1:
        raise ValueError("prepared FFT normalization loop changed")
    bank = bank.replace(
        normalization, normalization.replace("for", "if (!retain_folded_sums) for", 1)
    )
    (work / "folded_bank.c").write_text(bank)
    lib = work / "nested_anchors.so"
    command = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        "-I",
        str(original_kernel.HEADER.parent),
        str(source),
        "-lfftw3f",
        "-lm",
        "-o",
        str(lib),
    ]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(work)}, check=True, timeout=30)
    return lib, command


def divide(sums, support, *, out):
    # Uncovered cells have zero accumulated magnitude in the original bank.
    np.divide(sums, support, out=out, where=support > 0)
    return tuple(out)


class NestedGrid(original_kernel.PersistentGrid):
    def __init__(self, path):
        super().__init__(path)
        self._port = self.native
        self.native = self._measure_support
        self._sums = self.library.capture_fft_retain_sums
        self._sums.argtypes = (ct.c_int,)
        self._sums.restype = None
        self._take_support = False
        self._support = None
        self.partials = {}
        self.active = None
        self.mode = "original"
        self.audit = None
        self.peak_partial_bytes = 0
        self.reuses = 0

    def _measure_support(self, *args):
        status = self._port(*args)
        if self._take_support and status == 0:
            epochs, address = args[13], args[15]
            self._support = np.ctypeslib.as_array(
                (ct.c_int32 * epochs).from_address(address)
            ).copy()
        return status

    def _raw(self, *args):
        self._support = None
        self._take_support = True
        self._sums(1)
        try:
            rows = super().score_grid(*args)
            if self._support is None:
                return rows, None
            return rows[0].base, self._support
        finally:
            self._sums(0)
            self._take_support = False
            self._support = None

    def score_grid(
        self, acquisition, original, samples, template, rate, frequencies, symbols, epochs
    ):
        args = acquisition, original, samples, template, rate, frequencies, symbols, epochs
        if self.mode != "reuse" or self.active is None:
            return super().score_grid(*args)
        receiver, probe, edge = self.active
        key = receiver, probe, edge, rate, tuple(frequencies), epochs, samples.size
        if symbols == PRIMARY:
            raw, support = self._raw(*args)
            if support is None:
                self.partials.pop(key, None)
                return raw
            self.partials[key] = raw, support
            self.peak_partial_bytes = max(
                self.peak_partial_bytes,
                sum(sums.nbytes + weights.nbytes for sums, weights in self.partials.values()),
            )
            return divide(raw, support, out=np.zeros_like(raw))
        partial = self.partials.get(key)
        if symbols == SECOND and partial is not None:
            raw, support = self._raw(*args[:-2], ADDITION, epochs)
            if support is not None:
                before = process_time_ns()
                raw += partial[0]
                support += partial[1]
                rows = divide(raw, support, out=raw)
                self.reuses += 1
                self.calls[-1]["combine_cpu_ns"] = process_time_ns() - before
                if self.audit is not None:
                    self.audit(args, rows, support)
                return rows
        return super().score_grid(*args)

    @contextmanager
    def window(self, detector, mode):
        """Bind a cache to a single capture producer window with physical lane order."""
        if mode not in MODES or self.active is not None or self.partials:
            raise ValueError("unexpected nested detector mode or window scope")
        inner = detector._evaluate_probe
        attempts = []
        self.mode = mode
        self.reuses = self.peak_partial_bytes = 0

        def evaluate(
            probe, config, calibration, *, acquisition_config, receiver_id, probe_index, edge
        ):
            original = acquisition_config.anchor_symbols
            if mode != "original" and len(original) == len(PRIMARY):
                acquisition_config = replace(acquisition_config, anchor_symbols=PRIMARY)
            if len(original) != len(PRIMARY) and original != SECOND:
                raise ValueError("installed capture anchor geometry changed")
            self.active = receiver_id, probe_index, edge
            try:
                result = inner(
                    probe,
                    config,
                    calibration,
                    acquisition_config=acquisition_config,
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    edge=edge,
                )
                gate = result.has_fractional_detection(config.glrt64_margin_gate)
                attempts.append((receiver_id, len(original), gate))
                if gate:
                    self.partials = {k: v for k, v in self.partials.items() if k[0] != receiver_id}
                return result
            finally:
                self.active = None

        try:
            with patch.object(detector, "_evaluate_probe", evaluate):
                yield attempts
        finally:
            self.partials.clear()
            self.mode = "original"
