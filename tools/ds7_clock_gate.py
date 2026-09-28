"""Reference-free numerical gates for a constrained DS7 receiver-clock state."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class IdentifiabilityResult:
    rank: int
    columns: int
    scaled_condition_number: float
    projected_clock_norm: float
    identifiable: bool


def identifiability(
    position_and_nuisance: npt.ArrayLike,
    clock_column: npt.ArrayLike,
    *,
    maximum_condition_number: float = 1_000.0,
    minimum_projected_norm: float = 0.05,
) -> IdentifiabilityResult:
    """Test whether one shared clock column survives projection on other states.

    Columns are normalized before the condition-number test so units alone do
    not determine the result.  The projected norm is relative to the original
    clock-column norm.
    """
    base = np.asarray(position_and_nuisance, dtype=np.float64)
    clock = np.asarray(clock_column, dtype=np.float64).reshape(-1)
    if base.ndim != 2 or base.shape[0] != clock.size or clock.size == 0:
        raise ValueError("design rows and clock column must be nonempty and aligned")
    design = np.column_stack((base, clock))
    norms = np.linalg.norm(design, axis=0)
    if np.any(~np.isfinite(design)) or np.any(norms == 0.0):
        raise ValueError("design columns must be finite and nonzero")
    scaled = design / norms
    singular = np.linalg.svd(scaled, compute_uv=False)
    tolerance = max(scaled.shape) * np.finfo(np.float64).eps * singular[0]
    rank = int(np.count_nonzero(singular > tolerance))
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0.0 else float("inf")
    coefficients, *_ = np.linalg.lstsq(base, clock, rcond=None)
    projected = clock - base @ coefficients
    projected_norm = float(np.linalg.norm(projected) / np.linalg.norm(clock))
    return IdentifiabilityResult(
        rank=rank,
        columns=design.shape[1],
        scaled_condition_number=condition,
        projected_clock_norm=projected_norm,
        identifiable=(
            rank == design.shape[1]
            and condition <= maximum_condition_number
            and projected_norm >= minimum_projected_norm
        ),
    )


def recover_injected_bias(
    position_and_nuisance: npt.ArrayLike,
    clock_column: npt.ArrayLike,
    injected_bias_hz: float,
) -> float:
    """Recover a noise-free injected clock bias without a prior."""
    base = np.asarray(position_and_nuisance, dtype=np.float64)
    clock = np.asarray(clock_column, dtype=np.float64).reshape(-1)
    design = np.column_stack((base, clock))
    response = clock * float(injected_bias_hz)
    estimate, *_ = np.linalg.lstsq(design, response, rcond=None)
    return float(estimate[-1])
