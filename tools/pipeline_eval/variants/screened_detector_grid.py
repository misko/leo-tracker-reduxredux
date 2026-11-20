"""Opt-in AVX-VNNI screen, using two epochs per template-coefficient load."""

import ctypes
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

SOURCE = Path(__file__).with_suffix(".c")


def build(output):
    subprocess.run(
        [
            "cc",
            "-pipe",
            "-O3",
            "-mavxvnni",
            "-mavx2",
            "-mfma",
            "-fPIC",
            "-shared",
            "-Werror",
            "-Wall",
            "-Wextra",
            str(SOURCE),
            "-o",
            str(output),
            "-lm",
        ],
        env={**os.environ, "TMPDIR": str(output.parent.resolve())},
        check=True,
    )
    return output


class Grid:
    def __init__(self, library):
        features = frozenset(
            Path("/proc/cpuinfo").read_text().split("flags", 1)[-1].split("\n")[0].split()
        )
        if not {"avx_vnni", "avx2", "fma"} <= features:
            raise RuntimeError("integer screen requires supported host AVX-VNNI")
        self.call = ctypes.CDLL(str(library.resolve())).screened_detector_grid
        p, n = ctypes.c_void_p, ctypes.c_size_t
        self.call.argtypes = [p, n, p, n, p, n, p, p, n, p, n, p, ctypes.c_double, n, p]
        self.call.restype = ctypes.c_int
        self.cells = 0
        self.calls = 0
        self.fallbacks = 0

    def _tile(self, values, frame, frequencies, starts, stops, offsets, prefix, rate, epochs):
        grid = np.empty((len(frequencies), epochs), dtype=np.float64)

        def ptr(array):
            return array.ctypes.data

        failed = self.call(
            ptr(values),
            values.size,
            ptr(frame),
            frame.size,
            ptr(frequencies),
            frequencies.size,
            ptr(starts),
            ptr(stops),
            starts.size,
            ptr(offsets),
            offsets.size,
            ptr(prefix),
            rate,
            epochs,
            ptr(grid),
        )
        if failed:
            return None
        self.cells += grid.size
        return grid

    @contextmanager
    def route(self, screen=None):
        if screen is None:
            from leo.analysis.starlink import coarse_screen as screen
        from leo.analysis.starlink import _screen_native

        if _screen_native.SCREEN_KIND != "integer_vnni":
            raise RuntimeError("expected the installed integer-VNNI screen")
        original = screen.screen_grid

        def route(native, acquisition, values, template, rate, frequencies, symbols, epochs):
            args = (native, acquisition, values, template, rate, frequencies, symbols, epochs)
            self.calls += 1
            if not (
                rate == 10_000_000
                and 1 <= epochs <= 13_334
                and 1 <= len(symbols) <= 22
                and 1 <= len(frequencies) <= 72
                and 1 <= len(values) <= 200_000
                and 1 <= len(template) <= 13_334
            ):
                self.fallbacks += 1
                return original(*args)
            starts = np.array(
                [round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols],
                dtype=np.intp,
            )
            stops = np.array(
                [round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols],
                dtype=np.intp,
            )
            period = rate / acquisition.FRAME_RATE_HZ
            offsets = np.array(
                [round(f * period) for f in range(16) if round(f * period) < len(values)],
                dtype=np.intp,
            )
            values = np.ascontiguousarray(values, dtype=np.complex128)
            template = np.ascontiguousarray(template, dtype=np.complex128)
            frequencies = np.ascontiguousarray(frequencies, dtype=np.float64)
            prefix = acquisition._power_prefix(values)
            rows = []
            for start in range(0, len(frequencies), 24):
                tile = self._tile(
                    values,
                    template,
                    frequencies[start : start + 24],
                    starts,
                    stops,
                    offsets,
                    prefix,
                    rate,
                    epochs,
                )
                if tile is None:
                    self.fallbacks += 1
                    return original(*args)
                rows.extend(tile)
            return tuple(rows)

        with patch.object(screen, "screen_grid", route):
            yield self
