"""Transpose fractional GLRT interpolation and verify the decision intervals."""

import ctypes
import math
import subprocess
from pathlib import Path

import numpy as np

from .refine_bank import (
    EPOCHS,
    FRAME_BASE,
    GLRT_SIZE,
    LANCZOS,
    OFFSET,
    RATE,
    RELATIVE,
    SAMPLES,
    STOP,
    SYMBOL_STARTS,
    TAPS,
)

SOURCE = Path(__file__).with_suffix(".c")
FLAGS = ("-std=c11", "-O3", "-march=native", "-fopenmp-simd", "-shared", "-fPIC")
GATE = 0.025
UNIT = np.finfo(float).eps / 2
FRACTION_ERROR = np.spacing(float(SAMPLES)) / 2 + 4 * UNIT
KERNEL_TAPS = TAPS + len(LANCZOS) - 1


def compile_bank(path):
    subprocess.run(["cc", *FLAGS, str(SOURCE), "-o", str(path)], check=True)


def spectra(correlations):
    short = np.fft.fft(correlations, n=128, axis=-1)
    ac = np.fft.ifft(np.sum(np.abs(short) ** 2, axis=1), axis=-1)
    packed = np.zeros((2, GLRT_SIZE), dtype=np.complex128)
    packed[:, :64], packed[:, -63:] = ac[:, :64], ac[:, -63:]
    spectrum = np.fft.fft(packed, axis=-1).real
    frame_max = np.sum(np.abs(correlations), axis=-1)
    denominator = np.sum(frame_max ** 2, axis=1)
    return spectrum, frame_max, denominator


def rejection(spectrum, bound):
    exact, control = (float(np.max(row)) for row in spectrum)
    winner = int(np.argmax(spectrum[0]))
    runner = float(np.max(spectrum[0], where=np.arange(GLRT_SIZE) != winner, initial=-np.inf))
    if exact - runner <= 2 * bound[0]:
        return "unresolved_frequency_bin", winner
    if exact - control + np.sum(bound) >= GATE:
        return "positive_or_gate_overlap", winner
    return None, winner


class Adjoint:
    def __init__(self, library, fused):
        func = ctypes.CDLL(str(Path(library).resolve())).paired_adjoint
        z = np.ctypeslib.ndpointer(dtype=np.complex128, flags="C_CONTIGUOUS")
        i = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
        func.argtypes = [z, z, i, ctypes.c_int, z]
        func.restype = None
        self.dot = func
        self.fused = fused
        self.reset()

    def reset(self):
        self.data = None
        self.maximum = None
        self.receipts = []
        self.inputs = {}

    def score(self, samples, sample_rate_hz, *, epoch_sample, acquired_cfo_hz,
              edge="lower", glrt_size=GLRT_SIZE, fractional_epoch_offset_samples=0.0):
        offset = fractional_epoch_offset_samples

        def fallback(reason):
            self.receipts.append(dict(fallback=reason))
            return self.fused.fractional(
                samples, sample_rate_hz, epoch_sample=epoch_sample,
                acquired_cfo_hz=acquired_cfo_hz, edge=edge, glrt_size=glrt_size,
                fractional_epoch_offset_samples=offset,
            )

        if not (
            self.fused._supported(samples, sample_rate_hz, glrt_size)
            and isinstance(epoch_sample, (int, np.integer)) and 0 <= epoch_sample < EPOCHS
            and np.isfinite(acquired_cfo_hz) and abs(acquired_cfo_hz) <= RATE / 2
            and np.isfinite(offset) and abs(offset) <= 2.5 and abs(offset - round(offset)) > 2e-10
        ):
            return fallback("unsupported_geometry")
        if self.data is not samples:
            self.data = samples
            self.maximum = float(np.max(np.abs(samples)))
        if not np.isfinite(self.maximum):
            return fallback("unsupported_samples")

        frames = FRAME_BASE + epoch_sample
        producer = self.fused.producer
        left, right = producer.fractional_take_bounds(offset)
        valid = (frames + OFFSET + offset >= left) & (frames + STOP - 1 + offset < SAMPLES - right)
        invalid = np.flatnonzero(~valid)
        if invalid.size:
            frames = frames[:invalid[0]]
        if not len(frames):
            return fallback("no_supported_frame")
        if edge not in self.inputs:
            pilot = np.stack(self.fused._templates(edge)).reshape(2, 64, TAPS)
            self.inputs[edge] = pilot, np.sum(np.abs(pilot), axis=(1, 2))
        pilot, pilot_norm = self.inputs[edge]

        delta = offset - math.floor(offset) - LANCZOS
        weights = np.sinc(delta) * np.sinc(delta / 8)
        normalizer = float(np.sum(weights))
        unnormalized_error = len(weights) * (math.pi / 2) * (1 + 1 / 8) * FRACTION_ERROR
        if normalizer <= unnormalized_error:
            return fallback("unresolved_weight_normalizer")
        weights /= normalizer
        phase = np.exp(-2j * np.pi * acquired_cfo_hz * RELATIVE / RATE).reshape(64, TAPS)
        transfer = np.fft.fft(weights, n=64)
        transformed = np.fft.fft(pilot * phase, n=64, axis=-1)
        references = np.ascontiguousarray(np.fft.ifft(transformed * transfer)[..., :KERNEL_TAPS])
        starts = (frames + OFFSET + math.floor(offset) + LANCZOS[0]).astype(np.int32)
        out = np.empty((2, len(frames), 64), dtype=np.complex128)
        self.dot(samples, references, starts, len(frames), out)
        spectrum, fmax, denominator = spectra(out)

        # sinc(t) = integral_0^1 cos(pi*t*u) du, so |sinc'| <= pi/2.
        weight_l1 = float(np.sum(np.abs(weights)))
        weight_error = unnormalized_error * (1 + weight_l1) / (normalizer - unnormalized_error)
        phase_span = 2 * math.pi * abs(acquired_cfo_hz) * (SAMPLES + STOP) / RATE
        arithmetic = 16 * UNIT * (1 + phase_span) + 4096 * UNIT
        delta_frame = self.maximum * pilot_norm * (weight_error + weight_l1 * arithmetic)
        error_power = np.sum(delta_frame[:, None] * (2 * fmax + delta_frame[:, None]), axis=1)
        if np.any(denominator <= error_power):
            return fallback("unresolved_energy")
        bound = 2 * error_power / (denominator - error_power) + 4096 * UNIT
        normalized = spectrum / denominator[:, None]
        reason, winner = rejection(normalized, bound)
        if reason:
            return fallback(reason)
        times = (frames[:, None] + SYMBOL_STARTS + offset + (TAPS - 1) / 2) / RATE
        step = float(np.median(np.diff(times, axis=1)))
        frequency = np.fft.fftfreq(GLRT_SIZE, d=step)[winner]
        self.receipts.append(dict(
            fallback=None, bound=float(max(bound)), frames=len(frames),
            arrays_bytes=sum(a.nbytes for a in (references, transformed, out, normalized, times)),
        ))
        return self.fused._score(normalized[0, winner], np.max(normalized[1]),
                                 frequency, acquired_cfo_hz)
