"""Resumable Sacramento search and matched final RF comparisons through narrow ports.

No reference location enters this runner. Checkpoints must be scoped by the caller
to the input, ephemeris, code and configuration digests.
"""

import time
from dataclasses import asdict, dataclass, is_dataclass
from functools import partial

import numpy as np

from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_bootstrap import (
    BootstrapMatch,
    PositionBootstrap,
    bootstrap_position,
)
from leo.analysis.regional_position_calibration import (
    ReceiverCorrection,
    RegionalCalibration,
    calibrate_position,
)
from leo.analysis.regional_position_fit import PositionFit, fit_position
from leo.analysis.regional_position_score import PositionObjective
from leo.analysis.regional_position_search import (
    SpatialEvaluation,
    SpatialSearch,
    distinct_basins,
    hierarchical_search,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import POSITION_SCORES
from leo.contracts.regional_position_products import RegionalCheckpoints


class RegionalSliceExpired(Exception):
    """Completed stages are persisted; another worker slice can resume."""


@dataclass(frozen=True)
class RegionalRunConfiguration:
    point_budget: int = 400
    levels_km: tuple[float, ...] = (100.0, 50.0, 25.0, 12.5)
    basins_per_method: int = 3
    bootstrap_seconds: float = 5.0
    coarse_fit_seconds: float = 5.0
    calibration_seconds: float = 30.0
    association_seconds: float = 60.0
    final_fit_seconds: float = 20.0
    coarse_iterations: int = 200
    final_iterations: int = 300

    def __post_init__(self):
        if self.point_budget < 16 or self.basins_per_method < 1:
            raise ValueError("invalid regional search budget")
        if self.coarse_iterations < 1 or self.final_iterations < 1:
            raise ValueError("invalid regional optimizer budget")
        budgets = (
            self.bootstrap_seconds,
            self.coarse_fit_seconds,
            self.calibration_seconds,
            self.association_seconds,
            self.final_fit_seconds,
        )
        if any(not np.isfinite(value) or not 0 < value <= 1800 for value in budgets):
            raise ValueError("invalid regional stage time budget")


def json_value(value):
    """Convert numerical stage receipts to plain, non-pickle checkpoint values."""
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def _bootstrap(value):
    return PositionBootstrap(
        tuple(value["satellite_indices"]),
        np.asarray(value["vector"]),
        tuple(BootstrapMatch(**m) for m in value["matches"]),
    )


def _fit(value):
    return PositionFit(**{**value, "vector": np.asarray(value["vector"])})


def _calibration(value):
    correction = value["correction"]
    return RegionalCalibration(
        tuple(value["satellite_indices"]),
        _fit(value["prefit"]),
        _fit(value["postfit"]),
        ReceiverCorrection(
            np.asarray(correction["nodes_s"]),
            np.asarray(correction["knots_hz"]),
            np.asarray(correction["values_hz"]),
            tuple(correction["support_rows"]),
        ),
        np.asarray(value["receiver_baseline_hz"]),
    )


def run_regional_position(
    observations,
    bank,
    prior,
    tracks,
    checkpoints: RegionalCheckpoints,
    *,
    configuration: RegionalRunConfiguration | None = None,
    maximum_seconds=560.0,
):
    """Return complete numerical receipts or yield at a checkpoint boundary.

    Both hierarchies share original windows, orbit bank and per-point bootstrap.
    The union of their strongest distinct basins supplies identical final starts
    and frozen association/calibration to both scores and both RF arms.
    """
    if not np.isfinite(maximum_seconds) or maximum_seconds <= 0:
        raise ValueError("invalid worker slice budget")
    deadline = time.monotonic() + maximum_seconds
    config = configuration or RegionalRunConfiguration()
    config_key = canonical_digest(json_value(config))

    def stage(key, budget, operation):
        key = config_key + ":" + key
        cached = checkpoints.get(key)
        if cached is not None:
            return cached
        if time.monotonic() + budget >= deadline:
            raise RegionalSliceExpired(key)
        try:
            value = {"result": json_value(operation()), "reason": None}
        except (ValueError, TimeoutError) as error:
            value = {"result": None, "reason": f"{type(error).__name__}: {error}"}
        checkpoints.put(key, value)
        return value

    def point_key(east, north):
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
            )
            selected = bank.select(list(seed.satellite_indices))
            fits = {}
            for name, score in POSITION_SCORES.items():
                objective = PositionObjective(observations, selected, prior, score)
                try:
                    fits[name] = {
                        "fit": json_value(
                            fit_position(
                                objective,
                                seed.vector,
                                fixed_position=True,
                                maximum_seconds=config.coarse_fit_seconds,
                                maximum_iterations=config.coarse_iterations,
                            )
                        ),
                        "reason": None,
                    }
                except (ValueError, TimeoutError) as error:
                    fits[name] = {"fit": None, "reason": str(error)}
            return {"bootstrap": json_value(seed), "fits": fits}

        return stage(
            point_key(east, north),
            config.bootstrap_seconds + 2 * config.coarse_fit_seconds,
            compute,
        )

    searches = {}
    for name in POSITION_SCORES:

        def evaluate(east, north, method=name):
            receipt = point(east, north)
            result = receipt["result"]
            fit = result["fits"][method]["fit"] if result else None
            # Internal frontier ordering only. Missing objectives remain null in products.
            return fit["objective"] if fit else 1e100

        searches[name] = hierarchical_search(
            evaluate,
            radius_km=prior.radius_km,
            levels_km=config.levels_km,
            budget_points=config.point_budget,
        )

    basins: dict[str, SpatialEvaluation] = {}
    for search in searches.values():
        supported = SpatialSearch(
            tuple(p for p in search.evaluations if p.score < 1e100),
            search.deferred_cells,
            search.stop_reason,
        )
        for candidate in distinct_basins(supported, count=config.basins_per_method):
            key = point_key(candidate.east_km, candidate.north_km)
            # If both searches reached this center, retain the larger local domain.
            if key not in basins or candidate.spacing_km > basins[key].spacing_km:
                basins[key] = candidate

    finals = []
    failures = []
    for key, basin in sorted(basins.items()):
        initial = point(basin.east_km, basin.north_km)["result"]
        calibration = stage(
            key + ":calibration",
            config.calibration_seconds,
            partial(
                calibrate_position,
                observations,
                bank,
                prior,
                _bootstrap(initial["bootstrap"]),
                maximum_seconds=config.calibration_seconds,
            ),
        )
        if calibration["result"] is None:
            failures.append({"basin": key, "stage": "calibration", "reason": calibration["reason"]})
            continue
        calibrated = _calibration(calibration["result"])
        association = stage(
            key + ":association",
            config.association_seconds,
            partial(
                associate_calibration,
                observations,
                bank,
                prior,
                calibrated,
                maximum_seconds=config.association_seconds,
            ),
        )
        if association["result"] is None:
            failures.append({"basin": key, "stage": "association", "reason": association["reason"]})
            continue
        selected = association["result"]
        indices = selected["selected_indices"]
        subset = bank.select(indices)
        knots = calibrated.correction.knots_hz
        penalty = float(
            0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
        )
        for name, score in POSITION_SCORES.items():
            objective = PositionObjective(
                observations,
                subset,
                prior,
                score,
                receiver_baseline_hz=calibrated.receiver_baseline_hz,
            )
            for arm in ("fitted-c", "zero-c"):
                # Same two timing initializations for each score and RF arm.
                for start_name in ("associated", "zero-timing"):
                    start = np.asarray(selected["initial_vector"], float).copy()
                    if start_name == "zero-timing":
                        start[7:] = 0
                    receipt = stage(
                        f"{key}:{name}:{arm}:{start_name}",
                        config.final_fit_seconds,
                        partial(
                            fit_position,
                            objective,
                            start,
                            rf_arm=arm,
                            maximum_seconds=config.final_fit_seconds,
                            maximum_iterations=config.final_iterations,
                            local_center=start[:2],
                            local_radius_km=max(12.5, basin.spacing_km / np.sqrt(2)),
                        ),
                    )
                    finals.append(
                        {
                            "basin": key,
                            "method": name,
                            "arm": arm,
                            "start": start_name,
                            "fit": receipt["result"],
                            "reason": receipt["reason"],
                            "calibration_penalty": penalty,
                            "satellites": subset.numbers.tolist(),
                            "association": selected["selection"],
                        }
                    )
    points = {
        point_key(p.east_km, p.north_km): point(p.east_km, p.north_km)
        for search in searches.values()
        for p in search.evaluations
    }
    return {
        "searches": json_value(searches),
        "points": points,
        "basins": json_value(basins),
        "finals": finals,
        "failures": failures,
    }
