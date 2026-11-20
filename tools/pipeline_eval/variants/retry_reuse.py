"""Reuse two shared anchor convolutions within one stereo detector visit."""

import ctypes as ct
import subprocess
from contextlib import contextmanager
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from . import capture_batched_fft, capture_fft, original_kernel
from .wide_regional import replace

PRIMARY = tuple(range(2, 302, 26))
RETRY = tuple(range(2, 302, 14))
SHARED = tuple(sorted(set(PRIMARY) & set(RETRY)))
SAMPLES = 200_000
LANES = 21


def _bank(source):
    source = replace(
        source,
        "            if (!count) continue;",
        """            if (!count) continue;
            int cached = -1;
            if (retry_mode && taps[s] == 44) {
                if (k->starts[s] == 88) cached = 0;
                if (k->starts[s] == 8096) cached = 1;
            }
            const int reused = cached >= 0 && retry_mode == 2;""",
    )
    start = source.index("            for (int f", source.index("            const int reused"))
    stop = source.index(
        "            for (int f", source.index("            inverse_calls += nf;", start)
    )
    transform = source[start:stop]
    source = (
        source[:start]
        + "            if (!reused) {\n"
        + transform
        + "            }\n"
        + source[stop:]
    )
    source = replace(
        source,
        "                double *row = k->scores + (size_t)f * ne;",
        """                double *row = k->scores + (size_t)f * ne;
                if (cached >= 0) {
                    float *mags = retry_magnitudes + ((size_t)cached * nf + f) * 200000 + first;
                    if (!reused) {
                        #pragma omp simd
                        for (int t = start[0]; t < stop[count - 1]; ++t) {
                            const int j = t + taps[s] - 1;
                            const float real = lane[j][0] / fft_length;
                            const float imag = lane[j][1] / fft_length;
                            mags[t] = sqrtf(real * real + imag * imag);
                        }
                    }
                    for (int m = 0; m < count; ++m) {
                        #pragma omp simd
                        for (int t = start[m]; t < stop[m]; ++t)
                            row[t + base[m]] += (double)mags[t] * (norm[t] * template_weight);
                    }
                    continue;
                }""",
    )
    return source


def build(work):
    work.mkdir()
    canonical = capture_fft.SOURCE.with_name("folded_bank.c")
    prepared = original_kernel.kernel(capture_batched_fft.fft_bank(canonical.read_text()))
    (work / canonical.name).write_text(_bank(prepared))
    port = replace(
        capture_fft.SOURCE.read_text(),
        "static _Thread_local CaptureFftStats *measurement;",
        """static _Thread_local CaptureFftStats *measurement;
static _Thread_local float *retry_magnitudes;
static _Thread_local int retry_mode;""",
    )
    port = replace(
        port,
        "int epochs, double *scores, int32_t *support, CaptureFftStats *stats",
        "int epochs, double *scores, int32_t *support, CaptureFftStats *stats, "
        "float *cache, int mode",
    )
    port = replace(
        port,
        "    measurement = stats;\n    capture_fft_fold(&kernel);\n    measurement = NULL;",
        """    measurement = stats;
    retry_magnitudes = cache;
    retry_mode = cache ? mode : 0;
    capture_fft_fold(&kernel);
    retry_mode = 0;
    retry_magnitudes = NULL;
    measurement = NULL;""",
    )
    path = work / capture_fft.SOURCE.name
    path.write_text(port)
    dll = work / "retry_reuse.so"
    command = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        "-I",
        str(original_kernel.HEADER.parent),
        str(path),
        "-lfftw3f",
        "-lm",
        "-o",
        str(dll),
    ]
    subprocess.run(command, check=True, timeout=30)
    return dll, command


_memcmp = ct.CDLL(None).memcmp
_memcmp.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_size_t)
_memcmp.restype = ct.c_int


def equal_arrays(left, right):
    return (
        left.shape == right.shape
        and left.dtype == right.dtype
        and left.flags.c_contiguous
        and right.flags.c_contiguous
        and (left is right or _memcmp(left.ctypes.data, right.ctypes.data, left.nbytes) == 0)
    )


class Grid(original_kernel.PersistentGrid):
    """One preallocated cache, held at most until the pending physical lane is tried."""

    def __init__(self, library):
        super().__init__(library)
        self._storage = np.empty((len(SHARED), LANES, SAMPLES), dtype=np.float32)
        self.native.argtypes += (ct.c_void_p, ct.c_int)
        native = self.native
        self._mode = 0
        self.native = lambda *args: native(*args, self._storage.ctypes.data, self._mode)
        self._active = None
        self._prepared = None
        self._last_capture = None

    @property
    def storage_bytes(self):
        return self._storage.nbytes

    def score_grid(
        self, acquisition, original, samples, template, rate, frequencies, symbols, epochs
    ):
        started = process_time_ns()
        identity = self._active
        scope = (rate, tuple(frequencies), epochs)
        mode = 0
        if (
            identity is not None
            and rate == 10_000_000
            and samples.shape == (SAMPLES,)
            and len(frequencies) == LANES
            and epochs == 13_333
            and template.ndim == 1
            and template.dtype == np.complex128
            and template.flags.c_contiguous
            and samples.dtype == np.complex128
            and samples.flags.c_contiguous
        ):
            if identity[0] == "capture" and symbols == PRIMARY:
                mode = 1
                self._last_capture = None
            elif identity[0] == "retry" and symbols == RETRY and self._prepared is not None:
                key, inputs, old_samples, old_template = self._prepared
                if (
                    key == identity[1]
                    and inputs == scope
                    and equal_arrays(samples, old_samples)
                    and equal_arrays(template, old_template)
                ):
                    mode = 2
        self._mode = mode
        before = len(self.calls)
        matched = process_time_ns()
        try:
            rows = super().score_grid(
                acquisition,
                original,
                samples,
                template,
                rate,
                frequencies,
                symbols,
                epochs,
            )
        finally:
            self._mode = 0
        if len(self.calls) != before:
            call = self.calls[-1]
            call.update(
                cache_mode=mode, lookup_cpu_ns=matched - started, storage_bytes=self.storage_bytes
            )
            if mode == 1 and call["applied"]:
                self._last_capture = identity[1], scope, samples, template
        return rows

    @contextmanager
    def route(self, acquisition, screen=None):
        from leo.scanner import fast_scan_detector

        prior = fast_scan_detector._evaluate_probe

        def evaluate(
            probe, config, calibration, *, edge, acquisition_config, receiver_id, probe_index
        ):
            phase = acquisition_config.anchor_symbols
            lanes = config.receiver_ids
            identity = receiver_id, probe_index, edge
            action = None
            if len(lanes) == 2 and all(r in lanes for r in (0, 1)) and len(probe) == SAMPLES:
                if phase == PRIMARY:
                    if receiver_id == lanes[0]:
                        self._prepared = None
                    if self._prepared is None:
                        action = "capture"
                elif phase == RETRY:
                    action = "retry"
            self._active = (action, identity) if action else None
            self._last_capture = None
            try:
                result = prior(
                    probe,
                    config,
                    calibration,
                    edge=edge,
                    acquisition_config=acquisition_config,
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                )
                if action == "capture" and not result.has_fractional_detection(
                    config.glrt64_margin_gate
                ):
                    self._prepared = self._last_capture
                return result
            finally:
                self._active = self._last_capture = None

        with (
            super().route(acquisition, screen),
            patch.object(fast_scan_detector, "_evaluate_probe", evaluate),
        ):
            try:
                yield self
            finally:
                self._active = self._prepared = self._last_capture = None
