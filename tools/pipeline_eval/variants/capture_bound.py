"""Four-block Cauchy preflight and a separate per-tap magnitude audit."""

import ctypes as ct
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

SOURCE = Path(__file__).with_suffix(".c")


def build(output):
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-ffp-contract=off",
            "-fno-math-errno",
            "-Werror",
            "-Wall",
            "-Wextra",
            "-shared",
            "-fPIC",
            str(SOURCE),
            "-lm",
            "-o",
            str(output),
        ],
        env=os.environ | {"TMPDIR": str(output.parent)},
        check=True,
        timeout=15,
    )
    return output


class Envelope:
    def __init__(self, library):
        self.call = ct.CDLL(str(library.resolve())).leo_capture_bound
        p, n = ct.c_void_p, ct.c_size_t
        self.call.argtypes = [
            p,
            n,
            p,
            n,
            p,
            p,
            n,
            p,
            n,
            n,
            ct.c_int,
            p,
            ct.POINTER(ct.c_uint64),
            ct.POINTER(ct.c_uint64),
        ]
        self.call.restype = ct.c_int
        self.rows = []

    def evaluate(self, acquisition, args, *, per_tap=False):
        values, template, rate, frequencies, symbols, epochs = args
        if (
            rate != 10_000_000
            or values.shape != (200_000,)
            or not 1 <= epochs <= 13334
            or np.ndim(template) != 1
            or not 1 <= len(symbols) <= 22
            or not 1 <= len(frequencies) <= 21
        ):
            return None
        values = np.ascontiguousarray(values, dtype=np.complex128)
        template = np.ascontiguousarray(template, dtype=np.complex128)
        start = np.array(
            [round(x * rate * acquisition.OFDM_SYMBOL_DURATION_S) for x in symbols], dtype=np.intp
        )
        end = np.array(
            [round((x + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S) for x in symbols],
            dtype=np.intp,
        )
        period = rate / acquisition.FRAME_RATE_HZ
        offsets = np.array(
            [round(f * period) for f in range(16) if round(f * period) < values.size], dtype=np.intp
        )
        output = np.empty(epochs, dtype=np.float64)
        support, work = ct.c_uint64(), ct.c_uint64()
        initial = process_time_ns()
        status = self.call(
            values.ctypes.data,
            values.size,
            template.ctypes.data,
            template.size,
            start.ctypes.data,
            end.ctypes.data,
            start.size,
            offsets.ctypes.data,
            offsets.size,
            epochs,
            per_tap,
            output.ctypes.data,
            ct.byref(support),
            ct.byref(work),
        )
        elapsed = process_time_ns() - initial
        if status:
            return None
        return output, dict(cpu_ns=elapsed, support_terms=support.value, bound_terms=work.value)

    @contextmanager
    def activate(self, acquisition, screen=None):
        port = "_folded_anchor_score_grid" if screen is None else "acquire"
        module = acquisition if screen is None else screen
        original = getattr(module, port)

        def classify(args):
            values, _, rate, frequencies, symbols, epochs = args
            # Exactly zero IQ, with the same geometry as the actual scanner.
            # This alone determines the bypass; audit envelopes never set it.
            silent = (
                rate == 10_000_000
                and values.shape == (200_000,)
                and bool(symbols)
                and epochs == 13333
                and 1 <= len(frequencies) <= 21
                and not np.any(values)
            )
            evaluated = None if silent else self.evaluate(acquisition, args)
            row = dict(
                symbols=len(symbols),
                frequencies=len(frequencies),
                epochs=epochs,
                route="exact_silence" if silent else "original_full",
                preflight=evaluated[1] if evaluated is not None else None,
                omitted_cells=epochs * len(frequencies) if silent else 0,
            )
            self.rows.append(row)
            return silent

        def empty(args):
            return tuple(np.zeros(args[-1], dtype=float) for _ in args[3])

        def dense(*args):
            return empty(args) if classify(args) else original(*args)

        def screened(
            module, args, residuals, keep, epoch_separation, cfo_separation, *, observer=None
        ):
            if not classify(args):
                return original(
                    module,
                    args,
                    residuals,
                    keep,
                    epoch_separation,
                    cfo_separation,
                    observer=observer,
                )
            grid = empty(args)
            selected = module._retain_score_map_peaks(
                residuals, grid, keep, epoch_separation, cfo_separation, args[-1]
            )
            if observer is not None:
                observer(dict(path="exact_silence", columns=0))
            return grid, selected

        with patch.object(module, port, dense if screen is None else screened):
            yield self
