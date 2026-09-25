#!/usr/bin/env python3
"""Replay one resolved CFO component against two or three fixed satellites.

This read-only research adapter consumes the full JSON emitted by
``evaluate_duration_constrained_satellite_assignment.py``.  It pools every
branch observation in one resolved component, deduplicates physical source
observations, keeps every scheduled probe in one explicit half-open time
window, and invokes the bounded exact joint decoder for an explicitly supplied
set of fixed satellite/delay/CFO hypotheses.

The result is conditional on the chosen component, catalogue objects, nuisance
parameters, observer, and provisional costs.  It is not a catalogue search or
spacecraft-identification product.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.multi_satellite_activity import (  # type: ignore[import-untyped]
    JointSatelliteSchedule,
    decode_joint_fixed_hypotheses,
    evaluate_joint_satellite_schedule,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
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
OUTPUT_SCHEMA = "org.leo.research.joint-fixed-satellite-activity-replay/v1"


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
class FixedHypothesisSpec:
    """One fully specified satellite nuisance-parameter state."""

    catalog_number: int
    delay_s: float
    cfo_offset_hz: float
    delay_prior_cost: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.catalog_number, bool)
            or not isinstance(self.catalog_number, int)
            or self.catalog_number <= 0
        ):
            raise ValueError("catalog number must be a positive integer")
        _finite(self.delay_s, "hypothesis delay")
        _finite(self.cfo_offset_hz, "hypothesis CFO offset")
        _nonnegative(self.delay_prior_cost, "hypothesis delay-prior cost")


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    """Explicit provisional costs and activity-grid settings."""

    cell_duration_s: float = 0.1
    minimum_active_duration_s: float = 0.5
    allow_left_censored: bool = False
    allow_right_censored: bool = False
    cfo_sigma_hz: float = 100.0
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
            (self.cfo_sigma_hz, "CFO sigma"),
            (self.huber_threshold, "Huber threshold"),
        ):
            _positive(value, label)
        for value, label in (
            (self.clutter_cost, "clutter cost"),
            (self.satellite_cost, "satellite cost"),
            (self.episode_cost, "episode cost"),
        ):
            _nonnegative(value, label)
        _finite(self.horizon_mask_deg, "horizon mask")
        if not 0.0 <= self.horizon_mask_deg <= 90.0:
            raise ValueError("horizon mask must lie in [0, 90]")
        if not 0.0 < self.detection_probability < 1.0:
            raise ValueError("detection probability must lie in (0, 1)")
        minimum_cells = self.minimum_active_duration_s / self.cell_duration_s
        if not math.isclose(minimum_cells, round(minimum_cells), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("minimum active duration must be a whole number of cells")

    @property
    def minimum_active_cells(self) -> int:
        return round(self.minimum_active_duration_s / self.cell_duration_s)


@dataclass(frozen=True, slots=True)
class _PooledObservation:
    row: dict[str, Any]
    branch_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _WindowInventory:
    rows: tuple[dict[str, Any], ...]
    start_sample: int
    end_sample: int
    cell_samples: int
    cell_count: int


def _parse_hypothesis(value: str) -> FixedHypothesisSpec:
    fields = [item.strip() for item in value.split(",")]
    if len(fields) not in {3, 4} or any(not item for item in fields):
        raise argparse.ArgumentTypeError(
            "hypothesis must be CATALOG,DELAY_S,CFO_OFFSET_HZ[,DELAY_PRIOR_COST]"
        )
    try:
        catalog_number = int(fields[0])
        delay_s = float(fields[1])
        cfo_offset_hz = float(fields[2])
        delay_prior_cost = 0.0 if len(fields) == 3 else float(fields[3])
        return FixedHypothesisSpec(
            catalog_number=catalog_number,
            delay_s=delay_s,
            cfo_offset_hz=cfo_offset_hz,
            delay_prior_cost=delay_prior_cost,
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


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
    scheduled_times_s: tuple[float, ...],
    delay_s: float,
    sky_frequency_hz: float,
    observer: ObserverSiteV1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(scheduled_times_s) < 2:
        raise ValueError("joint replay needs at least two scheduled probes in its window")
    instants = tuple(
        first_sample_utc_ns + round((time_s + delay_s) * 1e9) for time_s in scheduled_times_s
    )
    differences_s = tuple(
        (second - first) / 1e9 for first, second in zip(instants, instants[1:], strict=False)
    )
    if any(value <= 0.0 for value in differences_s):
        raise ValueError("scheduled prediction epochs must be strictly increasing")
    grid = SamplingGrid(instants, len(instants) // 2, min(differences_s))
    propagated = propagate_grid(catalogue, grid, indices=(satellite_index,))
    if not bool(propagated.usable[0]):
        raise ValueError("a requested satellite failed SGP4 propagation in the replay window")
    tracks = observe_grid(propagated, observer, grid)
    if not bool(tracks.usable[0]):
        raise ValueError("a requested satellite has unusable geometry in the replay window")
    curve = np.asarray(
        doppler_shift_hz(sky_frequency_hz, tracks.range_rate_km_s[0]),
        dtype=np.float64,
    )
    return curve, tracks.elevation_deg[0], tracks.altitude_km[0]


def _validate_full_input(dataset: dict[str, Any]) -> None:
    if dataset.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected input schema {INPUT_SCHEMA}")
    if dataset.get("per_probe_rows_omitted"):
        raise ValueError("joint replay requires the full per-probe extraction")
    scheduled = dataset.get("scheduled_probes")
    branches = dataset.get("branches")
    components = dataset.get("alias_components")
    if not isinstance(scheduled, list) or not scheduled:
        raise ValueError("input has no scheduled-probe inventory")
    if not isinstance(branches, list) or not isinstance(components, list):
        raise ValueError("input has no complete branch/component inventory")
    truncated_probes = [
        str(item.get("probe_id", ""))
        for item in scheduled
        if int(item.get("truncated_candidate_count", 0)) != 0
    ]
    if truncated_probes:
        raise ValueError("joint replay refuses truncated scheduled-candidate inputs")
    frame_inventory = dataset.get("frame_evidence_inventory")
    if isinstance(frame_inventory, dict) and (
        int(frame_inventory.get("alias_expanded_truncated_track_count", 0)) != 0
        or frame_inventory.get("evidence_complete") is False
    ):
        raise ValueError("joint replay refuses inputs with declared frame-track truncation")


def _ordered_schedule(dataset: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = tuple(
        sorted(
            dataset["scheduled_probes"],
            key=lambda item: (int(item["schedule_ordinal"]), str(item["probe_id"])),
        )
    )
    ordinals = [int(item["schedule_ordinal"]) for item in rows]
    probe_ids = [str(item["probe_id"]) for item in rows]
    sample_starts = [int(item["probe_sample_start"]) for item in rows]
    if ordinals != list(range(len(rows))):
        raise ValueError("scheduled probes are not a complete ordinal sequence")
    if len(set(probe_ids)) != len(probe_ids):
        raise ValueError("scheduled probe IDs are not unique")
    if sample_starts != sorted(sample_starts) or len(set(sample_starts)) != len(sample_starts):
        raise ValueError("scheduled probe sample starts are not unique and increasing")
    return rows


def _window_inventory(
    *,
    dataset: dict[str, Any],
    ordered_schedule: tuple[dict[str, Any], ...],
    start_s: float,
    end_s: float,
    config: ReplayConfig,
) -> _WindowInventory:
    _finite(start_s, "window start")
    _finite(end_s, "window end")
    if start_s < 0.0 or end_s <= start_s:
        raise ValueError("replay window must be finite, nonnegative, and increasing")
    capture = dataset["capture"]
    sample_rate_hz = int(capture["sample_rate_hz"])
    declared_sample_count = int(capture["declared_sample_count"])
    cell_samples_value = config.cell_duration_s * sample_rate_hz
    start_sample_value = start_s * sample_rate_hz
    end_sample_value = end_s * sample_rate_hz
    for value, label in (
        (cell_samples_value, "activity-cell duration"),
        (start_sample_value, "window start"),
        (end_sample_value, "window end"),
    ):
        if not math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"{label} is not integral at the capture sample rate")
    cell_samples = round(cell_samples_value)
    start_sample = round(start_sample_value)
    end_sample = round(end_sample_value)
    if end_sample > declared_sample_count:
        raise ValueError("replay window extends beyond the declared capture")
    if start_sample % cell_samples != 0 or end_sample % cell_samples != 0:
        raise ValueError("replay-window boundaries must align to the capture activity-cell grid")
    if (end_sample - start_sample) % cell_samples != 0:
        raise ValueError("replay window must contain a whole number of activity cells")
    rows = tuple(
        item
        for item in ordered_schedule
        if start_sample <= int(item["probe_sample_start"]) < end_sample
    )
    if len(rows) < 2:
        raise ValueError("joint replay window contains fewer than two scheduled probes")
    for row in rows:
        scheduled_time_s = float(row["probe_start_time_s"])
        expected_time_s = int(row["probe_sample_start"]) / sample_rate_hz
        if not math.isclose(scheduled_time_s, expected_time_s, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("scheduled probe time disagrees with its sample start")
    return _WindowInventory(
        rows=rows,
        start_sample=start_sample,
        end_sample=end_sample,
        cell_samples=cell_samples,
        cell_count=(end_sample - start_sample) // cell_samples,
    )


def _observation_identity(row: dict[str, Any]) -> tuple[object, ...]:
    return (
        str(row["component_id"]),
        str(row["probe_id"]),
        int(row["probe_sample_start"]),
        int(row["measurement_sample"]),
        float(row["measurement_time_s"]),
        int(row["candidate_rank"]),
        int(row["local_epoch_sample"]),
        float(row["source_tracking_cfo_hz"]),
        float(row["component_cfo_hz"]),
    )


def _pool_component_observations(
    dataset: dict[str, Any],
    component_id: str,
) -> tuple[tuple[_PooledObservation, ...], tuple[str, ...], int]:
    components = [
        item
        for item in dataset["alias_components"]
        if str(item.get("component_id")) == component_id
    ]
    if len(components) != 1:
        raise ValueError(f"input contains {len(components)} components with ID {component_id!r}")
    component = components[0]
    if component.get("status") != "resolved":
        raise ValueError("joint replay requires one resolved CFO component")

    declared_owners: dict[str, set[str]] = defaultdict(set)
    for item in dataset["alias_components"]:
        for branch_id in item.get("branch_ids", ()):
            declared_owners[str(branch_id)].add(str(item.get("component_id")))
    selected_declared_branch_ids = {str(item) for item in component.get("branch_ids", ())}
    if any(
        declared_owners[branch_id] != {component_id} for branch_id in selected_declared_branch_ids
    ):
        raise ValueError("selected branch is declared in more than one CFO component")

    selected_branches = [
        item for item in dataset["branches"] if str(item.get("component_id")) == component_id
    ]
    selected_branch_ids = tuple(sorted(str(item["branch_id"]) for item in selected_branches))
    declared_branch_ids = tuple(sorted(str(item) for item in component.get("branch_ids", ())))
    if not selected_branch_ids or selected_branch_ids != declared_branch_ids:
        raise ValueError("resolved component and branch inventories disagree")

    schedule_ids = {str(item["probe_id"]) for item in dataset["scheduled_probes"]}
    rows_by_source: dict[str, dict[str, Any]] = {}
    branches_by_source: dict[str, set[str]] = defaultdict(set)
    raw_row_count = 0
    for branch in sorted(selected_branches, key=lambda item: str(item["branch_id"])):
        branch_id = str(branch["branch_id"])
        observations = branch.get("observations", ())
        if int(branch.get("source_probe_count", len(observations))) != len(observations):
            raise ValueError("component branch observation accounting is inconsistent")
        for row in sorted(
            observations,
            key=lambda item: (
                str(item["source_observation_id"]),
                str(item["probe_id"]),
            ),
        ):
            raw_row_count += 1
            if str(row.get("branch_id")) != branch_id:
                raise ValueError("component branch contains an observation owned by another branch")
            if str(row.get("component_id")) != component_id:
                raise ValueError("selected component contains a cross-component observation")
            probe_id = str(row["probe_id"])
            if probe_id not in schedule_ids:
                raise ValueError("component observation refers to an unscheduled probe")
            source_id = str(row["source_observation_id"])
            if not source_id:
                raise ValueError("component observation has an empty source observation ID")
            previous = rows_by_source.get(source_id)
            if previous is not None and _observation_identity(previous) != _observation_identity(
                row
            ):
                raise ValueError("duplicate source observation rows disagree across branches")
            rows_by_source.setdefault(source_id, row)
            branches_by_source[source_id].add(branch_id)

    selected_source_ids = set(rows_by_source)
    for branch in dataset["branches"]:
        if str(branch.get("component_id")) == component_id:
            continue
        for row in branch.get("observations", ()):
            if str(row.get("source_observation_id")) in selected_source_ids:
                raise ValueError("one source observation is reused across CFO components")

    pooled = tuple(
        _PooledObservation(rows_by_source[source_id], tuple(sorted(branches_by_source[source_id])))
        for source_id in sorted(rows_by_source)
    )
    return pooled, selected_branch_ids, raw_row_count


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


def replay_window(
    *,
    dataset: dict[str, Any],
    dataset_path: Path,
    tle_path: Path,
    expected_tle_digest: str,
    component_id: str,
    start_s: float,
    end_s: float,
    hypothesis_specs: tuple[FixedHypothesisSpec, ...],
    observer: ObserverSiteV1,
    config: ReplayConfig,
) -> dict[str, Any]:
    """Build, exactly solve, independently check, and serialize one joint replay."""

    _validate_full_input(dataset)
    if not 2 <= len(hypothesis_specs) <= 3:
        raise ValueError("joint replay requires two or three explicit fixed hypotheses")
    catalog_numbers = tuple(item.catalog_number for item in hypothesis_specs)
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("joint replay accepts only one fixed hypothesis per catalog number")

    actual_tle_digest = _file_digest(tle_path)
    if actual_tle_digest != expected_tle_digest:
        raise ValueError(
            f"TLE digest mismatch: observed {actual_tle_digest}, expected {expected_tle_digest}"
        )
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    ordered_specs = tuple(sorted(hypothesis_specs, key=lambda item: item.catalog_number))
    satellite_indices = {
        item.catalog_number: _unique_satellite_index(catalogue, item.catalog_number)
        for item in ordered_specs
    }

    schedule = _ordered_schedule(dataset)
    window = _window_inventory(
        dataset=dataset,
        ordered_schedule=schedule,
        start_s=start_s,
        end_s=end_s,
        config=config,
    )
    pooled, branch_ids, raw_component_row_count = _pool_component_observations(
        dataset, component_id
    )
    window_probe_ids = {str(item["probe_id"]) for item in window.rows}
    window_pooled = tuple(item for item in pooled if str(item.row["probe_id"]) in window_probe_ids)
    schedule_by_id = {str(item["probe_id"]): item for item in window.rows}

    matched_base_cost = -math.log(config.detection_probability)
    missed_detection_cost = -math.log1p(-config.detection_probability)
    probes = tuple(
        CfoProbe(
            probe_id=str(row["probe_id"]),
            time_s=float(row["probe_start_time_s"]),
            cell_index=(int(row["probe_sample_start"]) - window.start_sample)
            // window.cell_samples,
            missed_detection_cost=(
                missed_detection_cost if bool(row["usable_for_activity"]) else 0.0
            ),
            usable=bool(row["usable_for_activity"]),
        )
        for row in window.rows
    )
    candidates = []
    source_branches: dict[str, tuple[str, ...]] = {}
    local_epoch_offsets_s = []
    for pooled_observation in window_pooled:
        row = pooled_observation.row
        probe_id = str(row["probe_id"])
        if not bool(schedule_by_id[probe_id]["usable_for_activity"]):
            raise ValueError("component evidence occurs in an unusable scheduled probe")
        source_id = str(row["source_observation_id"])
        candidates.append(
            CfoCandidate(
                observation_id=source_id,
                probe_id=probe_id,
                exclusion_group_id=source_id,
                cfo_hz=float(row["component_cfo_hz"]),
                sigma_hz=config.cfo_sigma_hz,
                clutter_cost=config.clutter_cost,
                matched_base_cost=matched_base_cost,
                component_id=component_id,
            )
        )
        source_branches[source_id] = pooled_observation.branch_ids
        local_epoch_offsets_s.append(
            float(row["measurement_time_s"]) - float(schedule_by_id[probe_id]["probe_start_time_s"])
        )

    problem = SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=start_s,
            cell_duration_s=config.cell_duration_s,
            cell_count=window.cell_count,
            minimum_active_cells=config.minimum_active_cells,
            allow_left_censored=config.allow_left_censored,
            allow_right_censored=config.allow_right_censored,
        ),
        probes=probes,
        observations=tuple(candidates),
        costs=AssociationCostModel(
            satellite_cost=config.satellite_cost,
            episode_cost=config.episode_cost,
            huber_threshold=config.huber_threshold,
        ),
        truncated_observation_count=0,
    )

    capture = dataset["capture"]
    frequency = dataset["frequency_binding"]
    timing = dataset["timing_binding"]
    first_sample_utc_ns = int(timing["first_estimate_utc_ns"])
    sky_frequency_hz = float(frequency["sky_frequency_hz"])
    scheduled_times_s = tuple(float(item["probe_start_time_s"]) for item in window.rows)
    hypotheses = []
    predictions_by_hypothesis: dict[str, dict[str, float]] = {}
    geometry_by_hypothesis: dict[str, dict[str, float | bool]] = {}
    element_by_catalog: dict[int, dict[str, Any]] = {}
    for spec in ordered_specs:
        satellite_index = satellite_indices[spec.catalog_number]
        curve, elevation, altitude = _doppler_curve(
            catalogue=catalogue,
            satellite_index=satellite_index,
            first_sample_utc_ns=first_sample_utc_ns,
            scheduled_times_s=scheduled_times_s,
            delay_s=spec.delay_s,
            sky_frequency_hz=sky_frequency_hz,
            observer=observer,
        )
        minimum_elevation_deg = float(np.min(elevation))
        if minimum_elevation_deg <= config.horizon_mask_deg:
            raise ValueError(
                f"NORAD {spec.catalog_number} is not above the {config.horizon_mask_deg:g} "
                "degree horizon mask for the full replay window"
            )
        object_name = catalogue.names[satellite_index]
        hypothesis_id = canonical_digest(
            {
                "component_id": component_id,
                "window": {"start_s": start_s, "end_s": end_s},
                "tle_digest": actual_tle_digest,
                "observer": observer.model_dump(mode="json"),
                "spec": asdict(spec),
                "config": asdict(config),
            }
        )
        hypothesis = SingleSatelliteHypothesis(
            hypothesis_id=hypothesis_id,
            object_name=object_name,
            catalog_number=spec.catalog_number,
            delay_s=spec.delay_s,
            cfo_offset_hz=spec.cfo_offset_hz,
            delay_prior_cost=spec.delay_prior_cost,
            predictions=tuple(
                PredictedProbeCfo(str(row["probe_id"]), float(curve[index]))
                for index, row in enumerate(window.rows)
            ),
        )
        hypotheses.append(hypothesis)
        predictions_by_hypothesis[hypothesis_id] = {
            str(row["probe_id"]): float(curve[index]) for index, row in enumerate(window.rows)
        }
        geometry_by_hypothesis[hypothesis_id] = {
            "minimum_elevation_deg": minimum_elevation_deg,
            "maximum_elevation_deg": float(np.max(elevation)),
            "minimum_altitude_km": float(np.min(altitude)),
            "maximum_altitude_km": float(np.max(altitude)),
            "horizon_mask_deg": config.horizon_mask_deg,
            "eligible_for_full_replay_window": True,
            "full_window_horizon_gate_applied": True,
            "visibility_mask_applied": False,
        }
        element_epoch_utc_ns = catalogue.element_epoch_utc_ns()[satellite_index]
        element_by_catalog[spec.catalog_number] = {
            "catalog_number": spec.catalog_number,
            "object_name": object_name,
            "element_epoch_utc_ns": element_epoch_utc_ns,
            "element_age_at_window_start_s": (
                first_sample_utc_ns + round(start_s * 1e9) - element_epoch_utc_ns
            )
            / 1e9,
        }

    hypothesis_tuple = tuple(hypotheses)
    result = decode_joint_fixed_hypotheses(problem, hypothesis_tuple)
    schedules = tuple(
        JointSatelliteSchedule(
            hypothesis_id=item.hypothesis_id,
            activity_by_cell=item.activity_by_cell,
            assignments=item.assignments,
        )
        for item in result.satellites
    )
    checked = evaluate_joint_satellite_schedule(
        problem,
        hypothesis_tuple,
        schedules,
        algorithm=result.algorithm,
        exact=result.exact,
    )
    if checked != result:
        raise RuntimeError("joint decoder result disagrees with the independent objective checker")

    observation_by_id = {item.observation_id: item for item in problem.observations}
    satellites = []
    for item in result.satellites:
        prediction = predictions_by_hypothesis[item.hypothesis_id]
        assignments = []
        for assignment in item.assignments:
            observation = observation_by_id[assignment.observation_id]
            predicted_cfo_hz = prediction[assignment.probe_id] + item.cfo_offset_hz
            assignments.append(
                {
                    **asdict(assignment),
                    "source_branch_ids": list(source_branches[assignment.observation_id]),
                    "observed_component_cfo_hz": observation.cfo_hz,
                    "predicted_component_cfo_hz": predicted_cfo_hz,
                    "residual_hz": observation.cfo_hz - predicted_cfo_hz,
                }
            )
        episodes = [
            {
                **asdict(episode),
                "start_s": start_s + episode.start_cell * config.cell_duration_s,
                "end_s": start_s + episode.end_cell_exclusive * config.cell_duration_s,
            }
            for episode in item.episodes
        ]
        satellites.append(
            {
                "hypothesis_id": item.hypothesis_id,
                "object_name": item.object_name,
                "catalog_number": item.catalog_number,
                "delay_s": item.delay_s,
                "cfo_offset_hz": item.cfo_offset_hz,
                "delay_prior_cost": next(
                    value.delay_prior_cost
                    for value in hypothesis_tuple
                    if value.hypothesis_id == item.hypothesis_id
                ),
                "parameters_fitted_by_replay": False,
                "selected": item.selected,
                "geometry": geometry_by_hypothesis[item.hypothesis_id],
                "activity_runs": _activity_runs(item.activity_by_cell),
                "episodes": episodes,
                "assignments": assignments,
                "missed_probe_ids": list(item.missed_probe_ids),
            }
        )

    raw_window_row_count = sum(
        1
        for branch in dataset["branches"]
        if str(branch.get("component_id")) == component_id
        for row in branch.get("observations", ())
        if str(row["probe_id"]) in window_probe_ids
    )
    local_min = min(local_epoch_offsets_s) if local_epoch_offsets_s else None
    local_max = max(local_epoch_offsets_s) if local_epoch_offsets_s else None
    local_max_abs = (
        max(abs(value) for value in local_epoch_offsets_s) if local_epoch_offsets_s else None
    )
    config_document = {
        **asdict(config),
        "minimum_active_cells": config.minimum_active_cells,
        "matched_base_cost": matched_base_cost,
        "missed_detection_cost": missed_detection_cost,
    }
    return {
        "schema": OUTPUT_SCHEMA,
        "candidate_only": True,
        "specificity_claimed": False,
        "satellite_identification_claimed": False,
        "catalogue_search_performed": False,
        "conditional_on_resolved_component": True,
        "conditional_on_explicit_fixed_hypotheses": True,
        "parameters_fitted": False,
        "costs_calibrated": False,
        "activity_probability_claimed": False,
        "unknown_satellite_count_solved": False,
        "handover_claimed": False,
        "continuous_transmission_claimed": False,
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
            "snapshot_causality_verified": False,
            "elements": [element_by_catalog[item.catalog_number] for item in ordered_specs],
        },
        "observer": {
            **observer.model_dump(mode="json"),
            "capture_bound": False,
        },
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "endpoint_convention": "half-open [start_s, end_s)",
            "start_sample": window.start_sample,
            "end_sample_exclusive": window.end_sample,
            "activity_cell_count": window.cell_count,
            "scheduled_probe_count": len(probes),
            "usable_scheduled_probe_count": sum(item.usable for item in probes),
            "unusable_scheduled_probe_count": sum(not item.usable for item in probes),
        },
        "component": {
            "component_id": component_id,
            "status": "resolved",
            "branch_ids": list(branch_ids),
            "branch_count": len(branch_ids),
            "raw_branch_observation_row_count": raw_component_row_count,
            "deduplicated_source_observation_count": len(pooled),
            "duplicate_source_observation_row_count": raw_component_row_count - len(pooled),
            "window_raw_branch_observation_row_count": raw_window_row_count,
            "window_deduplicated_source_observation_count": len(window_pooled),
            "window_duplicate_source_observation_row_count": (
                raw_window_row_count - len(window_pooled)
            ),
            "source_observation_id_is_exclusion_group": True,
            "cross_component_observations_allowed": False,
            "truncated_observations_allowed": False,
        },
        "timing_approximation": {
            "prediction_epoch": "scheduled probe start",
            "candidate_local_epoch_applied": False,
            "window_candidate_count": len(local_epoch_offsets_s),
            "minimum_candidate_local_epoch_offset_s": local_min,
            "maximum_candidate_local_epoch_offset_s": local_max,
            "maximum_absolute_candidate_local_epoch_offset_s": local_max_abs,
            "caveat": (
                "all hypotheses are predicted at scheduled probe starts; individual candidate "
                "local measurement epochs can differ within a probe"
            ),
        },
        "provisional_costs": {
            **config_document,
            "config_digest": canonical_digest(config_document),
            "interpretation": "explicit prototype costs, not calibrated likelihood or odds",
        },
        "activity": {
            "algorithm": result.algorithm,
            "exact_for_fixed_hypotheses": result.exact,
            "independent_objective_check_passed": True,
            "selected_catalog_numbers": list(result.selected_catalog_numbers),
            "satellites": satellites,
            "unexplained_observation_ids": list(result.unexplained_observation_ids),
            "objective": asdict(result.objective),
        },
        "interpretation": {
            "claim": "conditional bounded fixed-hypothesis joint activity replay only",
            "limitations": [
                "the resolved radio component and catalogue hypotheses were supplied in advance",
                "delay and CFO offset were fixed inputs rather than fitted by this replay",
                "costs are explicit prototype settings, not calibrated posterior odds",
                "scheduled probe starts approximate candidate-specific local measurement epochs",
                "observer coordinates are not capture-bound",
                "TLE snapshot causality was not established by this tool",
                "no per-cell visibility mask was applied",
                "no payload was decoded",
            ],
        },
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--component-id", required=True)
    parser.add_argument("--start-s", type=float, required=True)
    parser.add_argument("--end-s", type=float, required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument(
        "--hypothesis",
        action="append",
        type=_parse_hypothesis,
        required=True,
        metavar="CATALOG,DELAY_S,CFO_OFFSET_HZ[,DELAY_PRIOR_COST]",
        help="repeat exactly two or three times",
    )
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--cell-duration-s", type=float, default=0.1)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--allow-left-censored", action="store_true")
    parser.add_argument("--allow-right-censored", action="store_true")
    parser.add_argument("--cfo-sigma-hz", type=float, default=100.0)
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
        cfo_sigma_hz=arguments.cfo_sigma_hz,
        detection_probability=arguments.detection_probability,
        clutter_cost=arguments.clutter_cost,
        satellite_cost=arguments.satellite_cost,
        episode_cost=arguments.episode_cost,
        huber_threshold=arguments.huber_threshold,
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    document = replay_window(
        dataset=_read_json(arguments.input),
        dataset_path=arguments.input,
        tle_path=arguments.tle,
        expected_tle_digest=expected_tle_digest,
        component_id=arguments.component_id,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
        hypothesis_specs=tuple(arguments.hypothesis),
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
