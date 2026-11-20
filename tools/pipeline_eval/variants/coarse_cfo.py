"""Interpolate missing coarse CFO dots before taking anchor magnitudes."""

import ctypes as ct
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from . import capture_batched_fft, capture_fft, fft_length_plan, original_kernel
from .wide_regional import replace

HEADER = Path(__file__).with_name("coarse_cfo_fold.h")
DIRECT = Path(__file__).with_name("coarse_cfo_repair.c")
RATE = 10_000_000
STEP = 80_000
TAPS = 44
LENGTH = 256
KEEP = np.arange(0, 21, 2)
ODD = np.arange(1, 20, 2)
ORDERS = (6, 11)
NUMERICAL_SLACK = 2e-6


def neighbors(terms):
    dist = abs(KEEP[None, :] - ODD[:, None])
    return np.sort(np.argsort(dist, axis=1, kind="stable")[:, :terms], axis=1)


def weights(references, terms):
    """Fit real weights to the phase-centered FIRs, weighted by each anchor's taps."""
    relative = np.arange(TAPS) - (TAPS - 1) / 2
    tone = np.exp(-2j * np.pi * STEP / RATE * np.arange(21)[:, None] * relative)
    amplitudes = np.abs(references)
    amplitudes /= np.linalg.norm(amplitudes, axis=1, keepdims=True)
    rows = np.empty((len(references), len(ODD), terms), dtype=np.float32)
    defects = np.empty(rows.shape[:2])
    for lane, ids in enumerate(neighbors(terms)):
        basis = tone[KEEP[ids]].T
        target = tone[ODD[lane]]
        for s, amplitude in enumerate(amplitudes):
            weighted = basis * amplitude[:, None]
            wanted = target * amplitude
            model = np.vstack((weighted.real, weighted.imag))
            truth = np.r_[wanted.real, wanted.imag]
            rows[s, lane] = np.linalg.lstsq(model, truth, rcond=None)[0]
            defects[s, lane] = np.linalg.norm(model @ rows[s, lane].astype(float) - truth)
    return rows, defects


def _c_array(items):
    return str(items).replace("[", "{").replace("]", "}")


def build(work, terms):
    if terms not in ORDERS:
        raise ValueError("unsupported reconstruction order")
    # The wisdom header operates on the original scientific 21-row geometry.
    # Prepare that ABI first and then reduce its executed 21-lane plan to eleven.
    seed = work.with_name(work.name + "-seed")
    seed.mkdir()
    (seed / "capture_fft.c").write_bytes(capture_fft.SOURCE.read_bytes())
    canonical = capture_fft.SOURCE.with_name("folded_bank.c")
    folded = original_kernel.kernel(capture_batched_fft.fft_bank(canonical.read_text()))
    folded = replace(folded, "fft_length = 512", "fft_length = 256")
    (seed / "folded_bank.c").write_text(folded)
    with patch.object(fft_length_plan, "COUNT", len(KEEP)):
        wisdom = fft_length_plan.measure(LENGTH)
    fft_length_plan.build(work, seed, wisdom)
    header_path = work / original_kernel.HEADER.name
    header = header_path.read_text()
    for before, after in (
        ("batch=(size_t)nf*fft_length", "batch=(size_t)11*fft_length"),
        ("dft(1,&length,nf,", "dft(1,&length,11,"),
        (
            "for(int f=0;f<nf;++f) {\n            memset",
            "for(int f=0;f<nf;f+=2) {\n            memset",
        ),
        ("((size_t)s*nf+f)*fft_length", "((size_t)s*11+f/2)*fft_length"),
        ("*built=ns*nf;", "*built=ns*11;"),
    ):
        header = replace(header, before, after)
    header_path.write_text(header)
    phase = np.exp(2j * np.pi * STEP * (KEEP - 10) / RATE * ((TAPS - 1) / 2))
    port = replace(
        (work / "capture_fft.c").read_text(),
        "static _Thread_local CaptureFftStats *measurement;",
        "static _Thread_local CaptureFftStats *measurement;\n"
        "static _Thread_local const float *mix;",
    )
    port = replace(
        port, "CaptureFftStats *stats\n)", "CaptureFftStats *stats, const float *weights\n)"
    )
    port = replace(port, "    measurement = stats;", "    measurement = stats;\n    mix = weights;")
    port = replace(port, "    measurement = NULL;", "    measurement = NULL;\n    mix = NULL;")
    (work / "capture_fft.c").write_text(port)
    folded = replace(
        folded,
        '#include "original_kernel_cache.h"',
        '#include "original_kernel_cache.h"\n'
        f"#define COARSE_TERMS {terms}\n"
        f"#define COARSE_PHASE_REAL {_c_array(phase.real.tolist())}\n"
        f"#define COARSE_PHASE_IMAG {_c_array(phase.imag.tolist())}\n"
        f"#define COARSE_EVEN_INDEX {_c_array(neighbors(terms).tolist())}\n"
        '#include "coarse_cfo_fold.h"',
    )
    forced = folded.index("    for (int s = 0; s < ns; ++s)")
    folded = (
        folded[:forced]
        + "    if (nf != 21 || !mix) { k->invalid_geometry=1; return; }\n"
        + folded[forced:]
    )
    start = folded.index("            for (int f", folded.index("const double template_weight"))
    stop = folded.index("            fftwf_execute(inverse);", start)
    transforms = folded[start:stop].replace("f < nf", "f < 11").replace("s * nf", "s * 11")
    end = folded.index("\n        }\n    }\n    for (int f", stop)
    folded = (
        folded[:start]
        + transforms
        + """            fftwf_execute(inverse);
            inverse_calls += 11;
            fold_cfo(output, mix + (size_t)s * 10 * COARSE_TERMS, k->scores,
                     ne, taps[s], limit, norm, template_weight, start, stop, base, count);"""
        + folded[end:]
    )
    folded = folded.replace("(size_t)ns*nf*fft_length", "(size_t)ns*11*fft_length")
    folded = folded.replace("(2 + 2*(size_t)nf)", "(2 + 2*(size_t)11)")
    (work / "folded_bank.c").write_text(folded)
    (work / HEADER.name).write_bytes(HEADER.read_bytes())
    path = work / "coarse_cfo.so"
    command = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        str(work / "capture_fft.c"),
        str(DIRECT),
        "-lfftw3f",
        "-lm",
        "-o",
        str(path),
    ]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(work)}, timeout=30, check=True)
    return path, command


def interval_neighbors(mask):
    result = mask.copy()
    result[:, :-1] |= mask[:, 1:]
    result[:, 1:] |= mask[:, :-1]
    return result


def complete_local_peaks(mask):
    interior = mask.copy()
    interior[:, :-1] &= mask[:, 1:]
    interior[:, 1:] &= mask[:, :-1]
    return interior


def exact_selection(votes, exact, seen, bounds, chosen):
    """Check a sufficient top-N condition when the input intervals enclose a grid."""
    unknown = ~complete_local_peaks(seen)
    upper = np.where(seen, exact, votes + bounds)
    return bool(
        chosen and np.min([v[0] for v in chosen]) > np.max(upper, where=unknown, initial=-np.inf)
    )


class Interpolated(original_kernel.PersistentGrid):
    def __init__(self, path, terms, control, *, repair=None):
        super().__init__(path)
        self.control = control
        self.terms = terms
        self.repair = repair
        self.history = {}
        self._context = None
        native = self.native
        native.argtypes += (ct.c_void_p,)
        self.native = lambda *args: native(*args, self._context[4].ctypes.data)
        self._direct = self.library.coarse_cfo_cells
        pointer, number = ct.c_void_p, ct.c_int
        self._direct.argtypes = (
            pointer,
            pointer,
            pointer,
            pointer,
            pointer,
            number,
            number,
            number,
            pointer,
            number,
            number,
            pointer,
        )
        self._direct.restype = None

    def score_grid(self, acquisition, original, wave, template, rate, bins, symbols, epochs):
        args = (wave, template, rate, bins, symbols, epochs)
        self._context = None
        if (
            rate != RATE
            or wave.shape != (200_000,)
            or epochs != 13_333
            or len(bins) != 21
            or not np.all(np.diff(bins) == STEP)
            or len(symbols) not in (12, 22)
        ):
            exact = self.control.score_grid(acquisition, original, *args)
            self.calls.append(dict(self.control.calls[-1], proposal=False))
            return exact
        begin = process_time_ns()
        anchors = np.array(
            [round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols], dtype=np.int32
        )
        references = np.ascontiguousarray(template[anchors[:, None] + np.arange(TAPS)])
        key = tuple(symbols), references.tobytes()
        if key not in self.history:
            if len(self.history) == 4:
                self.history.pop(next(iter(self.history)))
            self.history[key] = weights(references, self.terms)
        mix, defects = self.history[key]
        self._context = args, anchors, references, defects, mix, acquisition, original
        scores = super().score_grid(acquisition, original, *args)
        self.calls[-1].update(
            proposal=True,
            combined_cpu_ns=process_time_ns() - begin,
            ideal_maximum_defect=float(defects.max()),
            order=self.terms,
        )
        return scores

    def _inputs(self):
        args, anchors, refs, defects, _, acquisition, _ = self._context
        wave, _template, rate, bins, _, epochs = args
        frames = np.rint(np.arange(15) * rate / acquisition.FRAME_RATE_HZ).astype(np.int32)
        valid = len(wave) - TAPS + 1
        counts = np.clip(valid - frames[None, :] - anchors[:, None], 0, epochs)
        support = np.zeros(epochs + 1)
        support[0] = counts.size
        np.subtract.at(support, counts.ravel(), 1)
        support = np.cumsum(support[:-1])
        bounds = np.zeros((21, epochs + 1))
        bounds[1::2, 0] = defects.sum(axis=0) * len(frames)
        for anchor, geometry in enumerate(counts):
            for stop in geometry:
                bounds[1::2, stop] -= defects[anchor]
        averages = np.cumsum(bounds[:, :-1], axis=1) / support
        return wave, rate, bins, refs, anchors, frames, averages

    def restore(self, args, votes, retain):
        start = process_time_ns()
        residuals, _, count, epoch_sep, cfo_sep, epochs = args
        wave, rate, bins, templates, anchors, frames, ideal = self._inputs()
        bounds = ideal + NUMERICAL_SLACK
        proposal = np.zeros_like(votes, dtype=bool)
        nominations = retain(residuals, tuple(votes), 32, epoch_sep, cfo_sep, epochs)
        for _, epoch, frequency in nominations:
            if votes[residuals.index(frequency), epoch] > 0:
                proposal[residuals.index(frequency), max(0, epoch - 4) : epoch + 5] = True
        if not proposal.any():
            return retain(*args)
        rotation = np.exp(-2j * np.pi / rate * np.outer(bins, np.arange(TAPS)))
        refs = templates.conj() / np.linalg.norm(templates, axis=1, keepdims=True)
        coefficients = np.ascontiguousarray(rotation[:, None] * refs[None, :])
        prefix = self._context[5]._power_prefix(wave)
        energy = prefix[TAPS:] - prefix[:-TAPS]
        energy = np.sqrt(np.maximum(energy, 0))
        inverse = np.divide(1, energy, out=np.zeros_like(energy), where=energy > 0)
        wave = np.ascontiguousarray(wave, dtype=np.complex128)
        exact = np.full_like(votes, np.nan)
        seen = np.zeros_like(votes, dtype=bool)

        def compute(mask):
            cells = np.flatnonzero(mask & ~seen).astype(np.int32)
            if len(cells):
                self._direct(
                    wave.ctypes.data,
                    inverse.ctypes.data,
                    coefficients.ctypes.data,
                    anchors.ctypes.data,
                    frames.ctypes.data,
                    len(anchors),
                    len(frames),
                    len(wave),
                    cells.ctypes.data,
                    len(cells),
                    epochs,
                    exact.ctypes.data,
                )
                seen[:] |= mask

        compute(interval_neighbors(proposal))
        chosen = retain(residuals, tuple(exact), count, epoch_sep, cfo_sep, epochs)
        initial = int(seen.sum())
        cutoff = chosen[-1][0] if len(chosen) == count else -np.inf
        needed = votes + bounds >= cutoff
        missing = int(np.count_nonzero(interval_neighbors(needed) & ~seen))
        if self.repair == "bounded" and missing <= 512:
            compute(interval_neighbors(needed))
            chosen = retain(residuals, tuple(exact), count, epoch_sep, cfo_sep, epochs)
        passes = len(chosen) == count and exact_selection(votes, exact, seen, bounds, chosen)
        self.calls[-1].update(
            rescore_cpu_ns=process_time_ns() - start,
            first_cells=initial,
            revisited_cells=int(seen.sum()),
            interval_repair_cells=missing,
            interval_check=passes,
            fallback=False,
        )
        if self.repair == "bounded" and not passes:
            original_args, *_, acquisition, original = self._context
            fallback = self.control.score_grid(acquisition, original, *original_args)
            for a, b in zip(args[1], fallback, strict=True):
                a[:] = b
            self.calls[-1].update(fallback=True, rescore_cpu_ns=process_time_ns() - start)
            return retain(*args)
        for a, b in zip(args[1], exact, strict=True):
            a[:] = b
        return chosen

    @contextmanager
    def route(self, acquisition, screen=None):
        select = acquisition._retain_score_map_peaks

        def retain(*args):
            if self.repair is None or self._context is None:
                return select(*args)
            return self.restore(args, np.asarray(args[1]), select)

        with (
            super().route(acquisition, screen),
            patch.object(acquisition, "_retain_score_map_peaks", retain),
        ):
            try:
                yield self
            finally:
                self._context = None
