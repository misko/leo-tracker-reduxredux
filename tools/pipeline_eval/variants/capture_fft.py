"""Opt-in full folded FFT grid for a dedicated capture-era worker process."""

import ctypes as ct
import subprocess
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import RLock
from time import process_time_ns
from unittest.mock import patch

import numpy as np

SOURCE = Path(__file__).with_suffix(".c")
FLAGS = ("-std=c11", "-O3", "-ffp-contract=off", "-fno-fast-math", "-fPIC", "-shared", "-pthread")
_PORT = RLock()


class Stats(ct.Structure):
    _fields_ = (
        ("fft_length", ct.c_int),
        ("input_ffts", ct.c_int),
        ("inverse_ffts", ct.c_int),
        ("filter_ffts", ct.c_int),
        ("buffer_bytes", ct.c_size_t),
    )


def build(path):
    subprocess.run(
        ["cc", *FLAGS, str(SOURCE), "-lfftw3", "-lm", "-o", str(path)],
        check=True,
        timeout=30,
    )
    return path


class FullGrid:
    def __init__(self, library):
        self.library = ct.CDLL(str(library))
        self.native = self.library.capture_fft_score_grid
        self.native.restype = ct.c_int
        ptr, number = ct.c_void_p, ct.c_int
        self.native.argtypes = (
            ptr,
            number,
            ptr,
            number,
            ptr,
            number,
            ptr,
            ptr,
            number,
            ptr,
            number,
            ptr,
            ct.c_double,
            number,
            ptr,
            ptr,
            ct.POINTER(Stats),
        )
        self.calls = []

    def score_grid(
        self, acquisition, original, samples, template, rate, frequencies, symbols, epochs
    ):
        started = process_time_ns()
        wave, exact = (np.ascontiguousarray(v, dtype=np.complex128) for v in (samples, template))
        if (
            wave.ndim != 1
            or exact.ndim != 1
            or not np.isfinite(rate)
            or rate <= 0
            or wave.size > 200000
            or not 0 < epochs <= 13333
        ):
            return original(samples, template, rate, frequencies, symbols, epochs)
        bins = np.asarray(frequencies, dtype=np.float64)
        duration = acquisition.OFDM_SYMBOL_DURATION_S
        starts = np.array([round(s * rate * duration) for s in symbols], dtype=np.int32)
        stops = np.array([round((s + 1) * rate * duration) for s in symbols], dtype=np.int32)
        offsets, frame = [], 0
        period = rate / acquisition.FRAME_RATE_HZ
        while (offset := round(frame * period)) < wave.size:
            offsets.append(offset)
            frame += 1
        offsets = np.array(offsets, dtype=np.int32)
        prefix = np.ascontiguousarray(acquisition._power_prefix(samples), dtype=np.float64)
        support = np.empty(epochs, dtype=np.int32)
        grid = np.empty((len(bins), epochs), dtype=np.float64)
        stats = Stats()
        native_started = process_time_ns()
        status = self.native(
            wave.ctypes.data,
            wave.size,
            exact.ctypes.data,
            exact.size,
            bins.ctypes.data,
            bins.size,
            starts.ctypes.data,
            stops.ctypes.data,
            starts.size,
            offsets.ctypes.data,
            offsets.size,
            prefix.ctypes.data,
            rate,
            epochs,
            grid.ctypes.data,
            support.ctypes.data,
            ct.byref(stats),
        )
        clock = process_time_ns()
        self.calls.append(
            dict(
                applied=status == 0,
                anchors=len(symbols),
                frames=len(offsets),
                cfo_lanes=len(bins),
                epochs=epochs,
                config_cpu_ns=native_started - started,
                native_cpu_ns=clock - native_started,
                grid_bytes=grid.nbytes,
                support_bytes=support.nbytes,
                **{name: getattr(stats, name) for name, _ in stats._fields_},
            )
        )
        if status:
            return original(samples, template, rate, frequencies, symbols, epochs)
        return tuple(grid)

    @contextmanager
    def route(self, acquisition, screen=None):
        """Patch only coarse scoring and restore the release adapter on exit."""
        with _PORT, ExitStack() as scope:
            original = acquisition._folded_anchor_score_grid

            def grid(*args):
                return self.score_grid(acquisition, original, *args)

            scope.enter_context(patch.object(acquisition, "_folded_anchor_score_grid", grid))
            if screen is not None:
                stock_screen = screen.acquire

                def screened(module, args, residuals, count, epoch_sep, cfo_sep, *, observer=None):
                    if module is not acquisition:
                        return stock_screen(
                            module, args, residuals, count, epoch_sep, cfo_sep, observer=observer
                        )
                    rows = grid(*args)
                    retained = acquisition._retain_score_map_peaks(
                        residuals, rows, count, epoch_sep, cfo_sep, args[-1]
                    )
                    if observer is not None:
                        observer(dict(path="fft_full_grid", columns=args[-1]))
                    return rows, retained

                scope.enter_context(patch.object(screen, "acquire", screened))
            yield self
