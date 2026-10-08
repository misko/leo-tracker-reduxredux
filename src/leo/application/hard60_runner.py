"""Single-method Hard60 policy, qualified on the recorded N01--N64 cohort.

Reference coordinates never enter discovery, calibration, association or selection.
The two c arms are conditional final-stage ablations, with equal fitting budgets.
"""

import time
from dataclasses import dataclass, replace
from functools import partial

import numpy as np

from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_calibration import RegionalCalibration, receiver_correction
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_search import (
    SpatialSearch,
    distinct_basins,
    hierarchical_search,
)
from leo.application.regional_position_runner import (
    RegionalSliceExpired,
    _bootstrap,
    _calibration,
    _fit,
    json_value,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import POSITION_SCORES

HARD60_SCORE = replace(POSITION_SCORES["V16"], relative_sigma_s=2.0)


@dataclass(frozen=True)
class Hard60Configuration:
    policy: str = "hard60-v1"
    point_budget: int = 400
    levels_km: tuple[float, ...] = (40.0, 20.0, 10.0, 5.0)
    edge_priority: str = "nearest"
    slope_half_width_hz_s: float = 60.0
    basins: int = 3
    basin_separation_km: float = 12.5
    minimum_local_radius_km: float = 25.0
    bootstrap_seconds: float = 5.0
    coarse_fit_seconds: float = 5.0
    stage_fit_seconds: float = 20.0
    association_seconds: float = 60.0
    coarse_iterations: int = 200
    final_iterations: int = 600
    backend: str = "audited-native-orbits-narrow-gaussian-v1"
    final_starts: tuple[str, ...] = ("association", "zero-timing", "own-continuation")

    def __post_init__(self):
        if self.policy != "hard60-v1" or self.slope_half_width_hz_s != 60:
            raise ValueError("Hard60 requires its named hard slope bound")
        if self.point_budget < 1 or self.basins < 1:
            raise ValueError("invalid Hard60 search budget")
        if self.coarse_iterations < 1 or self.final_iterations < 1:
            raise ValueError("invalid Hard60 iteration budget")
        for value in (
            self.bootstrap_seconds,
            self.coarse_fit_seconds,
            self.stage_fit_seconds,
            self.association_seconds,
        ):
            if not np.isfinite(value) or not 0 < value <= 1800:
                raise ValueError("invalid Hard60 stage budget")


def run_hard60(
    observations, bank, prior, tracks, checkpoints, *, configuration=None, maximum_seconds=500.0
):
    if not np.isfinite(maximum_seconds) or maximum_seconds <= 0:
        raise ValueError("invalid worker slice budget")
    config = configuration or Hard60Configuration()
    deadline = time.monotonic() + maximum_seconds
    binding = canonical_digest(json_value(config))

    def stage(key, budget, operation):
        key = binding + ":" + key
        cached = checkpoints.get(key)
        if cached is not None:
            return cached
        if time.monotonic() + budget >= deadline:
            raise RegionalSliceExpired(key)
        try:
            receipt = {"result": json_value(operation()), "reason": None}
        except (ValueError, TimeoutError) as error:
            receipt = {"result": None, "reason": f"{type(error).__name__}: {error}"}
        checkpoints.put(key, receipt)
        return receipt

    def fit(objective, start, *, coarse=False, **options):
        return fit_position(
            objective,
            start,
            slope_half_width_hz_s=config.slope_half_width_hz_s,
            maximum_seconds=config.coarse_fit_seconds if coarse else config.stage_fit_seconds,
            maximum_iterations=config.coarse_iterations if coarse else config.final_iterations,
            **options,
        )

    def key_for(east, north):
        return f"point:{east:g}:{north:g}"

    def point(east, north):
        def compute():
            seed = bootstrap_position(
                observations,
                bank,
                prior,
                [east, north],
                tracks,
                maximum_seconds=config.bootstrap_seconds,
                orbit_predictor=predict_orbits,
            )
            objective = Hard60Objective(
                observations,
                bank.select(list(seed.satellite_indices)),
                prior,
                HARD60_SCORE,
            )
            fitted = fit(objective, seed.vector, coarse=True, fixed_position=True)
            return {
                "bootstrap": json_value(seed),
                "fits": {"V16": {"fit": json_value(fitted), "reason": None}},
            }

        return stage(
            key_for(east, north), config.bootstrap_seconds + config.coarse_fit_seconds, compute
        )

    def evaluate(east, north):
        receipt = point(east, north)
        return receipt["result"]["fits"]["V16"]["fit"]["objective"] if receipt["result"] else 1e100

    search = hierarchical_search(
        evaluate,
        radius_km=prior.radius_km,
        levels_km=config.levels_km,
        budget_points=config.point_budget,
        edge_priority=config.edge_priority,
    )
    supported = SpatialSearch(
        tuple(p for p in search.evaluations if p.score < 1e100),
        search.deferred_cells,
        search.stop_reason,
    )
    basins = distinct_basins(
        supported, count=config.basins, minimum_separation_km=config.basin_separation_km
    )
    finals, failures, calibrations = [], [], {}
    for basin in sorted(basins, key=lambda p: (p.east_km, p.north_km)):
        key = key_for(basin.east_km, basin.north_km)
        initial = point(basin.east_km, basin.north_km)["result"]
        seed = _bootstrap(initial["bootstrap"])
        subset = bank.select(list(seed.satellite_indices))
        objective = Hard60Objective(observations, subset, prior, HARD60_SCORE)

        def calibrate(initial=initial, objective=objective, subset=subset, seed=seed):
            prefit = _fit(initial["fits"]["V16"]["fit"])
            if not prefit.converged:
                prefit = fit(objective, prefit.vector, fixed_position=True)
            if not prefit.converged:
                raise ValueError("V16 calibration prefit did not converge")
            correction = receiver_correction(observations, objective.evaluate(prefit.vector)[2])
            corrected = Hard60Objective(
                observations,
                subset,
                prior,
                HARD60_SCORE,
                receiver_baseline_hz=correction.values_hz,
            )
            postfit = fit(corrected, prefit.vector, fixed_position=True)
            if not postfit.converged:
                raise ValueError("V16 calibration postfit did not converge")
            baseline = correction.values_hz + corrected.design[:, :4] @ postfit.vector[2:6]
            return RegionalCalibration(
                seed.satellite_indices, prefit, postfit, correction, baseline
            )

        receipt = stage(key + ":calibration", 2 * config.stage_fit_seconds, calibrate)
        if receipt["result"] is None:
            failures.append({"basin": key, "stage": "calibration", "reason": receipt["reason"]})
            continue
        calibrated = _calibration(receipt["result"])
        calibrations[key] = receipt["result"]
        receipt = stage(
            key + ":association",
            config.association_seconds,
            partial(
                associate_calibration,
                observations,
                bank,
                prior,
                calibrated,
                maximum_seconds=config.association_seconds,
                orbit_predictor=predict_orbits,
            ),
        )
        if receipt["result"] is None:
            failures.append({"basin": key, "stage": "association", "reason": receipt["reason"]})
            continue
        selected = receipt["result"]
        final_bank = bank.select(selected["selected_indices"])
        final_objective = Hard60Objective(
            observations,
            final_bank,
            prior,
            HARD60_SCORE,
            receiver_baseline_hz=calibrated.receiver_baseline_hz,
        )
        knots = calibrated.correction.knots_hz
        penalty = float(
            0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
        )
        center = np.array([basin.east_km, basin.north_km])
        radius = max(config.minimum_local_radius_km, basin.spacing_km / np.sqrt(2))
        for arm in ("zero-c", "fitted-c"):
            completed = []
            for start_name in config.final_starts:
                start = np.array(selected["initial_vector"], float)
                if start_name == "zero-timing":
                    start[7:] = 0
                elif start_name == "own-continuation" and completed:
                    start = np.array(min(completed, key=lambda row: row["objective"])["vector"])
                for origin, bound in ((np.zeros(2), prior.radius_km), (center, radius)):
                    delta = start[:2] - origin
                    distance = np.linalg.norm(delta)
                    if bound < distance <= bound + 1e-6:
                        start[:2] = origin + delta * ((bound - 1e-8) / distance)
                # Fit retains the best feasible evaluated state, including its initial state.
                # Continuation always belongs to the same c arm; no cross-arm warm starts.
                receipt = stage(
                    f"{key}:{arm}:{start_name}",
                    config.stage_fit_seconds,
                    partial(
                        fit,
                        final_objective,
                        start,
                        rf_arm=arm,
                        local_center=center,
                        local_radius_km=radius,
                    ),
                )
                if receipt["result"] is not None:
                    completed.append(receipt["result"])
                finals.append(
                    {
                        "basin": key,
                        "method": "V16",
                        "arm": arm,
                        "start": start_name,
                        "fit": receipt["result"],
                        "reason": receipt["reason"],
                        "calibration_penalty": penalty,
                        "satellites": final_bank.numbers.tolist(),
                        "association": selected["selection"],
                    }
                )
    return {
        "searches": {"V16": json_value(search)},
        "points": {
            key_for(p.east_km, p.north_km): point(p.east_km, p.north_km) for p in search.evaluations
        },
        "basins": json_value(basins),
        "calibrations": calibrations,
        "finals": finals,
        "failures": failures,
    }
