"""Bounded catalogue propagation with a conservative whole-prior horizon screen."""

import time
from dataclasses import dataclass

import numpy as np

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.regional_position_score import observer
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


@dataclass(frozen=True)
class RegionalBankReceipt:
    catalogue_count: int
    retained_numbers: tuple[int, ...]
    invalid_numbers: tuple[int, ...]
    outside_prior_numbers: tuple[int, ...]
    node_step_s: float
    elapsed_s: float


def could_be_visible(position_km, prior: RegionalPrior):
    """Conservative bound over every geodetic normal within the prior disk.

    For a fixed normal, satellite dot normal is linear between state-bank nodes;
    endpoint rejection therefore also rejects the interpolated interval. The
    ellipsoid support radius is at least its polar radius. This test deliberately
    retains borderline objects; actual visibility is evaluated at every trial site.
    """
    position = np.asarray(position_km, float)
    if position.ndim != 3 or position.shape[2] != 3 or not np.isfinite(position).all():
        raise ValueError("finite satellite/node/xyz positions required")
    _, center_up = observer(prior, [0, 0])
    radius = np.linalg.norm(position, axis=2)
    if np.any(radius <= 0):
        raise ValueError("nonzero satellite radius required")
    angle = np.arccos(np.clip(np.einsum("knj,j->kn", position, center_up) / radius, -1, 1))
    maximum_dot = radius * np.cos(np.maximum(angle - prior.radius_km / 6371.0088, 0))
    return np.any(maximum_dot >= 6356.752314245 + prior.altitude_m / 1000, axis=1)


def build_regional_bank(
    catalogue,
    indices,
    origin_utc_ns: int,
    observations: PositionObservations,
    prior: RegionalPrior,
    *,
    maximum_seconds=180.0,
    batch_size=128,
):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800 or batch_size < 1:
        raise ValueError("invalid bank work bounds")
    begun = time.monotonic()
    nodes = np.arange(
        np.floor(observations.times_s.min()) - 21, np.ceil(observations.times_s.max()) + 21.25, 0.25
    )
    numbers = np.asarray(catalogue.satellite_numbers)
    positions, velocities = [], []
    retained: list[int] = []
    invalid: list[int] = []
    outside: list[int] = []
    for begin in range(0, len(indices), batch_size):
        if time.monotonic() - begun >= maximum_seconds:
            raise TimeoutError("regional orbit bank time budget")
        batch = np.asarray(indices[begin : begin + batch_size])
        position, velocity, valid = propagate_candidate_states(
            catalogue, batch.tolist(), origin_utc_ns, nodes, np.array([0.0])
        )
        invalid.extend(int(numbers[i]) for i in sorted(set(batch) - set(valid)))
        position, velocity = position[:, 0], velocity[:, 0]
        keep = could_be_visible(position, prior)
        outside.extend(int(numbers[i]) for i in valid[~keep])
        retained.extend(int(numbers[i]) for i in valid[keep])
        positions.extend(position[keep])
        velocities.extend(velocity[keep])
    if not retained:
        raise ValueError("no valid satellites potentially visible in prior")
    bank = PositionOrbitBank(
        np.asarray(retained), nodes, np.asarray(positions), np.asarray(velocities)
    )
    receipt = RegionalBankReceipt(
        len(indices),
        tuple(retained),
        tuple(invalid),
        tuple(outside),
        0.25,
        time.monotonic() - begun,
    )
    return bank, receipt
