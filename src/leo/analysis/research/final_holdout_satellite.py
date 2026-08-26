"""Pure Starlink candidate propagation for the final holdout.

Catalogue bytes, site/RF authorities, and bin membership must already be frozen
before calling this module.  It performs no archive lookup or response access.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from leo.contracts.sky import ObserverSiteV1
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

COARSE_SPACING_S = 0.1


@dataclass(frozen=True, slots=True)
class StarlinkCandidatePopulation:
    catalogue_indices: IntArray
    norad_ids: IntArray
    names: tuple[str, ...]
    prediction_hz: FloatArray
    minimum_elevation_deg: FloatArray
    maximum_elevation_deg: FloatArray
    coarse_candidate_count: int


def visible_starlink_candidates(
    catalogue: ElementSetCatalogue,
    utc_ns: IntArray,
    *,
    nominal_sky_frequency_hz: float,
    observer_preset: str,
) -> StarlinkCandidatePopulation:
    """Return the full geometric-horizon union at exact frozen bin times."""

    return visible_starlink_candidates_at_site(
        catalogue,
        utc_ns,
        nominal_sky_frequency_hz=nominal_sky_frequency_hz,
        observer=resolve_preset(observer_preset),
    )


def visible_starlink_candidates_at_site(
    catalogue: ElementSetCatalogue,
    utc_ns: IntArray,
    *,
    nominal_sky_frequency_hz: float,
    observer: ObserverSiteV1,
) -> StarlinkCandidatePopulation:
    """Return candidates for one already-frozen observer sensitivity site."""

    times = np.asarray(utc_ns, dtype=np.int64)
    if times.ndim != 1 or times.size < 3 or np.any(np.diff(times) <= 0):
        raise ValueError("candidate UTC bins must be strictly increasing and nontrivial")
    if not math.isfinite(nominal_sky_frequency_hz) or nominal_sky_frequency_hz <= 0.0:
        raise ValueError("nominal sky frequency must be finite and positive")
    coarse_grid = _uniform_grid(int(times[0]), int(times[-1]), COARSE_SPACING_S)
    coarse = observe_grid(propagate_grid(catalogue, coarse_grid), observer, coarse_grid)
    margin = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    plausible = coarse.usable & (np.min(coarse.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    coarse_indices = np.flatnonzero(plausible & (np.max(coarse.elevation_deg, axis=1) > -margin))
    exact_grid = SamplingGrid(
        tuple(int(value) for value in times),
        times.size // 2,
        float(np.median(np.diff(times)) / 1e9),
    )
    exact = observe_grid(
        propagate_grid(catalogue, exact_grid, indices=coarse_indices.tolist()),
        observer,
        exact_grid,
    )
    exact_plausible = exact.usable & (
        np.min(exact.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    rows = np.flatnonzero(exact_plausible & (np.max(exact.elevation_deg, axis=1) >= 0.0))
    indices = np.asarray(coarse_indices[rows], dtype=np.int64)
    predictions = np.asarray(
        doppler_shift_hz(nominal_sky_frequency_hz, exact.range_rate_km_s[rows]),
        dtype=np.float64,
    )
    return StarlinkCandidatePopulation(
        catalogue_indices=indices,
        norad_ids=np.asarray(
            [catalogue.satellite_numbers[int(index)] for index in indices],
            dtype=np.int64,
        ),
        names=tuple(catalogue.names[int(index)] for index in indices),
        prediction_hz=predictions,
        minimum_elevation_deg=np.min(exact.elevation_deg[rows], axis=1),
        maximum_elevation_deg=np.max(exact.elevation_deg[rows], axis=1),
        coarse_candidate_count=int(coarse_indices.size),
    )


def _uniform_grid(start_ns: int, stop_ns: int, spacing_s: float) -> SamplingGrid:
    if stop_ns <= start_ns:
        raise ValueError("candidate UTC interval has no positive span")
    step_ns = max(1, round(spacing_s * 1e9))
    count = max(3, math.ceil((stop_ns - start_ns) / step_ns) + 1)
    values = tuple(start_ns + index * step_ns for index in range(count))
    return SamplingGrid(values, count // 2, step_ns / 1e9)
