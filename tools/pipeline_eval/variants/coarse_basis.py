"""Diagnostics for factoring the capture detector's complete coarse bank."""

import ctypes as ct
import subprocess
from pathlib import Path
from time import process_time_ns

import numpy as np

from .capture_fft import FLAGS

RANKS = (4, 8, 12, 16, 20, 24, 32, 44)
SOURCE = Path(__file__).with_suffix(".c")


def filters(template, starts, taps, frequencies, rate):
    """Return unit-norm correlation coefficients indexed by anchor, CFO and tap."""
    time = np.arange(taps)
    reference = np.asarray(template, dtype=np.complex128)[np.asarray(starts)[:, None] + time].conj()
    reference /= np.linalg.norm(reference, axis=1, keepdims=True)
    modulation = np.exp(-2j * np.pi * np.asarray(frequencies)[:, None] * time / rate)
    return reference[:, None] * modulation[None, :]


def decomposition(bank):
    """Factor the complex filters before discarding coefficient directions."""
    rows = bank.reshape(-1, bank.shape[-1])
    _, singular, basis = np.linalg.svd(rows, full_matrices=False)
    return rows @ basis.conj().T, singular, basis


def singular_diagnostics(bank):
    coefficient, singular, basis = decomposition(bank)
    rows = bank.reshape(-1, bank.shape[-1])
    error = {}
    for rank in RANKS:
        if rank <= len(singular):
            residual = np.linalg.norm(rows - coefficient[:, :rank] @ basis[:rank], axis=-1)
            rms = np.linalg.norm(residual) / np.sqrt(len(rows))
            error[rank] = {
                "rms_normalized_template_residual": float(rms),
                "max_normalized_template_residual": float(residual.max()),
            }
    return dict(singular_values=singular.tolist(), truncation=error)


def rotational_diagnostics(bank):
    """Find the closest distinct filters, allowing phase and conjugate time reversal."""
    rows = bank.reshape(-1, bank.shape[-1])
    anchors = bank[:, bank.shape[1] // 2]
    matches = {}
    for label, subset in (("anchors", anchors), ("full", rows)):
        largest = {}
        for kind, target in (("phase", subset), ("conjugate_reversal", subset[:, ::-1].conj())):
            overlap = abs(subset @ target.conj().T)
            np.fill_diagonal(overlap, -1)
            i, j = np.unravel_index(overlap.argmax(), overlap.shape)
            largest[kind] = dict(
                filters=[int(i), int(j)],
                overlap=float(overlap[i, j]),
                residual=float(np.sqrt(max(0, 2 - 2 * overlap[i, j]))),
                equal_pairs=int(np.count_nonzero(overlap > 1 - 1e-12) // 2),
            )
        matches[label] = largest
    return matches


class Projection:
    """Measure one warm low-rank bank with every eligible magnitude evaluated."""

    def __init__(self, library, bank, rank, starts, offsets, epochs):
        dll = ct.CDLL(str(library))
        self.fold = dll.coarse_basis_fold
        pointer, count = ct.c_void_p, ct.c_int
        self.fold.argtypes = (
            pointer,
            pointer,
            count,
            count,
            count,
            pointer,
            count,
            count,
            pointer,
            count,
            count,
            pointer,
        )
        self.fold.restype = None
        coefficient, _, basis = decomposition(bank)
        self.coefficient = np.ascontiguousarray(coefficient[:, :rank], dtype=np.complex64)
        self.basis = np.ascontiguousarray(basis[:rank, ::-1], dtype=np.complex64)
        self.starts = np.asarray(starts, dtype=np.int32)
        self.frames = np.asarray(offsets, dtype=np.int32)
        self.epochs = epochs
        self.lanes = bank.shape[1]
        self._spectrum = None

    def responses(self, samples, prefix):
        start = process_time_ns()
        rank, taps = self.basis.shape
        valid = len(samples) - taps + 1
        span = 512 - taps + 1
        origins = self.starts[:, None] + self.frames
        support = np.clip(valid - origins, 0, self.epochs).ravel()
        support = np.cumsum(np.bincount(support, minlength=self.epochs + 1)[:0:-1])[::-1]
        energy = np.maximum(prefix[taps:] - prefix[:-taps], 0)
        norm = np.divide(1.0, np.sqrt(energy), out=np.zeros(valid, np.float32), where=energy > 0)
        scores = np.zeros((self.lanes, self.epochs), np.float64)
        count = (valid + span - 1) // span
        wave = np.zeros(count * span + taps - 1, dtype=np.complex64)
        wave[: len(samples)] = samples
        if self._spectrum is None:
            self._spectrum = np.fft.fft(self.basis, n=512)
        fft_start = process_time_ns()
        blocks = np.lib.stride_tricks.sliding_window_view(wave, 512)[::span]
        forward = np.fft.fft(blocks)
        inverse = np.fft.ifft(self._spectrum[:, None] * forward)
        responses = np.ascontiguousarray(inverse[:, :, taps - 1 :]).reshape(rank, -1)
        reconstruct_start = process_time_ns()
        receipt = dict(
            rank=rank,
            forward_ffts=count,
            inverse_ffts=count * rank,
            reconstruction_complex_multiply_adds=self.lanes * len(self.starts) * valid * rank,
            supported_magnitudes=int(np.sum(support)) * self.lanes,
            prepare_ns=fft_start - start,
            fft_ns=reconstruct_start - fft_start,
        )
        return responses, norm, valid, scores, support, receipt

    def score(self, samples, prefix):
        responses, norm, valid, scores, support, receipt = self.responses(samples, prefix)
        reconstruct_start = process_time_ns()
        tile = 2048
        for first in range(0, valid, tile):
            dots = self.coefficient @ responses[:, first : min(first + tile, valid)]
            self.fold(
                dots.ctypes.data,
                norm.ctypes.data,
                dots.shape[1],
                first,
                valid,
                self.starts.ctypes.data,
                len(self.starts),
                self.lanes,
                self.frames.ctypes.data,
                len(self.frames),
                self.epochs,
                scores.ctypes.data,
            )
        np.divide(scores, support, out=scores, where=support != 0)
        receipt["reconstruct_fold_ns"] = process_time_ns() - reconstruct_start
        return scores, receipt


def compile_projection(library):
    command = [
        "cc",
        *FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        str(SOURCE),
        "-lm",
        "-o",
        str(library),
    ]
    subprocess.run(command, check=True, timeout=30)
    return command
