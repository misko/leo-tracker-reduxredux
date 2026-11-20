"""Shared sliding Qin tone products with an exact tiled selection guard."""

import ctypes
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import process_time

import numpy as np

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_states,
)

from . import anchor_grid
from .anchor_receiver import FLAGS

SOURCE = Path(__file__).with_suffix(".c")
BLOCK = 128
BASIS_TILE = 2048
TILE = 16
SUPPORTED_RATES = (2_500_000, 10_000_000)
ROTATIONS = np.array([1, -1j, -1, 1j])


def compile_filter(library):
    subprocess.run(["cc", *FLAGS, "-mavx2", str(SOURCE), "-lm", "-o", str(library)], check=True)


def _gamma(n, dtype):
    nu = n * np.finfo(dtype).eps / 2
    return nu / (1 - nu)


@lru_cache(maxsize=4)
def _edge_basis(edge, sample_rate, span):
    tones = edge_frequencies_hz(edge)
    time_s = np.arange(span) / sample_rate - CYCLIC_PREFIX_DURATION_S
    kernels = np.exp(-2j * np.pi * tones[:, None] * time_s) * np.exp(-0.25j * np.pi)
    return tones, kernels, qin_edge_pilot_states(edge)


@dataclass
class _Grid:
    iq: tuple
    valid: int
    aperture: int
    frames: np.ndarray
    starts: np.ndarray
    inverse_iq_norm: np.ndarray
    support: np.ndarray
    scores: np.ndarray
    direct: tuple
    error_bound: float
    timing: dict


def _prepare(values, template, sample_rate, frequencies, symbols, epochs):
    aperture = round(sample_rate * OFDM_SYMBOL_DURATION_S)
    span = BLOCK + aperture - 1
    taps = np.arange(aperture)
    if not symbols or any(isinstance(s, bool) or not isinstance(s, int) for s in symbols):
        return None
    starts = np.asarray(symbols, dtype=np.int32) * aperture
    values = np.asarray(values, dtype=np.complex128)
    if (
        values.ndim != 1
        or len(values) != sample_rate // 50
        or not len(frequencies)
        or min(symbols) < 2
        or max(symbols) > 301
        or max(starts) + aperture > len(template)
        or not np.isfinite(frequencies).all()
        or np.any(np.abs(frequencies) > sample_rate / 2)
    ):
        return None
    iq = tuple(np.ascontiguousarray(x, dtype=np.float32) for x in (values.real, values.imag))
    if any(np.any(x < -32768) or np.any(x > 32767) or np.any(x != np.trunc(x)) for x in iq) or (
        np.any(values.real != iq[0]) or np.any(values.imag != iq[1])
    ):
        return None

    references = np.asarray(template[starts[:, None] + taps].conj(), dtype=np.complex128)
    norms = np.array([np.linalg.norm(ref) for ref in references])
    if np.any(norms <= 0):
        return None
    full_ref = references * np.sqrt(8.0)
    scales = norms * np.sqrt(8.0)
    for edge in StarlinkEdge:
        tones, base, all_states = _edge_basis(edge, sample_rate, span)
        states = np.ascontiguousarray(all_states[np.asarray(symbols) - 2], dtype=np.uint8)
        model = ROTATIONS[states] @ base[:, :aperture]
        discrepancy = full_ref - model
        # The template's float time-to-symbol boundary can use the previous
        # state at tap zero. Rounding elsewhere must match the Qin basis.
        if np.max(np.linalg.norm(discrepancy[:, 1:], axis=1) / scales) <= 1e-6:
            break
    else:
        return None

    periods = sample_rate / FRAME_RATE_HZ
    frames = np.rint(np.arange(int(np.ceil(len(values) / periods)) + 1) * periods).astype(np.int32)
    frames = frames[frames < len(values)]
    prefix = np.r_[0.0, np.cumsum(values.real**2 + values.imag**2, dtype=np.float64)]
    energy = np.sqrt(np.maximum(prefix[aperture:] - prefix[:-aperture], 0.0))
    inverse_iq_norm = np.divide(1.0, energy, out=np.zeros_like(energy), where=energy > 0).astype(
        np.float32
    )
    valid = len(energy)
    counts = np.clip(valid - frames[:, None] - starts, 0, epochs).ravel()
    support = np.cumsum(np.bincount(counts, minlength=epochs + 1)[:0:-1])[::-1]
    frequency_rotation = np.exp(-2j * np.pi / sample_rate * frequencies[:, None] * taps)
    coefficients = np.stack([frequency_rotation * ref / norm for ref, norm in zip(
        references, norms, strict=True
    )], axis=1)
    direct = tuple(np.ascontiguousarray(a, dtype=np.float32) for a in (
        coefficients.real, coefficients.imag
    ))
    block_phase = np.exp(-2j * np.pi / sample_rate * frequencies[:, None] * np.arange(span))
    mixed = block_phase[:, None, :] * base
    inverse_phase = np.exp(
        2j * np.pi / sample_rate * (frequencies[:, None] + tones)[..., None] * np.arange(BLOCK)
    )
    weights = np.stack((mixed.real, mixed.imag), axis=-2)
    unrotate = np.stack((inverse_phase.real, inverse_phase.imag), axis=-2)
    model[:, 0] = full_ref[:, 0]
    correction = np.ascontiguousarray(discrepancy[:, 0], dtype=np.complex64).view(np.float32)

    # Bound the coefficient defect from finite-precision phase tables by
    # comparing the adjacent phase relation over the entire block, plus the
    # cancellation from subtracting two independently rounded prefix sums.
    # CI16 has a minimum nonzero local norm of one.
    step = inverse_phase[:, :, 1:2]
    defect = np.max(abs(step * mixed[:, :, 1:] - mixed[:, :, :-1]))
    inverse_defect = np.max(abs(step * inverse_phase[:, :, :-1] - inverse_phase[:, :, 1:]))
    amplitude = np.max(np.abs(values))
    recurrence = amplitude * span * (
        aperture * (defect + inverse_defect + _gamma(4, np.float64))
        + 4 * _gamma(span + 8, np.float64)
    )
    model_coefficients = frequency_rotation[:, None, :] * model / scales[:, None]
    reference32 = direct[0].astype(float) + 1j * direct[1].astype(float)
    template_error = np.max(np.linalg.norm(model_coefficients - reference32, axis=-1))
    mix_norm = np.max((8 * np.sqrt(aperture) + abs(discrepancy[:, 0])) / scales)
    arithmetic = 4 * mix_norm * _gamma(20, np.float32) + 2 * _gamma(aperture + 9, np.float32)
    bound = float(template_error + arithmetic + 8 * recurrence / np.min(scales) + 1e-12)

    scores = np.zeros((len(frequencies), epochs))
    basis = np.empty((16, min(valid, BASIS_TILE)), dtype=np.float32)
    inverse_template = (1 / scales).astype(np.float32)
    persistent = sum(a.nbytes for a in (
        *iq, frames, starts, inverse_iq_norm, support, scores, *direct, weights, unrotate,
        correction, inverse_template, states, basis
    ))
    receipt = dict(
        frequencies=len(frequencies),
        anchors=len(symbols),
        taps=aperture,
        supported_anchor_outputs=int(counts.sum()) * len(frequencies),
        sliding_tone_outputs=8 * valid * len(frequencies),
        sliding_modulation_products=8 * (
            valid + ((valid + BLOCK - 1) // BLOCK) * (aperture - 1)
        ) * len(frequencies),
        shared_basis_bytes=basis.nbytes,
        persistent_stage_array_bytes=persistent,
        error_bound=bound,
    )
    grid = _Grid(
        iq, valid, aperture, frames, starts, inverse_iq_norm, support,
        scores, direct, bound, receipt,
    )
    return grid, weights, unrotate, states, correction, inverse_template, basis


class SpectralGrid:
    """Bind one experimental grid and its matching producer peak selector."""

    def __init__(self, library, control):
        dll = ctypes.CDLL(str(Path(library).resolve()))

        def array(dtype):
            return np.ctypeslib.ndpointer(dtype=dtype, flags="C_CONTIGUOUS")

        f, d, i, b = (array(a) for a in (np.float32, np.float64, np.int32, np.uint8))
        n = ctypes.c_int
        self._score = dll.score_spectral_row
        self._score.argtypes = [f, f, n, n, d, d, i, n, b, f, f, i, n, f, n, f, d]
        self._score.restype = None
        self._repair = dll.repair_spectral_row
        self._repair.argtypes = [f, f, n, n, f, f, i, n, i, n, f, n, i, n, d]
        self._repair.restype = None
        self._control = control
        self._pending = None
        self.receipts = []

    def score_grid(self, values, template, sample_rate, absolute_cfo, symbols, epochs):
        start = process_time()
        args = (values, template, sample_rate, absolute_cfo, symbols, epochs)
        prepared = None
        if sample_rate in SUPPORTED_RATES and epochs == round(sample_rate / FRAME_RATE_HZ):
            prepared = _prepare(
                values, template, sample_rate, np.asarray(absolute_cfo), tuple(symbols), epochs
            )
        self._pending = args, None
        if prepared is None:
            scores = self._control(*args)
            self.receipts.append(dict(
                fallback="unsupported_grid", coarse_cpu_s=process_time() - start,
                sample_rate=sample_rate, samples=len(values), epochs=epochs,
            ))
            return scores
        grid, weights, unrotate, states, correction, inverse_template, basis = prepared
        for index, row in enumerate(grid.scores):
            self._score(
                *grid.iq, grid.valid, grid.aperture, weights[index],
                unrotate[index], grid.starts, len(grid.starts), states,
                correction, inverse_template, grid.frames, len(grid.frames), grid.inverse_iq_norm,
                epochs, basis, row,
            )
        np.divide(grid.scores, grid.support, out=grid.scores, where=grid.support > 0)
        self._pending = args, grid
        grid.timing["coarse_cpu_s"] = process_time() - start
        self.receipts.append(grid.timing)
        return tuple(grid.scores)

    def retain_peaks(self, residuals, scores, count, epoch_separation, cfo_separation, epochs):
        start = process_time()
        args, grid = self._pending if self._pending is not None else (None, None)
        self._pending = None

        def retain(rows):
            return anchor_grid.retained_peaks(
                residuals, rows, count, epoch_separation, cfo_separation, epochs
            )

        initial = retain(scores)
        if grid is None:
            return initial
        control_reason = None
        if not grid.inverse_iq_norm.any():
            grid.timing.update(repair_cpu_s=process_time() - start, repair_tiles=0, fallback=None)
            return initial

        if len(initial) != count:
            control_reason = "insufficient_provisional_peaks"
        else:
            repaired = self._repair_contenders(grid, initial[-1][0] - 2 * grid.error_bound)
            final = retain(scores)
            row_by_cfo = {f: row for row, f in enumerate(residuals)}
            all_repaired = all(
                np.all(repaired[row_by_cfo[f], max(0, e - 1):min(epochs, e + 2)])
                for _, e, f in final
            )
            unrepaired_ub = np.max(grid.scores, where=~repaired, initial=-np.inf) + grid.error_bound
            if len(final) == count and all_repaired and final[-1][0] > unrepaired_ub:
                grid.timing.update(repair_cpu_s=process_time() - start, fallback=None)
                return final
            control_reason = "overlapping_selection_intervals"

        direct = self._control(*args)
        for approximate, exact in zip(scores, direct, strict=True):
            approximate[:] = exact
        grid.timing.update(repair_cpu_s=process_time() - start, fallback=control_reason)
        return retain(scores)

    def _repair_contenders(self, grid, cutoff):
        selected = grid.scores >= cutoff
        repair = selected.copy()
        repair[:, :-1] |= selected[:, 1:]
        repair[:, 1:] |= selected[:, :-1]
        epochs = grid.scores.shape[1]
        result = np.zeros(epochs)
        tiles = 0
        for index, mask in enumerate(repair):
            starts = np.unique(np.flatnonzero(mask) // TILE * TILE).astype(np.int32)
            if not len(starts):
                continue
            tiles += len(starts)
            result.fill(0)
            self._repair(
                *grid.iq, grid.valid, grid.aperture, grid.direct[0][index], grid.direct[1][index],
                grid.starts, len(grid.starts), grid.frames, len(grid.frames), grid.inverse_iq_norm,
                epochs,
                starts, len(starts), result,
            )
            for first in starts:
                mask[first:first + TILE] = True
            np.divide(result, grid.support, out=result, where=grid.support > 0)
            grid.scores[index, mask] = result[mask]
        grid.timing.update(repair_tiles=tiles, repaired_cells=int(repair.sum()))
        return repair
