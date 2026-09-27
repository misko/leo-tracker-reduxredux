"""Compact, science-identical GLRT-64 workspace prototype.

This is a report-owned experiment.  Production remains the numerical oracle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from leo.analysis.starlink import pilot_methods
from leo.analysis.starlink.pilot_methods import PilotMethod, PilotMethodScore, _SymbolCorrelations
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_frame,
)

_FIRST_SYMBOL = 2
_LAST_SYMBOL = 65


@dataclass(frozen=True, slots=True)
class _CompactGeometry:
    exact_template: np.ndarray
    control_template: np.ndarray
    local_starts: np.ndarray
    local_stops: np.ndarray
    counts: np.ndarray


def _immutable(values: np.ndarray) -> np.ndarray:
    values.flags.writeable = False
    return values


@lru_cache(maxsize=8)
def _compact_geometry(sample_rate_hz: float, edge: StarlinkEdge) -> _CompactGeometry:
    """Cache sample-independent templates and the exact 64-symbol geometry."""

    exact = _immutable(
        np.asarray(qin_edge_pilot_frame(sample_rate_hz, edge), dtype=np.complex128)
    )
    control = _immutable(
        np.asarray(
            qin_edge_pilot_frame(
                sample_rate_hz,
                edge,
                symbol_roll=CONTROL_SYMBOL_ROLL,
            ),
            dtype=np.complex128,
        )
    )
    symbols = np.arange(_FIRST_SYMBOL, _LAST_SYMBOL + 1)
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    starts = _immutable(np.rint(symbols * symbol_period).astype(int))
    stops = _immutable(
        np.minimum(np.rint((symbols + 1) * symbol_period).astype(int), len(exact))
    )
    return _CompactGeometry(exact, control, starts, stops, _immutable(stops - starts))


def compact_glrt64_correlations(
    samples: np.ndarray,
    sample_rate_hz: int,
    epoch_sample: int,
    cfo_hz: float,
    *,
    edge: StarlinkEdge | str,
) -> tuple[_SymbolCorrelations, _SymbolCorrelations]:
    """Return the same selected GLRT-64 correlations without a 300-column workspace."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    geometry = _compact_geometry(float(sample_rate_hz), selected_edge)
    frame_period = sample_rate_hz / FRAME_RATE_HZ

    frame_starts: list[int] = []
    frame = 0
    while True:
        frame_start = epoch_sample + round(frame * frame_period)
        if frame_start >= len(values) or frame_start + geometry.local_starts[0] >= len(values):
            break
        frame_starts.append(frame_start)
        frame += 1

    shape = (len(frame_starts), len(geometry.local_starts))
    exact_matrix = np.zeros(shape, dtype=np.complex128)
    exact_power = np.zeros(shape, dtype=float)
    control_matrix = np.zeros(shape, dtype=np.complex128)
    control_power = np.zeros(shape, dtype=float)
    times = np.zeros(shape, dtype=float)
    valid_matrix = np.zeros(shape, dtype=bool)

    # Keep the production grouping, vector operations, and reduction axes in the
    # same order.  Only the unused columns for symbols 66..301 are absent.
    for count in np.unique(geometry.counts):
        if count < 2:
            continue
        positions = np.flatnonzero(geometry.counts == count)
        relative = geometry.local_starts[positions, None] + np.arange(int(count))[None, :]
        relative_rotation = np.exp(-2j * np.pi * cfo_hz * relative / sample_rate_hz)
        exact_reference = geometry.exact_template[relative]
        control_reference = geometry.control_template[relative]
        exact_energy = np.sum(np.abs(exact_reference) ** 2, axis=1)
        control_energy = np.sum(np.abs(control_reference) ** 2, axis=1)
        for frame_index, frame_start in enumerate(frame_starts):
            starts = frame_start + geometry.local_starts[positions]
            valid = (starts >= 0) & (starts + count <= len(values))
            if not np.any(valid):
                continue
            active_positions = positions[valid]
            absolute = frame_start + relative[valid]
            frame_rotation = np.exp(-2j * np.pi * cfo_hz * frame_start / sample_rate_hz)
            received = values[absolute]
            corrected = received * relative_rotation[valid] * frame_rotation
            received_energy = np.sum(np.abs(received) ** 2, axis=1)
            exact_correlation = np.sum(np.conj(exact_reference[valid]) * corrected, axis=1)
            control_correlation = np.sum(
                np.conj(control_reference[valid]) * corrected,
                axis=1,
            )
            exact_matrix[frame_index, active_positions] = exact_correlation
            control_matrix[frame_index, active_positions] = control_correlation
            exact_power[frame_index, active_positions] = np.abs(exact_correlation) ** 2 / np.maximum(
                exact_energy[valid] * received_energy,
                1e-20,
            )
            control_power[frame_index, active_positions] = np.abs(
                control_correlation
            ) ** 2 / np.maximum(control_energy[valid] * received_energy, 1e-20)
            times[frame_index, active_positions] = (
                starts[valid] + (count - 1) / 2
            ) / sample_rate_hz
            valid_matrix[frame_index, active_positions] = True

    valid = np.logical_and.reduce(tuple(valid_matrix[:, index] for index in range(shape[1])))
    invalid = np.flatnonzero(~valid)
    frame_count = int(invalid[0]) if invalid.size else len(valid)

    def selected(matrix: np.ndarray, *, dtype: np.dtype) -> np.ndarray:
        selected_shape = (frame_count, shape[1])
        if not frame_count:
            return np.zeros(selected_shape, dtype=dtype)
        # Match _ConditionedCorrelationWorkspace.select's column-stack order.
        return np.stack(
            tuple(matrix[:frame_count, index] for index in range(shape[1])),
            axis=1,
        )

    exact = _SymbolCorrelations(
        selected(exact_matrix, dtype=np.dtype(np.complex128)),
        selected(exact_power, dtype=np.dtype(float)),
        selected(times, dtype=np.dtype(float)),
    )
    control = _SymbolCorrelations(
        selected(control_matrix, dtype=np.dtype(np.complex128)),
        selected(control_power, dtype=np.dtype(float)),
        selected(times, dtype=np.dtype(float)),
    )
    return exact, control


def compact_conditioned_glrt64_score(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    epoch_sample: int,
    acquired_cfo_hz: float,
    edge: StarlinkEdge | str = StarlinkEdge.LOWER,
    glrt_size: int = 512,
) -> PilotMethodScore:
    """Drop-in scientific prototype for ``conditioned_glrt64_score``."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("conditioned pilot samples must be a nonempty vector")
    if not math.isfinite(acquired_cfo_hz):
        raise ValueError("acquired CFO must be finite")
    if isinstance(glrt_size, bool) or not isinstance(glrt_size, int) or glrt_size < 2:
        raise ValueError("GLRT size must be an integer of at least two")
    exact, control = compact_glrt64_correlations(
        values,
        sample_rate_hz,
        epoch_sample,
        acquired_cfo_hz,
        edge=edge,
    )
    (score, residual), (control_score, _) = pilot_methods._glrt_pair(
        exact,
        control,
        size=glrt_size,
    )
    return pilot_methods._score(
        PilotMethod.GLRT64,
        score,
        control_score,
        residual,
        acquired_cfo_hz,
    )
