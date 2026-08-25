#!/usr/bin/env python3
"""Replay one resolved radio branch against one fixed satellite hypothesis.

The input is the full, non-summary JSON emitted by
``evaluate_duration_constrained_satellite_assignment.py``.  This research tool
keeps every scheduled probe, profiles one shared delay/CFO offset on a frozen
chronological prefix, and then runs the exact single-satellite semi-Markov
decoder.  It is deliberately conditional on an existing radio-only branch and
does not claim satellite specificity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    DelayProfileCandidate,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
    profile_delay_and_cfo_offset,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.doppler import doppler_shift_hz  # type: ignore[import-untyped]
from leo.sky.propagation import (  # type: ignore[import-untyped]
    ElementSetCatalogue,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid  # type: ignore[import-untyped]
from leo.sky.screening import observe_grid  # type: ignore[import-untyped]

INPUT_SCHEMA = "org.leo.research.duration-constrained-satellite-assignment-input/v1"
OUTPUT_SCHEMA = "org.leo.research.single-satellite-activity-replay/v1"


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be nonnegative")


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _refuse_qnap_output(path: Path) -> None:
    resolved = path.resolve(strict=False)
    if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
        raise ValueError("this read-only replay refuses output beneath /mnt/qnap01")


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    cell_duration_s: float = 0.1
    minimum_active_duration_s: float = 0.5
    allow_left_censored: bool = False
    allow_right_censored: bool = False
    delay_min_s: float = -2.0
    delay_max_s: float = 2.0
    delay_step_s: float = 0.05
    delay_prior_mean_s: float = 0.0
    delay_prior_sigma_s: float = 0.5
    cfo_offset_min_hz: float = -400_000.0
    cfo_offset_max_hz: float = 400_000.0
    cfo_sigma_hz: float = 65.0
    profile_fraction: float = 0.60
    detection_probability: float = 0.75
    clutter_cost: float = 4.0
    satellite_cost: float = 5.25
    episode_cost: float = 5.75
    huber_threshold: float = 1.345
    horizon_mask_deg: float = 0.0

    def __post_init__(self) -> None:
        for value, label in (
            (self.cell_duration_s, "activity-cell duration"),
            (self.minimum_active_duration_s, "minimum active duration"),
            (self.delay_step_s, "delay step"),
            (self.delay_prior_sigma_s, "delay-prior sigma"),
            (self.cfo_sigma_hz, "CFO sigma"),
            (self.huber_threshold, "Huber threshold"),
        ):
            _positive(value, label)
        for value, label in (
            (self.delay_min_s, "minimum delay"),
            (self.delay_max_s, "maximum delay"),
            (self.delay_prior_mean_s, "delay-prior mean"),
            (self.cfo_offset_min_hz, "minimum CFO offset"),
            (self.cfo_offset_max_hz, "maximum CFO offset"),
            (self.horizon_mask_deg, "horizon mask"),
        ):
            _finite(value, label)
        for value, label in (
            (self.clutter_cost, "clutter cost"),
            (self.satellite_cost, "satellite cost"),
            (self.episode_cost, "episode cost"),
        ):
            _nonnegative(value, label)
        if self.delay_min_s >= self.delay_max_s:
            raise ValueError("delay bounds must be increasing")
        delay_steps = (self.delay_max_s - self.delay_min_s) / self.delay_step_s
        if not math.isclose(delay_steps, round(delay_steps), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("delay range must be divisible by the delay step")
        if self.cfo_offset_min_hz >= self.cfo_offset_max_hz:
            raise ValueError("CFO-offset bounds must be increasing")
        if not 0.0 < self.profile_fraction <= 1.0:
            raise ValueError("profile fraction must lie in (0, 1]")
        if not 0.0 < self.detection_probability < 1.0:
            raise ValueError("detection probability must lie in (0, 1)")
        if not 0.0 <= self.horizon_mask_deg <= 90.0:
            raise ValueError("horizon mask must lie in [0, 90]")
        minimum_cells = self.minimum_active_duration_s / self.cell_duration_s
        if not math.isclose(minimum_cells, round(minimum_cells), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("minimum active duration must be a whole number of cells")

    @property
    def minimum_active_cells(self) -> int:
        return round(self.minimum_active_duration_s / self.cell_duration_s)

    def delay_grid(self) -> tuple[float, ...]:
        count = round((self.delay_max_s - self.delay_min_s) / self.delay_step_s) + 1
        return tuple(
            float(value) for value in np.linspace(self.delay_min_s, self.delay_max_s, count)
        )


def _unique_satellite_index(catalogue: ElementSetCatalogue, catalog_number: int) -> int:
    matches = [
        index
        for index, observed_number in enumerate(catalogue.satellite_numbers)
        if observed_number == catalog_number
    ]
    if len(matches) != 1:
        raise ValueError(
            f"TLE catalogue contains {len(matches)} records for NORAD {catalog_number}"
        )
    return matches[0]


def _doppler_curve(
    *,
    catalogue: ElementSetCatalogue,
    satellite_index: int,
    first_sample_utc_ns: int,
    times_s: tuple[float, ...],
    delay_s: float,
    sky_frequency_hz: float,
    observer: ObserverSiteV1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(times_s) < 3:
        raise ValueError("replay needs at least three scheduled probes")
    instants = tuple(first_sample_utc_ns + round((time_s + delay_s) * 1e9) for time_s in times_s)
    if any(second <= first for first, second in zip(instants, instants[1:], strict=False)):
        raise ValueError("prediction epochs must be strictly increasing")
    spacing_s = min(
        (second - first) / 1e9 for first, second in zip(instants, instants[1:], strict=False)
    )
    grid = SamplingGrid(instants, len(instants) // 2, spacing_s)
    propagated = propagate_grid(catalogue, grid, indices=(satellite_index,))
    if not bool(propagated.usable[0]):
        raise ValueError("requested satellite failed SGP4 propagation in the replay window")
    tracks = observe_grid(propagated, observer, grid)
    if not bool(tracks.usable[0]):
        raise ValueError("requested satellite geometry is unusable in the replay window")
    curve = np.asarray(
        doppler_shift_hz(sky_frequency_hz, tracks.range_rate_km_s[0]),
        dtype=np.float64,
    )
    return curve, tracks.elevation_deg[0], tracks.altitude_km[0]


def _activity_runs(mask: tuple[bool, ...]) -> list[dict[str, int | bool]]:
    result: list[dict[str, int | bool]] = []
    index = 0
    while index < len(mask):
        value = mask[index]
        start = index
        while index + 1 < len(mask) and mask[index + 1] == value:
            index += 1
        result.append(
            {
                "start_cell": start,
                "end_cell_exclusive": index + 1,
                "active": value,
            }
        )
        index += 1
    return result


def _rms(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.sqrt(np.mean(np.square(np.asarray(values, dtype=np.float64)))))


def replay_branch(
    *,
    dataset: dict[str, Any],
    dataset_path: Path,
    tle_path: Path,
    expected_tle_digest: str,
    catalog_number: int,
    branch_id: str,
    observer: ObserverSiteV1,
    config: ReplayConfig,
) -> dict[str, Any]:
    """Build, solve, and serialize one deterministic conditional replay."""

    if dataset.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected input schema {INPUT_SCHEMA}")
    if dataset.get("per_probe_rows_omitted"):
        raise ValueError("replay requires the full per-probe extraction")
    scheduled_rows = dataset.get("scheduled_probes")
    if not isinstance(scheduled_rows, list) or not scheduled_rows:
        raise ValueError("input has no scheduled-probe inventory")
    branches = [item for item in dataset.get("branches", ()) if item.get("branch_id") == branch_id]
    if len(branches) != 1:
        raise ValueError(f"input contains {len(branches)} branches with ID {branch_id!r}")
    branch = branches[0]
    component_id = str(branch["component_id"])
    components = [
        item
        for item in dataset.get("alias_components", ())
        if item.get("component_id") == component_id
    ]
    if len(components) != 1 or components[0].get("status") != "resolved":
        raise ValueError("selected branch does not belong to one resolved CFO component")

    actual_tle_digest = _file_digest(tle_path)
    if actual_tle_digest != expected_tle_digest:
        raise ValueError(
            f"TLE digest mismatch: observed {actual_tle_digest}, expected {expected_tle_digest}"
        )
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    satellite_index = _unique_satellite_index(catalogue, catalog_number)
    object_name = catalogue.names[satellite_index]

    capture = dataset["capture"]
    frequency = dataset["frequency_binding"]
    timing = dataset["timing_binding"]
    sample_rate_hz = int(capture["sample_rate_hz"])
    declared_sample_count = int(capture["declared_sample_count"])
    sky_frequency_hz = float(frequency["sky_frequency_hz"])
    first_sample_utc_ns = int(timing["first_estimate_utc_ns"])
    cell_samples_float = config.cell_duration_s * sample_rate_hz
    if not math.isclose(cell_samples_float, round(cell_samples_float), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("activity-cell duration is not integral at the capture sample rate")
    cell_samples = round(cell_samples_float)
    cell_count = math.ceil(declared_sample_count / cell_samples)

    ordered_scheduled = sorted(
        scheduled_rows,
        key=lambda item: (int(item["schedule_ordinal"]), str(item["probe_id"])),
    )
    ordinals = [int(item["schedule_ordinal"]) for item in ordered_scheduled]
    probe_ids = [str(item["probe_id"]) for item in ordered_scheduled]
    if ordinals != list(range(len(ordered_scheduled))) or len(set(probe_ids)) != len(probe_ids):
        raise ValueError("scheduled probes are not a complete unique ordinal sequence")

    observations = list(branch.get("observations", ()))
    observation_by_probe: dict[str, dict[str, Any]] = {}
    for observation in observations:
        if str(observation["component_id"]) != component_id:
            raise ValueError("selected branch spans independently gauged components")
        probe_id = str(observation["probe_id"])
        if probe_id in observation_by_probe:
            raise ValueError("selected branch has multiple collapsed rows in one probe")
        observation_by_probe[probe_id] = observation
    if len(observation_by_probe) < 2:
        raise ValueError("selected branch needs at least two observed probes")

    matched_base_cost = -math.log(config.detection_probability)
    missed_detection_cost = -math.log1p(-config.detection_probability)
    probes = []
    prediction_times = []
    schedule_by_id: dict[str, dict[str, Any]] = {}
    for row in ordered_scheduled:
        probe_id = str(row["probe_id"])
        schedule_by_id[probe_id] = row
        sample_start = int(row["probe_sample_start"])
        cell_index = sample_start // cell_samples
        observation = observation_by_probe.get(probe_id)
        time_s = (
            float(observation["measurement_time_s"])
            if observation is not None
            else float(row["probe_start_time_s"])
        )
        usable = bool(row["usable_for_activity"])
        probes.append(
            CfoProbe(
                probe_id=probe_id,
                time_s=time_s,
                cell_index=cell_index,
                missed_detection_cost=missed_detection_cost if usable else 0.0,
                usable=usable,
            )
        )
        prediction_times.append(time_s)
    unknown_observation_probes = sorted(set(observation_by_probe) - set(schedule_by_id))
    if unknown_observation_probes:
        raise ValueError("selected branch refers to probes outside the scheduled inventory")

    times_s = tuple(prediction_times)
    delay_curves: dict[float, np.ndarray] = {}
    geometry_by_delay: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for delay_s in config.delay_grid():
        curve, elevation, altitude = _doppler_curve(
            catalogue=catalogue,
            satellite_index=satellite_index,
            first_sample_utc_ns=first_sample_utc_ns,
            times_s=times_s,
            delay_s=delay_s,
            sky_frequency_hz=sky_frequency_hz,
            observer=observer,
        )
        delay_curves[delay_s] = curve
        geometry_by_delay[delay_s] = (elevation, altitude)

    probe_index = {probe_id: index for index, probe_id in enumerate(probe_ids)}
    ordered_observations = sorted(
        observations,
        key=lambda item: (float(item["measurement_time_s"]), str(item["source_observation_id"])),
    )
    observation_indices = [probe_index[str(item["probe_id"])] for item in ordered_observations]
    observed_cfo: npt.NDArray[np.float64] = np.asarray(
        [float(item["component_cfo_hz"]) for item in ordered_observations], dtype=np.float64
    )
    observation_count = len(ordered_observations)
    if observation_count >= 3 and config.profile_fraction < 1.0:
        training_count = min(
            observation_count - 1,
            max(2, math.floor(observation_count * config.profile_fraction)),
        )
    else:
        training_count = observation_count
    training_indices = observation_indices[:training_count]
    profile = profile_delay_and_cfo_offset(
        observed_cfo[:training_count],
        np.full(training_count, config.cfo_sigma_hz, dtype=np.float64),
        tuple(
            DelayProfileCandidate(
                delay_s=delay_s,
                predicted_cfo_hz=tuple(
                    float(delay_curves[delay_s][index]) for index in training_indices
                ),
            )
            for delay_s in config.delay_grid()
        ),
        delay_prior_mean_s=config.delay_prior_mean_s,
        delay_prior_sigma_s=config.delay_prior_sigma_s,
        huber_threshold=config.huber_threshold,
        cfo_offset_bounds_hz=(config.cfo_offset_min_hz, config.cfo_offset_max_hz),
    )
    best = profile.posterior_best
    best_curve = delay_curves[best.delay_s]
    best_elevation, best_altitude = geometry_by_delay[best.delay_s]
    if float(np.min(best_elevation)) <= config.horizon_mask_deg:
        raise ValueError(
            "requested satellite is not above the replay horizon mask for the full window"
        )

    candidates = []
    for item in ordered_observations:
        probe_id = str(item["probe_id"])
        source_observation_id = str(item["source_observation_id"])
        row = schedule_by_id[probe_id]
        if not bool(row["usable_for_activity"]):
            raise ValueError("selected branch contains evidence from an unusable probe")
        candidates.append(
            CfoCandidate(
                observation_id=source_observation_id,
                probe_id=probe_id,
                exclusion_group_id=source_observation_id,
                cfo_hz=float(item["component_cfo_hz"]),
                sigma_hz=config.cfo_sigma_hz,
                clutter_cost=config.clutter_cost,
                matched_base_cost=matched_base_cost,
                component_id=component_id,
            )
        )
    problem = SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=0.0,
            cell_duration_s=config.cell_duration_s,
            cell_count=cell_count,
            minimum_active_cells=config.minimum_active_cells,
            allow_left_censored=config.allow_left_censored,
            allow_right_censored=config.allow_right_censored,
        ),
        probes=tuple(probes),
        observations=tuple(candidates),
        costs=AssociationCostModel(
            satellite_cost=config.satellite_cost,
            episode_cost=config.episode_cost,
            huber_threshold=config.huber_threshold,
        ),
        truncated_observation_count=sum(
            int(row["truncated_candidate_count"]) for row in ordered_scheduled
        ),
    )
    hypothesis_id = canonical_digest(
        {
            "branch_id": branch_id,
            "catalog_number": catalog_number,
            "delay_s": best.delay_s,
            "cfo_offset_hz": best.fitted_cfo_offset_hz,
            "component_id": component_id,
            "config": asdict(config),
        }
    )
    hypothesis = SingleSatelliteHypothesis(
        hypothesis_id=hypothesis_id,
        object_name=object_name,
        catalog_number=catalog_number,
        delay_s=best.delay_s,
        cfo_offset_hz=best.fitted_cfo_offset_hz,
        delay_prior_cost=best.delay_prior_cost,
        predictions=tuple(
            PredictedProbeCfo(probe_id=probe_id, cfo_hz=float(best_curve[index]))
            for index, probe_id in enumerate(probe_ids)
        ),
    )
    result = decode_single_satellite(problem, hypothesis)

    residual_by_observation = {
        str(item["source_observation_id"]): float(item["component_cfo_hz"])
        - (float(best_curve[probe_index[str(item["probe_id"])]]) + best.fitted_cfo_offset_hz)
        for item in ordered_observations
    }
    training_ids = {
        str(item["source_observation_id"]) for item in ordered_observations[:training_count]
    }
    training_residuals = [
        residual_by_observation[observation_id] for observation_id in sorted(training_ids)
    ]
    holdout_residuals = [
        residual_by_observation[str(item["source_observation_id"])]
        for item in ordered_observations[training_count:]
    ]
    element_epoch_utc_ns = catalogue.element_epoch_utc_ns()[satellite_index]

    return {
        "schema": OUTPUT_SCHEMA,
        "candidate_only": True,
        "specificity_claimed": False,
        "conditional_on_dealiased_branch": True,
        "costs_calibrated": False,
        "payload_decoded": False,
        "input": {
            "path": str(dataset_path.resolve()),
            "file_digest": _file_digest(dataset_path),
            "schema": dataset["schema"],
            "capture": capture,
            "frequency_binding": frequency,
            "timing_binding": timing,
            "source_products": dataset.get("source_products", {}),
        },
        "tle": {
            "path": str(tle_path.resolve()),
            "file_digest": actual_tle_digest,
            "catalog_number": catalog_number,
            "object_name": object_name,
            "element_epoch_utc_ns": element_epoch_utc_ns,
            "element_age_at_first_sample_s": (first_sample_utc_ns - element_epoch_utc_ns) / 1e9,
        },
        "observer": {
            **observer.model_dump(mode="json"),
            "capture_bound": False,
        },
        "config": {
            **asdict(config),
            "config_digest": canonical_digest(asdict(config)),
            "matched_base_cost": matched_base_cost,
            "missed_detection_cost": missed_detection_cost,
            "prediction_epoch_method": (
                "branch local measurement epoch when observed; scheduled probe start otherwise"
            ),
        },
        "branch": {
            "branch_id": branch_id,
            "component_id": component_id,
            "component_status": components[0]["status"],
            "source_probe_count": int(branch["source_probe_count"]),
            "scheduled_probe_count": len(probes),
            "usable_scheduled_probe_count": sum(probe.usable for probe in probes),
            "unusable_scheduled_probe_count": sum(not probe.usable for probe in probes),
            "source_truncated_candidate_count": problem.truncated_observation_count,
        },
        "geometry": {
            "horizon_mask_deg": config.horizon_mask_deg,
            "minimum_elevation_deg": float(np.min(best_elevation)),
            "maximum_elevation_deg": float(np.max(best_elevation)),
            "minimum_altitude_km": float(np.min(best_altitude)),
            "maximum_altitude_km": float(np.max(best_altitude)),
            "eligible_for_full_replay_window": True,
        },
        "profile": {
            "split": "chronological-prefix",
            "training_observation_count": training_count,
            "holdout_observation_count": observation_count - training_count,
            "training_rms_hz": _rms(training_residuals),
            "holdout_rms_hz": _rms(holdout_residuals),
            "data_only_best_delay_s": profile.data_only_best.delay_s,
            "posterior_best_delay_s": best.delay_s,
            "posterior_best_cfo_offset_hz": best.fitted_cfo_offset_hz,
            "data_cost_span": profile.data_cost_span,
            "data_flat": profile.data_flat,
            "data_ambiguous": profile.data_ambiguous,
            "posterior_differs_from_data_only": profile.posterior_differs_from_data_only,
            "delay_prior_dominated": profile.delay_prior_dominated,
            "posterior_at_delay_boundary": profile.posterior_at_delay_boundary,
            "offset_at_bound": best.offset_at_bound,
            "points": [asdict(item) for item in profile.points],
        },
        "activity": {
            "algorithm": result.algorithm,
            "exact_for_fixed_hypothesis": result.exact,
            "selected": result.selected,
            "hypothesis_id": result.hypothesis_id,
            "activity_runs": _activity_runs(result.activity_by_cell),
            "episodes": [asdict(item) for item in result.episodes],
            "assignments": [
                {
                    **asdict(item),
                    "residual_hz": residual_by_observation[item.observation_id],
                }
                for item in result.assignments
            ],
            "missed_probe_ids": list(result.missed_probe_ids),
            "unexplained_observation_ids": list(result.unexplained_observation_ids),
            "objective": asdict(result.objective),
        },
        "interpretation": {
            "claim": "conditional activity replay only",
            "limitations": [
                "radio branch was selected before this replay",
                "costs are explicit prototype settings, not calibrated posterior odds",
                "delay and CFO offset can be nearly collinear on short arcs",
                "observer coordinates are not capture-bound",
                "one fixed satellite was evaluated; catalogue specificity was not tested here",
            ],
        },
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument("--catalog-number", type=int, required=True)
    parser.add_argument("--branch-id", required=True)
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--cell-duration-s", type=float, default=0.1)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--allow-left-censored", action="store_true")
    parser.add_argument("--allow-right-censored", action="store_true")
    parser.add_argument("--delay-min-s", type=float, default=-2.0)
    parser.add_argument("--delay-max-s", type=float, default=2.0)
    parser.add_argument("--delay-step-s", type=float, default=0.05)
    parser.add_argument("--delay-prior-mean-s", type=float, default=0.0)
    parser.add_argument("--delay-prior-sigma-s", type=float, default=0.5)
    parser.add_argument("--cfo-offset-min-hz", type=float, default=-400_000.0)
    parser.add_argument("--cfo-offset-max-hz", type=float, default=400_000.0)
    parser.add_argument("--cfo-sigma-hz", type=float, default=65.0)
    parser.add_argument("--profile-fraction", type=float, default=0.60)
    parser.add_argument("--detection-probability", type=float, default=0.75)
    parser.add_argument("--clutter-cost", type=float, default=4.0)
    parser.add_argument("--satellite-cost", type=float, default=5.25)
    parser.add_argument("--episode-cost", type=float, default=5.75)
    parser.add_argument("--huber-threshold", type=float, default=1.345)
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    expected_tle_digest = arguments.tle_sha256
    if not expected_tle_digest.startswith("sha256:"):
        expected_tle_digest = f"sha256:{expected_tle_digest}"
    config = ReplayConfig(
        cell_duration_s=arguments.cell_duration_s,
        minimum_active_duration_s=arguments.minimum_active_duration_s,
        allow_left_censored=arguments.allow_left_censored,
        allow_right_censored=arguments.allow_right_censored,
        delay_min_s=arguments.delay_min_s,
        delay_max_s=arguments.delay_max_s,
        delay_step_s=arguments.delay_step_s,
        delay_prior_mean_s=arguments.delay_prior_mean_s,
        delay_prior_sigma_s=arguments.delay_prior_sigma_s,
        cfo_offset_min_hz=arguments.cfo_offset_min_hz,
        cfo_offset_max_hz=arguments.cfo_offset_max_hz,
        cfo_sigma_hz=arguments.cfo_sigma_hz,
        profile_fraction=arguments.profile_fraction,
        detection_probability=arguments.detection_probability,
        clutter_cost=arguments.clutter_cost,
        satellite_cost=arguments.satellite_cost,
        episode_cost=arguments.episode_cost,
        huber_threshold=arguments.huber_threshold,
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    dataset = _read_json(arguments.input)
    document = replay_branch(
        dataset=dataset,
        dataset_path=arguments.input,
        tle_path=arguments.tle,
        expected_tle_digest=expected_tle_digest,
        catalog_number=arguments.catalog_number,
        branch_id=arguments.branch_id,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
    )
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        _refuse_qnap_output(arguments.output)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
