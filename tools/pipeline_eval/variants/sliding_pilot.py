"""Evaluate the capture-era coarse pilot family with rolling tone correlators."""

import ctypes as ct
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import process_time_ns

import numpy as np

from .capture_fft import FullGrid
from .refine_bank import EPOCHS, FRAME_BASE, RATE, SAMPLES, TAPS

SOURCE = Path(__file__).with_suffix(".c")
RETRY = tuple(range(2, 302, 14))
TILE = 1024
TONE_COUNT = 8
FLAGS = (
    "-std=c11",
    "-O3",
    "-march=native",
    "-mavx2",
    "-fopenmp-simd",
    "-ffp-contract=fast",
    "-fno-math-errno",
    "-fno-trapping-math",
    "-fPIC",
    "-shared",
)


class Complex(ct.Structure):
    _fields_ = (("r", ct.c_double), ("i", ct.c_double))


def drift(library, values, absolute_cfo_hz):
    port = library.sliding_pilot_long
    port.argtypes = (ct.c_void_p, ct.c_int, ct.c_void_p, Complex, Complex, ct.c_void_p)
    port.restype = None
    samples = np.ascontiguousarray(values, dtype=np.complex128)
    positions = np.linspace(0, len(values) - TAPS, 257, dtype=int)
    samples_to_check = samples[positions[:, None] + np.arange(TAPS)]
    denominator = np.linalg.norm(samples_to_check, axis=1) * np.sqrt(TAPS)
    largest, relative, end = 0.0, 0.0, 0.0
    tone_values = family("lower", RETRY).tones_hz
    out = np.empty(len(samples) - TAPS + 1, dtype=np.complex128)
    for tone in tone_values:
        phase = -2j * np.pi * (absolute_cfo_hz + tone) / RATE
        basis = np.exp(phase * np.arange(TAPS))
        undo, tail = (np.exp(k * phase) for k in (-1, TAPS - 1))
        port(
            samples.ctypes.data,
            len(samples),
            basis.ctypes.data,
            Complex(undo.real, undo.imag),
            Complex(tail.real, tail.imag),
            out.ctypes.data,
        )
        error = abs(out[positions] - np.sum(samples_to_check * basis, axis=1))
        scaled = np.divide(error, denominator, out=np.zeros_like(error), where=denominator > 0)
        largest, relative, end = (
            max(largest, float(error.max())),
            max(relative, float(scaled.max())),
            max(end, float(scaled[-1])),
        )
    return dict(
        rebased=False,
        offsets=len(positions),
        span=len(out),
        absolute_max=largest,
        normalized_max=relative,
        normalized_at_end_max=end,
    )


@dataclass(frozen=True)
class PilotFamily:
    starts: np.ndarray
    states: np.ndarray
    tones_hz: np.ndarray
    phases: np.ndarray
    seam: np.ndarray
    inv_energy: np.ndarray
    support: np.ndarray
    tap_error: float
    relative_error: float


def build(work):
    output = work / "sliding_pilot.so"
    cmd = ["cc", *FLAGS, str(SOURCE), "-lm", "-o", str(output)]
    subprocess.run(cmd, check=True, env=os.environ | {"TMPDIR": str(work)})
    return output, cmd


@lru_cache(maxsize=4)
def template_for(edge):
    from leo.analysis.starlink import templates

    return templates.qin_edge_pilot_frame(RATE, edge).astype(np.complex128)


@lru_cache(maxsize=4)
def family(edge, symbols):
    from leo.analysis.starlink import templates

    starts = TAPS * np.asarray(symbols, dtype=np.int32)
    refs = template_for(edge)[starts[:, None] + np.arange(TAPS)]
    states = np.ascontiguousarray(
        templates.qin_edge_pilot_states(edge)[list(np.asarray(symbols) - 2)], dtype=np.uint8
    )
    tones = templates.edge_frequencies_hz(edge)
    q0 = np.complex64(np.exp(0.25j * np.pi))
    coeff = q0 * (1j**states)
    scale = np.exp(-2j * np.pi * tones * templates.CYCLIC_PREFIX_DURATION_S) / np.sqrt(TONE_COUNT)
    basis = scale[None, :] * np.exp(2j * np.pi * np.arange(TAPS)[:, None] * tones[None, :] / RATE)
    delta = refs - coeff @ basis.T
    correction = abs(delta[:, 0]) > 1e-7
    seam = np.where(correction, delta[:, 0].conj(), 0)
    delta[correction, 0] = 0
    energy = np.linalg.norm(refs, axis=1)
    cuts = np.minimum(EPOCHS, SAMPLES - TAPS + 1 - starts[:, None] - FRAME_BASE)
    support = np.sum(np.arange(EPOCHS)[None, None, :] < cuts[:, :, None], axis=(0, 1)).astype(
        np.int32
    )
    return PilotFamily(
        starts,
        states,
        tones,
        (scale * q0).conj(),
        seam,
        1 / energy,
        support,
        float(np.max(abs(delta))),
        float(np.max(np.linalg.norm(delta, axis=1) / energy)),
    )


@lru_cache(maxsize=16)
def rotations(frequencies, tones):
    phase = (-2j * np.pi / RATE) * (np.asarray(frequencies)[:, None] + np.asarray(tones))
    return (
        np.exp(-phase),
        np.exp((TAPS - 1) * phase),
        np.exp(np.arange(TAPS)[None, :, None] * phase[:, None, :]),
    )


class SlidingPilotGrid(FullGrid):
    def __init__(self, library, *, use_float=False, use_pairs=False):
        self.library = ct.CDLL(str(library))
        self.use_float = use_float
        self.use_pairs = use_pairs
        self.native = self.library.sliding_pilot_grid
        p, n = ct.c_void_p, ct.c_int
        self.native.argtypes = (p, p, p, n, n, p, n, p, n, p, p, p, p, p, p, p, p, n, n, p)
        self.native.restype = None
        self.calls = []

    def score_grid(
        self, acquisition, original, samples, template, rate, frequencies, symbols, epochs
    ):
        if not (
            rate == RATE
            and epochs == EPOCHS
            and samples.shape == (SAMPLES,)
            and template.shape == (EPOCHS,)
            and len(frequencies) == 21
            and symbols in (acquisition.DEFAULT_ANCHOR_SYMBOLS, RETRY)
            and np.isfinite(frequencies).all()
        ):
            self.calls.append(dict(applied=False, reason="unsupported_geometry"))
            return original(samples, template, rate, frequencies, symbols, epochs)
        edge = next(
            (e for e in ("lower", "upper") if np.array_equal(template, template_for(e))), None
        )
        if edge is None:
            self.calls.append(dict(applied=False, reason="unrecognized_pilot_frame"))
            return original(samples, template, rate, frequencies, symbols, epochs)
        setup = process_time_ns()
        model = family(edge, symbols)
        inverse, end, seeds = rotations(tuple(frequencies), tuple(model.tones_hz))
        frames = FRAME_BASE.astype(np.int32)
        limit = SAMPLES - TAPS + 1
        raw = np.zeros((2, SAMPLES + 1), dtype=np.float32)
        raw[0, :-1], raw[1, :-1] = samples.real, samples.imag
        prefix = acquisition._power_prefix(samples)
        energy = prefix[TAPS:] - prefix[:-TAPS]
        norm = np.divide(1, np.sqrt(np.maximum(energy, 0)), out=np.zeros(limit), where=energy > 0)
        norm = norm.astype(np.float32)
        grid = np.empty((len(frequencies), epochs), dtype=np.float64)
        start = process_time_ns()

        def pointer(array):
            return array.ctypes.data

        self.native(
            pointer(raw[0]),
            pointer(raw[1]),
            pointer(norm),
            limit,
            epochs,
            pointer(model.starts),
            len(symbols),
            pointer(frames),
            len(frames),
            pointer(model.states),
            pointer(model.seam),
            pointer(model.inv_energy),
            pointer(model.support),
            pointer(inverse),
            pointer(end),
            pointer(model.phases),
            pointer(seeds),
            len(frequencies),
            int(self.use_float) + 2 * int(self.use_pairs),
            pointer(grid),
        )
        ended = process_time_ns()
        stride = 128 if self.use_float else TILE
        self.calls.append(
            dict(
                applied=True,
                edge=edge,
                anchors=len(symbols),
                rows=len(frequencies),
                config_cpu_ns=start - setup,
                native_cpu_ns=ended - start,
                inverse_ffts=0,
                tone_updates=limit * len(frequencies) * TONE_COUNT,
                anchor_magnitudes=int(model.support.sum()) * len(frequencies),
                rebases=((limit + stride - 1) // stride) * len(frequencies) * TONE_COUNT,
                grid_bytes=grid.nbytes,
                buffer_bytes=raw.nbytes
                + norm.nbytes
                + TILE * TONE_COUNT * 16
                + TILE * 128 * int(self.use_pairs),
            )
        )
        return tuple(grid)
