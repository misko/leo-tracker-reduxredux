"""Small numerical controls for differential-phase observability.

Angles are represented unwrapped in radians.  Wrapping is applied only when a
phasor comparison is requested, so gaps and phase wraps cannot silently become
extra information.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def wrap_rad(value: np.ndarray) -> np.ndarray:
    return np.angle(np.exp(1j * np.asarray(value, dtype=float)))


def _series(name: str, value: np.ndarray, *, size: int | None = None) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.ndim != 1 or result.size < 2:
        raise ValueError(f"{name} must be a one-dimensional series with at least two samples")
    if size is not None and result.size != size:
        raise ValueError(f"{name} length does not match target")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} contains missing or non-finite values")
    return result


def equivalent_decomposition(
    geometry: np.ndarray, instrument: np.ndarray, transfer: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Move any q(t) between geometry and instrument without changing their sum."""
    geometry = _series("geometry", geometry)
    instrument = _series("instrument", instrument, size=geometry.size)
    transfer = _series("transfer", transfer, size=geometry.size)
    return geometry + transfer, instrument - transfer


def relative_to_first(phase: np.ndarray) -> np.ndarray:
    """Return phase change; this is observable with an unknown stable offset."""
    phase = _series("phase", phase)
    return phase - phase[0]


@dataclass(frozen=True)
class ReferenceRecovery:
    phase: np.ndarray
    reference_instrument: np.ndarray


def recover_with_reference(
    satellite_phase: np.ndarray,
    reference_phase: np.ndarray,
    known_reference_geometry: np.ndarray,
) -> ReferenceRecovery:
    """Remove a simultaneous reference response with independently known geometry.

    Any differential injection-path phase is necessarily included in the inferred
    instrument response and therefore appears with the opposite sign in ``phase``.
    """
    satellite = _series("satellite_phase", satellite_phase)
    reference = _series("reference_phase", reference_phase, size=satellite.size)
    known = _series(
        "known_reference_geometry", known_reference_geometry, size=satellite.size
    )
    instrument = reference - known
    return ReferenceRecovery(phase=satellite - instrument, reference_instrument=instrument)
