"""Bounded alternation of orbital-shape proposals and common receiver drift.

Every pass retains the same observations and common original/joined proposal
pool. Drift affects shape profiling; returned seeds use original physical CFO.
No satellite identity or optimizer stationarity is asserted by this initializer.
"""

import time
from dataclasses import asdict, dataclass, replace

import numpy as np

from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
)
from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_score import ALIAS_HZ, circular, predict_orbits, zero_sum_basis


@dataclass(frozen=True)
class ClockConditioningConfiguration:
    conditioning: str = "alternating"
    passes: int = 3
    damping: float = 0.5
    maximum_slope_hz_per_s: float = 50.0
    starts_hz_per_s: tuple[tuple[float, float], ...] = ((0.0, 0.0), (-20.0, -20.0), (20.0, 20.0))

    def __post_init__(self):
        if self.conditioning not in ("none", "alternating"):
            raise ValueError("unknown clock conditioning policy")
        if not isinstance(self.passes, int) or not 1 <= self.passes <= 8:
            raise ValueError("invalid clock conditioning pass count")
        if not np.isfinite((self.damping, self.maximum_slope_hz_per_s)).all():
            raise ValueError("nonfinite clock conditioning limits")
        if not 0 < self.damping <= 1 or not 0 < self.maximum_slope_hz_per_s <= 50:
            raise ValueError("invalid clock conditioning limits")
        starts = np.asarray(self.starts_hz_per_s, float)
        if starts.ndim != 2 or starts.shape[1] != 2 or not 1 <= len(starts) <= 9:
            raise ValueError("invalid clock conditioning starts")
        if not np.isfinite(starts).all() or np.max(abs(starts)) > self.maximum_slope_hz_per_s:
            raise ValueError("clock conditioning starts outside bound")


def _original_support_score(observations, bank, prior, point, tracks, seed, orbit_predictor):
    """Same original supports and weights for every candidate/clock branch."""
    shifts = seed.vector[7] + zero_sum_basis(len(seed.satellite_indices)) @ seed.vector[8:]
    predicted, visible, _, _ = orbit_predictor(
        bank.select(list(seed.satellite_indices)),
        observations,
        prior,
        point,
        shifts,
        derivatives=False,
    )
    centered = observations.times_s - observations.time_center_s
    correction = seed.vector[2 + 2 * observations.receiver]
    correction = correction + seed.vector[3 + 2 * observations.receiver] * centered
    total = 0.0
    for track in tracks:
        rows = np.asarray(track, int)
        matches = [m for m in seed.matches if set(track) <= set(m.rows)]
        if len(matches) > 1:
            raise ValueError("ambiguous original support assignment")
        residual = np.full(len(rows), ALIAS_HZ / 2)
        if matches:
            column = seed.satellite_indices.index(matches[0].satellite_index)
            supported = visible[rows, column]
            residual[supported] = circular(
                observations.measured_hz[rows[supported]]
                - predicted[rows[supported], column]
                - correction[rows[supported]]
            )
        squared_weight = np.sqrt(min(len(rows), 100)) / len(rows)
        total += squared_weight * np.sum(2 * 200**2 * (np.sqrt(1 + (residual / 200) ** 2) - 1))
    return float(total)


def bootstrap_with_clock_conditioning(
    observations,
    bank,
    prior,
    point,
    tracks,
    *,
    merged_tracks,
    policy=None,
    configuration=None,
    maximum_seconds=5.0,
    samples_per_track=12,
    orbit_predictor=predict_orbits,
    audit=None,
):
    """Fixed pass count in both controls; all calls share one total deadline.

    No-conditioning repeats the old procedure, controlling profiling work. The
    alternating arm subtracts the preceding damped common slope during profiling
    and restores it in the physical seed. Absolute returned slopes are clipped
    to the declared initializer bound, with clipping recorded rather than hidden.
    """
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("invalid conditioned bootstrap time budget")
    configuration = configuration or ClockConditioningConfiguration()
    policy = policy or ContinuousBootstrapPolicy()
    begun = time.monotonic()
    centered = observations.times_s - observations.time_center_s
    branches, seeds = [], []
    total_passes = len(configuration.starts_hz_per_s) * configuration.passes
    for branch, start in enumerate(configuration.starts_hz_per_s):
        slopes = np.array(start) if configuration.conditioning == "alternating" else np.zeros(2)
        receipts = []
        for index in range(configuration.passes):
            remaining = maximum_seconds - (time.monotonic() - begun)
            if remaining <= 0:
                raise TimeoutError("conditioned bootstrap total time budget")
            derived = replace(
                observations,
                measured_hz=observations.measured_hz - slopes[observations.receiver] * centered,
            )
            pass_audits = []
            passes_left = total_passes - branch * configuration.passes - index
            result = bootstrap_with_continuity(
                derived,
                bank,
                prior,
                point,
                tracks,
                merged_tracks=merged_tracks,
                policy=policy,
                audit=pass_audits.append,
                maximum_seconds=remaining / passes_left,
                samples_per_track=samples_per_track,
                orbit_predictor=orbit_predictor,
            )
            vector = result.vector.copy()
            absolute = vector[[3, 5]] + slopes
            vector[[3, 5]] = np.clip(
                absolute,
                -configuration.maximum_slope_hz_per_s,
                configuration.maximum_slope_hz_per_s,
            )
            restored = PositionBootstrap(result.satellite_indices, vector, result.matches)
            receipts.append(
                {
                    "pass": index,
                    "conditioning_slopes_hz_per_s": slopes.tolist(),
                    "restored_slopes_hz_per_s": vector[[3, 5]].tolist(),
                    "slope_clipped": (absolute != vector[[3, 5]]).tolist(),
                    "candidate_indices": list(result.satellite_indices),
                    "proposal_audit": pass_audits[0],
                }
            )
            if configuration.conditioning == "alternating":
                slopes = (1 - configuration.damping) * slopes + configuration.damping * vector[
                    [3, 5]
                ]
        score = _original_support_score(
            observations, bank, prior, point, tracks, restored, orbit_predictor
        )
        seeds.append(restored)
        branches.append(
            {"start_hz_per_s": list(start), "passes": receipts, "original_support_score": score}
        )
    if time.monotonic() - begun >= maximum_seconds:
        raise TimeoutError("conditioned bootstrap total time budget")
    selected = min(range(len(branches)), key=lambda i: (branches[i]["original_support_score"], i))
    if audit is not None:
        audit(
            {
                "configuration": asdict(configuration),
                "policy": asdict(policy),
                "point": list(point),
                "branches": branches,
                "selected_branch": selected,
                "seconds": time.monotonic() - begun,
                "scope": "Initializer proposals only; candidate preferences are not identities.",
            }
        )
    return seeds[selected]
