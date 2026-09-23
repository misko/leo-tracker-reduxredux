"""Phase-coordinate helpers for the sealed long-arc pilot-frame replay.

The saved complex vector is already in the raw capture carrier gauge.  For a
guarded slice beginning at a physical sample counter ``o``, the estimator
removes an acquisition NCO at local sample ``n`` and restores it at the local
reference.  The raw samples themselves contain the ``o`` phase.  Therefore a
consumer must use the physical reference counter below, but must *not* rotate
the saved vector by ``o`` again.
"""

from __future__ import annotations

import numpy as np


def saved_reference_counter(frame: dict, observation: dict, source_first_counter: int) -> float:
    """Physical counter of a vector produced by the current integer-grid replay."""
    return float(
        observation["valid_start_counter"]
        - source_first_counter
        + frame["frame"]["reference_sample"]
    )


def fractional_reextracted_reference_counter(
    frame: dict, observation: dict, source_first_counter: int
) -> float:
    """Reference counter only if a future extractor interpolates at fractional epoch."""
    return saved_reference_counter(frame, observation, source_first_counter) + float(
        observation["fractional_epoch_offset_samples"]
    )


def wrap_pi(angle_rad: float | np.ndarray) -> float | np.ndarray:
    """Wrap carrier phase to the Qin pilot's pi-radian equivalence class."""
    return 0.5 * np.angle(np.exp(2j * np.asarray(angle_rad)))


def vector_increment_rad(left: np.ndarray, right: np.ndarray) -> float:
    """Common carrier advance of two tone vectors, modulo pi.

    ``vdot`` cancels a static per-tone channel.  Squaring its phase implements
    the documented pi carrier-phase period without choosing a sign branch.
    """
    overlap = np.vdot(np.asarray(left, complex), np.asarray(right, complex))
    if not np.isfinite(overlap) or abs(overlap) == 0:
        raise ValueError("vectors must have finite nonzero overlap")
    return float(wrap_pi(np.angle(overlap)))


def carrier_cycles_from_frequency(times_s: np.ndarray, frequency_hz: np.ndarray) -> np.ndarray:
    """Trapezoidal carrier cycles at frame references, anchored at zero."""
    times = np.asarray(times_s, float)
    frequency = np.asarray(frequency_hz, float)
    if times.ndim != 1 or frequency.shape != times.shape or len(times) < 1:
        raise ValueError("times and frequencies must be aligned nonempty vectors")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(frequency)):
        raise ValueError("times and frequencies must be finite")
    if np.any(np.diff(times) <= 0):
        raise ValueError("frame references must be strictly increasing")
    cycles = np.zeros(len(times), dtype=float)
    cycles[1:] = np.cumsum(0.5 * (frequency[1:] + frequency[:-1]) * np.diff(times))
    return cycles


def transport_vectors(
    vectors: np.ndarray, times_s: np.ndarray, reference_frequency_hz: np.ndarray
) -> np.ndarray:
    """Remove a declared native-RF carrier trajectory from raw-gauge vectors."""
    vectors = np.asarray(vectors, complex)
    if vectors.ndim != 2 or vectors.shape[0] != len(times_s):
        raise ValueError("one tone vector is required for every frame time")
    cycles = carrier_cycles_from_frequency(times_s, reference_frequency_hz)
    return vectors * np.exp(-2j * np.pi * cycles)[:, None]
