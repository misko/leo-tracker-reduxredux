#!/usr/bin/env python3
"""Screen a frozen Starlink catalogue against one raw activity window.

This research adapter extends ``replay_raw_grouped_satellite_activity.py`` in
one deliberately bounded direction: catalogue candidates are no longer named
by the caller.  Every named Starlink that is physically plausible and visible
throughout the complete probe-by-delay bank is scored independently on a
coarse nuisance grid.  A deterministic shortlist is refined, and the best
three distinct catalogues are passed to the existing exact grouped oracle.

The catalogue screen is coarse-to-fine and its CFO modes are data proposed, so
it is not a global unknown-N optimizer.  A geometry-independent optimistic
lower bound can, however, certify the null exactly under the current additive
objective without propagating the catalogue.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    CfoCandidate,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.doppler import doppler_shift_hz  # type: ignore[import-untyped]
from leo.sky.propagation import (  # type: ignore[import-untyped]
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid  # type: ignore[import-untyped]
from leo.sky.screening import observe_grid  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    ALGORITHM,
    INPUT_SCHEMA,
    NULL_CERTIFICATE_ALGORITHM,
    OUTPUT_SCHEMA,
    CatalogueScreenConfig,
    build_search_configuration,
    member_evaluation_scope_digest,
    pilot_scan_search_configuration,
    producer_implementation_manifest,
)
from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    ReplayConfig as _WindowConfig,
)
from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    _file_digest,
    _ordered_schedule,
    _read_json,
    _refuse_qnap_output,
    _window_inventory,
)


@dataclass(frozen=True, slots=True)
class CatalogueGeometryAccounting:
    catalogue_object_count: int
    unique_catalog_number_count: int
    nonmatching_name_count: int
    name_selected_count: int
    coarse_propagation_failure_count: int
    implausible_altitude_count: int
    safely_below_horizon_count: int
    fine_propagation_failure_count: int
    fine_implausible_altitude_count: int
    not_full_window_visible_count: int
    eligible_catalog_count: int

    def __post_init__(self) -> None:
        partition = (
            self.nonmatching_name_count
            + self.coarse_propagation_failure_count
            + self.implausible_altitude_count
            + self.safely_below_horizon_count
            + self.fine_propagation_failure_count
            + self.fine_implausible_altitude_count
            + self.not_full_window_visible_count
            + self.eligible_catalog_count
        )
        if partition != self.catalogue_object_count:
            raise ValueError("catalogue geometry accounting does not partition every object")
        if self.name_selected_count != self.catalogue_object_count - self.nonmatching_name_count:
            raise ValueError("catalogue name-selection accounting is inconsistent")


@dataclass(frozen=True, slots=True)
class CataloguePredictionBank:
    """Vectorized exact-time Doppler samples for the eligible catalogue rows."""

    catalogue: ElementSetCatalogue
    exact_utc_ns: tuple[int, ...]
    scheduled_times_s: tuple[float, ...]
    first_sample_utc_ns: int
    delay_grid: tuple[float, ...]
    columns_by_delay: tuple[tuple[int, ...], ...]
    doppler_hz: NDArray[np.float64]
    elevation_deg: NDArray[np.float64]
    catalogue_indices: tuple[int, ...]
    accounting: CatalogueGeometryAccounting

    def __post_init__(self) -> None:
        rows = len(self.catalogue_indices)
        columns = len(self.exact_utc_ns)
        if self.doppler_hz.shape != (rows, columns):
            raise ValueError("catalogue Doppler-bank shape is inconsistent")
        if self.elevation_deg.shape != (rows, columns):
            raise ValueError("catalogue elevation-bank shape is inconsistent")
        if len(self.delay_grid) != len(self.columns_by_delay):
            raise ValueError("catalogue delay-column inventory is inconsistent")
        if any(len(item) != len(self.scheduled_times_s) for item in self.columns_by_delay):
            raise ValueError("catalogue delay columns do not cover every scheduled probe")
        if rows != self.accounting.eligible_catalog_count:
            raise ValueError("eligible geometry count disagrees with prediction-bank rows")

    @property
    def catalog_numbers(self) -> tuple[int, ...]:
        return tuple(self.catalogue.satellite_numbers[index] for index in self.catalogue_indices)

    def curve(self, row_index: int, delay_s: float) -> NDArray[np.float64]:
        try:
            delay_index = self.delay_grid.index(delay_s)
        except ValueError as error:
            raise ValueError("requested delay is absent from the prediction bank") from error
        return np.asarray(
            self.doppler_hz[row_index, np.asarray(self.columns_by_delay[delay_index])],
            dtype=np.float64,
        )

    def elevation(self, row_index: int, delay_s: float) -> NDArray[np.float64]:
        delay_index = self.delay_grid.index(delay_s)
        return np.asarray(
            self.elevation_deg[row_index, np.asarray(self.columns_by_delay[delay_index])],
            dtype=np.float64,
        )


@dataclass(frozen=True, slots=True)
class CatalogScore:
    catalog_number: int
    object_name: str
    catalogue_index: int
    generated_state_count: int
    best_state: raw_replay._StateEvaluation


@dataclass(frozen=True, slots=True)
class NullCertificate:
    certified: bool
    modeled_null_cost: float
    optimistic_delta_from_null: float
    optimistic_selected: bool
    active_cell_count: int
    episode_count: int
    assignment_count: int


def _strict_delay_grid(lower_s: float, upper_s: float, step_s: float) -> tuple[float, ...]:
    count_value = (upper_s - lower_s) / step_s
    count = round(count_value)
    if not math.isclose(count_value, count, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("coarse delay step must divide the configured delay interval")
    return tuple(lower_s + index * step_s for index in range(count + 1))


def _exact_time_grid(utc_ns: tuple[int, ...]) -> SamplingGrid:
    ordered = tuple(sorted(set(utc_ns)))
    if len(ordered) < 3:
        raise ValueError("catalogue prediction grid needs at least three exact instants")
    differences = [right - left for left, right in pairwise(ordered)]
    if min(differences) <= 0:
        raise ValueError("catalogue prediction instants must be strictly increasing")
    return SamplingGrid(ordered, 0, min(differences) / 1e9)


def _uniform_grid(start_utc_ns: int, end_utc_ns: int, spacing_s: float) -> SamplingGrid:
    if end_utc_ns <= start_utc_ns:
        raise ValueError("catalogue geometry window must have positive duration")
    count = max(3, int(math.ceil((end_utc_ns - start_utc_ns) / 1e9 / spacing_s)) + 1)
    step_ns = int(math.ceil((end_utc_ns - start_utc_ns) / (count - 1)))
    return SamplingGrid(
        tuple(start_utc_ns + index * step_ns for index in range(count)),
        0,
        step_ns / 1e9,
    )


def build_catalogue_prediction_bank(
    *,
    catalogue: ElementSetCatalogue,
    scheduled_times_s: tuple[float, ...],
    first_sample_utc_ns: int,
    delay_grid: tuple[float, ...],
    sky_frequency_hz: float,
    observer: ObserverSiteV1,
    horizon_mask_deg: float,
    name_prefix: str,
    geometry_spacing_s: float,
) -> CataloguePredictionBank:
    """Propagate and account the complete named-Starlink visibility universe."""

    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("catalogue contains duplicate NORAD identities")
    if not scheduled_times_s or not delay_grid:
        raise ValueError("catalogue screen requires scheduled probes and a delay grid")
    prefix = name_prefix.strip().upper()
    selected_by_name = tuple(
        index for index, name in enumerate(catalogue.names) if str(name).upper().startswith(prefix)
    )
    nonmatching_count = len(catalogue) - len(selected_by_name)

    shifted_utc = tuple(
        first_sample_utc_ns + int(round((time_s + delay_s) * 1e9))
        for delay_s in delay_grid
        for time_s in scheduled_times_s
    )
    exact_grid = _exact_time_grid(shifted_utc)
    exact_column = {utc_ns: index for index, utc_ns in enumerate(exact_grid.utc_ns)}
    columns_by_delay = tuple(
        tuple(
            exact_column[first_sample_utc_ns + int(round((time_s + delay_s) * 1e9))]
            for time_s in scheduled_times_s
        )
        for delay_s in delay_grid
    )

    coarse_grid = _uniform_grid(
        min(exact_grid.utc_ns),
        max(exact_grid.utc_ns),
        geometry_spacing_s,
    )
    coarse = propagate_grid(catalogue, coarse_grid, selected_by_name)
    coarse_tracks = observe_grid(coarse, observer, coarse_grid)
    coarse_usable = np.asarray(coarse_tracks.usable, dtype=np.bool_)
    coarse_plausible = coarse_usable & (
        np.min(coarse_tracks.altitude_km, axis=1) >= MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    angular_margin_deg = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    coarse_horizon_candidate = coarse_plausible & (
        np.max(coarse_tracks.elevation_deg, axis=1) >= horizon_mask_deg - angular_margin_deg
    )
    candidate_rows = np.flatnonzero(coarse_horizon_candidate)
    fine_catalogue_indices = tuple(selected_by_name[int(row)] for row in candidate_rows)

    fine = propagate_grid(catalogue, exact_grid, fine_catalogue_indices)
    fine_tracks = observe_grid(fine, observer, exact_grid)
    fine_usable = np.asarray(fine_tracks.usable, dtype=np.bool_)
    fine_plausible = fine_usable & (
        np.min(fine_tracks.altitude_km, axis=1) >= MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    fine_full_visible = fine_plausible & (
        np.min(fine_tracks.elevation_deg, axis=1) > horizon_mask_deg
    )
    visible_rows = np.flatnonzero(fine_full_visible)
    eligible_indices = tuple(fine_catalogue_indices[int(row)] for row in visible_rows)

    accounting = CatalogueGeometryAccounting(
        catalogue_object_count=len(catalogue),
        unique_catalog_number_count=len(set(catalogue.satellite_numbers)),
        nonmatching_name_count=nonmatching_count,
        name_selected_count=len(selected_by_name),
        coarse_propagation_failure_count=int(np.count_nonzero(~coarse_usable)),
        implausible_altitude_count=int(np.count_nonzero(coarse_usable & ~coarse_plausible)),
        safely_below_horizon_count=int(
            np.count_nonzero(coarse_plausible & ~coarse_horizon_candidate)
        ),
        fine_propagation_failure_count=int(np.count_nonzero(~fine_usable)),
        fine_implausible_altitude_count=int(np.count_nonzero(fine_usable & ~fine_plausible)),
        not_full_window_visible_count=int(np.count_nonzero(fine_plausible & ~fine_full_visible)),
        eligible_catalog_count=len(eligible_indices),
    )
    return CataloguePredictionBank(
        catalogue=catalogue,
        exact_utc_ns=exact_grid.utc_ns,
        scheduled_times_s=scheduled_times_s,
        first_sample_utc_ns=first_sample_utc_ns,
        delay_grid=delay_grid,
        columns_by_delay=columns_by_delay,
        doppler_hz=np.asarray(
            doppler_shift_hz(
                sky_frequency_hz,
                fine_tracks.range_rate_km_s[visible_rows],
            ),
            dtype=np.float64,
        ),
        elevation_deg=np.asarray(fine_tracks.elevation_deg[visible_rows], dtype=np.float64),
        catalogue_indices=eligible_indices,
        accounting=accounting,
    )


def optimistic_null_certificate(problem: SatelliteActivityProblem) -> NullCertificate:
    """Return a global null certificate from a zero-residual optimistic relaxation."""

    if problem.truncated_observation_count:
        raise ValueError("null certificate requires a complete retained observation inventory")
    relaxed_observations = tuple(
        CfoCandidate(
            observation_id=item.observation_id,
            probe_id=item.probe_id,
            exclusion_group_id=item.exclusion_group_id,
            cfo_hz=0.0,
            sigma_hz=item.sigma_hz,
            clutter_cost=item.clutter_cost,
            matched_base_cost=item.matched_base_cost,
            component_id=item.component_id,
        )
        for item in problem.observations
    )
    relaxed = replace(problem, observations=relaxed_observations)
    hypothesis = SingleSatelliteHypothesis(
        hypothesis_id="optimistic-zero-residual-satellite",
        object_name="OPTIMISTIC-LOWER-BOUND",
        catalog_number=1,
        delay_s=0.0,
        cfo_offset_hz=0.0,
        delay_prior_cost=0.0,
        predictions=tuple(
            PredictedProbeCfo(probe_id=item.probe_id, cfo_hz=0.0) for item in problem.probes
        ),
    )
    decoded = decode_single_satellite(relaxed, hypothesis)
    delta = decoded.objective.delta_from_null
    certified = not decoded.selected and delta == 0.0
    return NullCertificate(
        certified=certified,
        modeled_null_cost=decoded.objective.null_cost,
        optimistic_delta_from_null=delta,
        optimistic_selected=decoded.selected,
        active_cell_count=sum(decoded.activity_by_cell),
        episode_count=len(decoded.episodes),
        assignment_count=len(decoded.assignments),
    )


def _ranking_problem(problem: SatelliteActivityProblem) -> SatelliteActivityProblem:
    return replace(
        problem,
        costs=replace(problem.costs, satellite_cost=0.0),
    )


def _evaluate_catalog(
    *,
    bank: CataloguePredictionBank,
    row_index: int,
    delay_grid: tuple[float, ...],
    problem: SatelliteActivityProblem,
    raw_observations: tuple[raw_replay._RawObservation, ...],
    calibration: raw_replay.ScoreCalibration,
    config: raw_replay.RawReplayConfig,
) -> CatalogScore:
    catalogue_index = bank.catalogue_indices[row_index]
    catalog_number = bank.catalogue.satellite_numbers[catalogue_index]
    object_name = str(bank.catalogue.names[catalogue_index])
    states: list[raw_replay._StateEvaluation] = []
    for delay_s in delay_grid:
        curve = bank.curve(row_index, delay_s)
        elevation = bank.elevation(row_index, delay_s)
        for mode in raw_replay._offset_modes(
            raw=raw_observations,
            base_prediction_hz=curve,
            calibration=calibration,
            config=config,
        ):
            delay_prior_cost = (
                0.5 * ((delay_s - config.delay_prior_mean_s) / config.delay_prior_sigma_s) ** 2
            )
            hypothesis = SingleSatelliteHypothesis(
                hypothesis_id=canonical_digest(
                    {
                        "catalog_number": catalog_number,
                        "delay_s": delay_s,
                        "cfo_offset_hz": mode.cfo_offset_hz,
                        "prediction_epoch": "scheduled_probe_start",
                        "catalogue_screen": ALGORITHM,
                    }
                ),
                object_name=object_name,
                catalog_number=catalog_number,
                delay_s=delay_s,
                cfo_offset_hz=mode.cfo_offset_hz,
                delay_prior_cost=delay_prior_cost,
                predictions=tuple(
                    PredictedProbeCfo(probe_id=probe.probe_id, cfo_hz=float(curve[index]))
                    for index, probe in enumerate(problem.probes)
                ),
            )
            decoded = decode_single_satellite(problem, hypothesis)
            states.append(
                raw_replay._StateEvaluation(
                    hypothesis=hypothesis,
                    proposal=mode,
                    single_total_cost=decoded.objective.total_cost,
                    single_delta_from_null=decoded.objective.delta_from_null,
                    single_selected=decoded.selected,
                    minimum_elevation_deg=float(np.min(elevation)),
                    maximum_elevation_deg=float(np.max(elevation)),
                )
            )
    ordered = sorted(states, key=raw_replay._state_sort_key)
    if not ordered:
        raise RuntimeError(f"NORAD {catalog_number} generated no catalogue-screen states")
    return CatalogScore(
        catalog_number=catalog_number,
        object_name=object_name,
        catalogue_index=catalogue_index,
        generated_state_count=len(ordered),
        best_state=ordered[0],
    )


def _catalog_score_key(item: CatalogScore) -> tuple[object, ...]:
    return (
        item.best_state.single_delta_from_null,
        item.catalog_number,
        item.best_state.hypothesis.hypothesis_id,
    )


def _score_catalog_rows(
    *,
    bank: CataloguePredictionBank,
    row_indices: tuple[int, ...],
    delay_grid: tuple[float, ...],
    problem: SatelliteActivityProblem,
    raw_observations: tuple[raw_replay._RawObservation, ...],
    calibration: raw_replay.ScoreCalibration,
    config: raw_replay.RawReplayConfig,
) -> tuple[CatalogScore, ...]:
    scored = tuple(
        _evaluate_catalog(
            bank=bank,
            row_index=row_index,
            delay_grid=delay_grid,
            problem=problem,
            raw_observations=raw_observations,
            calibration=calibration,
            config=config,
        )
        for row_index in row_indices
    )
    if len({item.catalog_number for item in scored}) != len(scored):
        raise RuntimeError("catalogue screen produced duplicate NORAD scores")
    return tuple(sorted(scored, key=_catalog_score_key))


def _refinement_rows(
    coarse_scores: tuple[CatalogScore, ...],
    config: CatalogueScreenConfig,
) -> tuple[int, ...]:
    if len(coarse_scores) < config.final_catalog_count:
        raise ValueError(
            "catalogue-screen v1 requires at least final_catalog_count full-window-visible "
            "objects; no association was emitted"
        )
    base_count = min(config.refinement_catalog_count, len(coarse_scores))
    selected = list(coarse_scores[:base_count])
    cutoff = selected[-1].best_state.single_delta_from_null
    if cutoff < 0.0 and config.refinement_guard_cost > 0.0:
        guarded_cutoff = min(0.0, cutoff + config.refinement_guard_cost)
        selected.extend(
            item
            for item in coarse_scores[base_count:]
            if item.best_state.single_delta_from_null < 0.0
            and item.best_state.single_delta_from_null <= guarded_cutoff
        )
    if len(selected) > config.maximum_refinement_catalog_count:
        raise ValueError("coarse score guard band exceeds the refinement hard cap")
    return tuple(item.catalogue_index for item in selected)


def _score_summary(item: CatalogScore, rank: int) -> dict[str, Any]:
    state = item.best_state
    threshold = max(0.0, -state.single_delta_from_null)
    return {
        "rank": rank,
        "catalog_number": item.catalog_number,
        "object_name": item.object_name,
        "catalogue_index": item.catalogue_index,
        "generated_state_count": item.generated_state_count,
        "best_single_delta_at_zero_satellite_cost": state.single_delta_from_null,
        "activation_satellite_cost_threshold": threshold,
        "best_delay_s": state.hypothesis.delay_s,
        "best_cfo_offset_hz": state.hypothesis.cfo_offset_hz,
        "delay_prior_cost": state.hypothesis.delay_prior_cost,
        "mode_support_probe_count": state.proposal.support_probe_count,
        "mode_support_group_count": state.proposal.support_group_count,
        "minimum_elevation_deg": state.minimum_elevation_deg,
        "maximum_elevation_deg": state.maximum_elevation_deg,
        "best_hypothesis_id": state.hypothesis.hypothesis_id,
    }


def _calibration_source_digests(document: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    sources = document.get("sources")
    if not isinstance(sources, dict):
        return result
    for item in sources.get("null", ()):
        if isinstance(item, dict):
            result.add(str(item.get("file_digest", "")))
    for item in sources.get("signal", ()):
        if isinstance(item, dict) and isinstance(item.get("pilot_scan"), dict):
            result.add(str(item["pilot_scan"].get("file_digest", "")))
    return result


def _search_configuration(
    *,
    calibration_schema: object,
    calibration_digest: str,
    tle_digest: str,
    sky_frequency_hz: float,
    pilot_scan_configuration: dict[str, Any],
    observer: ObserverSiteV1,
    start_s: float,
    end_s: float,
    scheduled_probe_count: int,
    cell_count: int,
    evaluation_scope_digest: str,
    config: raw_replay.RawReplayConfig,
    screen_config: CatalogueScreenConfig,
) -> dict[str, Any]:
    """Canonical, data-path-independent settings for structural calibration binding."""

    return build_search_configuration(
        calibration_schema=calibration_schema,
        calibration_digest=calibration_digest,
        tle_digest=tle_digest,
        sky_frequency_hz=sky_frequency_hz,
        pilot_scan_configuration=pilot_scan_configuration,
        observer_configuration=observer.model_dump(mode="json"),
        window_start_s=start_s,
        window_end_s=end_s,
        scheduled_probe_count=scheduled_probe_count,
        cell_count=cell_count,
        member_evaluation_scope_digest=evaluation_scope_digest,
        producer_implementation=producer_implementation_manifest(),
        raw_replay_configuration=asdict(config),
        catalogue_screen_configuration=asdict(screen_config),
    )


def _pilot_scan_configuration(path: Path) -> dict[str, Any]:
    """Detector search settings that change the retained candidate opportunity set."""

    return pilot_scan_search_configuration(_read_json(path))


def _member_evaluation_scope_digest(
    *,
    dataset: dict[str, Any],
    dataset_path: Path,
    pilot_scan_digest: str,
    window: Any,
    start_s: float,
    end_s: float,
) -> str:
    capture = dataset["capture"]
    frequency = dataset["frequency_binding"]
    return member_evaluation_scope_digest(
        duration_dataset_digest=_file_digest(dataset_path),
        pilot_scan_digest=pilot_scan_digest,
        session_id=str(capture["session_id"]),
        recording_manifest_digest=str(capture["recording_manifest_digest"]),
        stream_id=str(capture["stream_id"]),
        receiver_id=int(capture["receiver_id"]),
        tuning_tag=str(frequency["tuning_tag"]),
        sky_frequency_hz=float(frequency["sky_frequency_hz"]),
        scheduled_probe_ids=tuple(str(row["probe_id"]) for row in window.rows),
        window_start_s=start_s,
        window_end_s=end_s,
    )


def _prepare_raw_inventory(
    *,
    dataset: dict[str, Any],
    calibration_document: dict[str, Any],
    start_s: float,
    end_s: float,
    config: raw_replay.RawReplayConfig,
) -> tuple[
    raw_replay.ScoreCalibration,
    Any,
    raw_replay._RawInventory,
    tuple[float, ...],
]:
    if dataset.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected input schema {INPUT_SCHEMA}")
    if dataset.get("per_probe_rows_omitted"):
        raise ValueError("catalogue screen requires the full scheduled-probe extraction")
    raw_replay._validate_calibration_grouping(calibration_document, config)
    calibration = raw_replay._score(calibration_document)
    if not calibration.weak_match_is_dominated_by_miss():
        raise ValueError("score calibration does not make weak raw candidates miss-dominated")
    window = _window_inventory(
        dataset=dataset,
        ordered_schedule=_ordered_schedule(dataset),
        start_s=start_s,
        end_s=end_s,
        config=_WindowConfig(
            cell_duration_s=config.cell_duration_s,
            minimum_active_duration_s=config.minimum_active_duration_s,
            allow_left_censored=config.allow_left_censored,
            allow_right_censored=config.allow_right_censored,
        ),
    )
    inventory = raw_replay._load_raw_inventory(
        dataset=dataset,
        window_rows=window.rows,
        window_start_sample=window.start_sample,
        window_cell_samples=window.cell_samples,
        window_cell_count=window.cell_count,
        calibration=calibration,
        config=config,
    )
    if inventory.scan_digest in _calibration_source_digests(calibration_document):
        raise ValueError("evaluated raw scan was also used to calibrate detector-score costs")
    return (
        calibration,
        window,
        inventory,
        tuple(float(item["probe_start_time_s"]) for item in window.rows),
    )


def _null_certificate_document(
    *,
    dataset_path: Path,
    calibration_path: Path,
    tle_path: Path,
    tle_digest: str,
    inventory: raw_replay._RawInventory,
    window: Any,
    start_s: float,
    end_s: float,
    certificate: NullCertificate,
    observer: ObserverSiteV1,
    config: raw_replay.RawReplayConfig,
    screen_config: CatalogueScreenConfig,
    catalogue: ElementSetCatalogue,
    calibration_schema: object,
    sky_frequency_hz: float,
    pilot_scan_configuration: dict[str, Any],
    evaluation_scope_digest: str,
) -> dict[str, Any]:
    full_null = certificate.modeled_null_cost + inventory.elided_clutter_constant
    calibration_digest = _file_digest(calibration_path)
    search_configuration = _search_configuration(
        calibration_schema=calibration_schema,
        calibration_digest=calibration_digest,
        tle_digest=tle_digest,
        sky_frequency_hz=sky_frequency_hz,
        pilot_scan_configuration=pilot_scan_configuration,
        observer=observer,
        start_s=start_s,
        end_s=end_s,
        scheduled_probe_count=len(window.rows),
        cell_count=window.cell_count,
        evaluation_scope_digest=evaluation_scope_digest,
        config=config,
        screen_config=screen_config,
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "catalogue_search_performed": False,
        "catalogue_search_avoided_by_global_null_certificate": True,
        "catalogue_search_exact": False,
        "null_vs_any_activation_solved": True,
        "unknown_satellite_count_solved": False,
        "global_optimum_claimed": False,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_full_window_visibility_screen": False,
        "conditional_on_data_proposed_cfo_modes": False,
        "conditional_on_pruned_joint_shortlist": False,
        "conditional_on_pruned_nuisance_state_bank": False,
        "costs_calibrated": False,
        "detector_score_costs_empirically_calibrated": False,
        "resolution_group_score_frequency_estimated": calibration_schema
        in {raw_replay.CALIBRATION_SCHEMA_V2, raw_replay.CALIBRATION_SCHEMA_V3},
        "conservative_rank_mark_bounds_applied": calibration_schema
        == raw_replay.CALIBRATION_SCHEMA_V3,
        "structural_costs_calibrated": False,
        "input": {
            "duration_dataset_path": str(dataset_path.resolve()),
            "duration_dataset_digest": _file_digest(dataset_path),
            "pilot_scan_path": str(inventory.scan_path),
            "pilot_scan_digest": inventory.scan_digest,
            "score_calibration_path": str(calibration_path.resolve()),
            "score_calibration_digest": calibration_digest,
            "tle_path": str(tle_path.resolve()),
            "tle_digest": tle_digest,
        },
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "cell_duration_s": config.cell_duration_s,
            "cell_count": window.cell_count,
            "minimum_active_cells": config.minimum_active_cells,
            "minimum_active_duration_s": config.minimum_active_duration_s,
            "scheduled_probe_count": len(window.rows),
        },
        "raw_inventory": {
            "source_candidate_count": inventory.source_candidate_count,
            "returned_candidate_count": inventory.returned_candidate_count,
            "truncated_candidate_count": 0,
            "probe_count_at_retained_candidate_cap": inventory.saturated_probe_count,
            "declared_post_acquisition_inventory_complete": True,
            "pre_acquisition_cap_inventory_complete": False,
            "exclusion_group_count": inventory.exclusion_group_count,
            "modeled_exclusion_group_count": inventory.modeled_exclusion_group_count,
            "positive_exclusion_group_count": inventory.positive_exclusion_group_count,
            "omitted_clutter_objective_constant": inventory.elided_clutter_constant,
        },
        "catalogue": {
            "object_count": len(catalogue),
            "unique_catalog_number_count": len(set(catalogue.satellite_numbers)),
            "name_prefix": screen_config.name_prefix,
        },
        "null_certificate": {
            **asdict(certificate),
            "algorithm": NULL_CERTIFICATE_ALGORITHM,
            "residual_loss_lower_bound": 0.0,
            "candidate_group_reuse_between_hypothetical_satellites_allowed": True,
            "proof_scope": (
                "current additive satellite/episode/delay-prior objective over the retained "
                "raw candidate inventory"
            ),
        },
        "association": {
            "selected_catalog_numbers": [],
            "selected_satellite_count": 0,
            "objective": {
                "null_cost": full_null,
                "total_cost": full_null,
                "delta_from_null": 0.0,
            },
        },
        "decision": {
            "result_kind": "certified_null",
            "selected_catalog_numbers": [],
            "selected_satellite_count": 0,
            "full_persisted_inventory_objective": {
                "null_cost": full_null,
                "total_cost": full_null,
                "delta_from_null": 0.0,
                "constant_elided_from_exact_decision_problem": (inventory.elided_clutter_constant),
            },
        },
        "configuration": asdict(config),
        "catalogue_screen_configuration": asdict(screen_config),
        "search_configuration": search_configuration,
        "search_configuration_digest": canonical_digest(search_configuration),
        "observer": {**observer.model_dump(mode="json"), "capture_bound": False},
        "caveats": [
            "the null certificate is conditional on the retained bounded raw peak inventory",
            "structural costs have not yet been calibrated on a locked dwell-level null corpus",
            (
                "an analyzer no-result dwell is an empirical control, not ground-truth "
                "satellite absence"
            ),
            "TLE bytes are digest-bound but snapshot acquisition causality is not verified here",
            "no payload was decoded",
        ],
    }


def screen_raw_catalogue_window(
    *,
    dataset: dict[str, Any],
    dataset_path: Path,
    calibration_document: dict[str, Any],
    calibration_path: Path,
    tle_path: Path,
    expected_tle_digest: str,
    start_s: float,
    end_s: float,
    observer: ObserverSiteV1,
    config: raw_replay.RawReplayConfig,
    screen_config: CatalogueScreenConfig,
) -> dict[str, Any]:
    """Run the null certificate or a staged full named-Starlink screen."""

    observed_tle_digest = _file_digest(tle_path)
    if observed_tle_digest != expected_tle_digest:
        raise ValueError("catalogue-screen TLE digest mismatch")
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("catalogue contains duplicate NORAD identities")
    calibration, window, inventory, scheduled_times_s = _prepare_raw_inventory(
        dataset=dataset,
        calibration_document=calibration_document,
        start_s=start_s,
        end_s=end_s,
        config=config,
    )
    sky_frequency_hz = float(dataset["frequency_binding"]["sky_frequency_hz"])
    pilot_scan_configuration = _pilot_scan_configuration(inventory.scan_path)
    evaluation_scope_digest = _member_evaluation_scope_digest(
        dataset=dataset,
        dataset_path=dataset_path,
        pilot_scan_digest=inventory.scan_digest,
        window=window,
        start_s=start_s,
        end_s=end_s,
    )
    certificate = optimistic_null_certificate(inventory.problem)
    if certificate.certified:
        return _null_certificate_document(
            dataset_path=dataset_path,
            calibration_path=calibration_path,
            tle_path=tle_path,
            tle_digest=observed_tle_digest,
            inventory=inventory,
            window=window,
            start_s=start_s,
            end_s=end_s,
            certificate=certificate,
            observer=observer,
            config=config,
            screen_config=screen_config,
            catalogue=catalogue,
            calibration_schema=calibration_document.get("schema"),
            sky_frequency_hz=sky_frequency_hz,
            pilot_scan_configuration=pilot_scan_configuration,
            evaluation_scope_digest=evaluation_scope_digest,
        )

    coarse_delay_grid = _strict_delay_grid(
        config.delay_min_s,
        config.delay_max_s,
        screen_config.coarse_delay_step_s,
    )
    prediction_delay_grid = tuple(sorted(set(config.delay_grid) | set(coarse_delay_grid)))
    bank = build_catalogue_prediction_bank(
        catalogue=catalogue,
        scheduled_times_s=scheduled_times_s,
        first_sample_utc_ns=int(dataset["timing_binding"]["first_estimate_utc_ns"]),
        delay_grid=prediction_delay_grid,
        sky_frequency_hz=sky_frequency_hz,
        observer=observer,
        horizon_mask_deg=config.horizon_mask_deg,
        name_prefix=screen_config.name_prefix,
        geometry_spacing_s=screen_config.geometry_spacing_s,
    )
    ranking_problem = _ranking_problem(inventory.problem)
    coarse_config = replace(
        config,
        delay_step_s=screen_config.coarse_delay_step_s,
        modes_per_delay=screen_config.coarse_modes_per_delay,
        satellite_cost=0.0,
    )
    fine_config = replace(config, satellite_cost=0.0)
    coarse_scores = _score_catalog_rows(
        bank=bank,
        row_indices=tuple(range(len(bank.catalogue_indices))),
        delay_grid=coarse_delay_grid,
        problem=ranking_problem,
        raw_observations=inventory.observations,
        calibration=calibration,
        config=coarse_config,
    )
    refinement_catalogue_indices = _refinement_rows(coarse_scores, screen_config)
    bank_row_by_catalogue_index = {
        catalogue_index: row for row, catalogue_index in enumerate(bank.catalogue_indices)
    }
    refinement_rows = tuple(
        bank_row_by_catalogue_index[index] for index in refinement_catalogue_indices
    )
    fine_scores = _score_catalog_rows(
        bank=bank,
        row_indices=refinement_rows,
        delay_grid=config.delay_grid,
        problem=ranking_problem,
        raw_observations=inventory.observations,
        calibration=calibration,
        config=fine_config,
    )
    if len(fine_scores) < screen_config.final_catalog_count:
        raise RuntimeError("fine catalogue screen returned too few distinct catalogues")
    shortlisted_catalog_numbers = tuple(
        item.catalog_number for item in fine_scores[: screen_config.final_catalog_count]
    )

    document = raw_replay.replay_raw_window(
        dataset=dataset,
        dataset_path=dataset_path,
        calibration_document=calibration_document,
        calibration_path=calibration_path,
        tle_path=tle_path,
        expected_tle_digest=expected_tle_digest,
        catalog_numbers=shortlisted_catalog_numbers,
        start_s=start_s,
        end_s=end_s,
        observer=observer,
        config=config,
    )
    calibration_digest = _file_digest(calibration_path)
    search_configuration = _search_configuration(
        calibration_schema=calibration_document.get("schema"),
        calibration_digest=calibration_digest,
        tle_digest=observed_tle_digest,
        sky_frequency_hz=sky_frequency_hz,
        pilot_scan_configuration=pilot_scan_configuration,
        observer=observer,
        start_s=start_s,
        end_s=end_s,
        scheduled_probe_count=len(window.rows),
        cell_count=window.cell_count,
        evaluation_scope_digest=evaluation_scope_digest,
        config=config,
        screen_config=screen_config,
    )
    document["schema"] = OUTPUT_SCHEMA
    document["catalogue_search_performed"] = True
    document["catalogue_search_avoided_by_global_null_certificate"] = False
    document["catalogue_search_exact"] = False
    selected_catalog_numbers = document["association"]["association"]["selected_catalog_numbers"]
    # A single feasible negative-cost witness proves that the null is beaten,
    # even though coarse-to-fine pruning cannot prove that the selected subset
    # is globally best.  Proving the opposite requires the optimistic null
    # certificate above or an exhaustive state search.
    document["null_vs_any_activation_solved"] = bool(selected_catalog_numbers)
    document["unknown_satellite_count_solved"] = False
    document["global_optimum_claimed"] = False
    document["conditional_on_explicit_catalog_shortlist"] = False
    document["conditional_on_catalogue_screen_shortlist"] = True
    document["conditional_on_full_window_visibility_screen"] = True
    document["conditional_on_data_proposed_cfo_modes"] = True
    document["conditional_on_pruned_joint_shortlist"] = True
    document["catalogue_screen_configuration"] = asdict(screen_config)
    document["search_configuration"] = search_configuration
    document["search_configuration_digest"] = canonical_digest(search_configuration)
    document["decision"] = {
        "result_kind": "catalogue_screened_grouped_activity",
        "selected_catalog_numbers": selected_catalog_numbers,
        "selected_satellite_count": len(selected_catalog_numbers),
        "full_persisted_inventory_objective": document["full_persisted_inventory_objective"],
    }
    document["catalogue_search"] = {
        "algorithm": ALGORITHM,
        "exact": False,
        "geometry_accounting": asdict(bank.accounting),
        "full_window_visibility_scope": {
            "probe_count": len(scheduled_times_s),
            "prediction_delay_grid": list(prediction_delay_grid),
            "fine_delay_grid": list(config.delay_grid),
            "exact_shifted_time_count": len(bank.exact_utc_ns),
            "horizon_mask_deg": config.horizon_mask_deg,
            "sampled_visibility_strictly_above_mask": True,
            "rise_set_objects_supported": False,
        },
        "coarse_stage": {
            "delay_grid": list(coarse_delay_grid),
            "modes_per_delay": screen_config.coarse_modes_per_delay,
            "eligible_catalog_count": len(coarse_scores),
            "scored_catalog_count": len(coarse_scores),
            "generated_state_count": sum(item.generated_state_count for item in coarse_scores),
            "declared_delay_grid_exhausted": True,
            "data_proposed_cfo_mode_space_exhausted": False,
            "ranking": [
                _score_summary(item, rank) for rank, item in enumerate(coarse_scores, start=1)
            ],
        },
        "fine_stage": {
            "delay_grid": list(config.delay_grid),
            "modes_per_delay": config.modes_per_delay,
            "refinement_catalog_count": len(fine_scores),
            "eligible_catalog_count": len(coarse_scores),
            "omitted_catalog_count": len(coarse_scores) - len(fine_scores),
            "generated_state_count": sum(item.generated_state_count for item in fine_scores),
            "declared_delay_grid_exhausted_for_refined_catalogues": True,
            "eligible_catalogue_state_space_exhausted": len(fine_scores) == len(coarse_scores),
            "data_proposed_cfo_mode_space_exhausted": False,
            "ranking": [
                _score_summary(item, rank) for rank, item in enumerate(fine_scores, start=1)
            ],
        },
        "shortlist": {
            "catalog_numbers": list(shortlisted_catalog_numbers),
            "distinct_catalog_count": len(shortlisted_catalog_numbers),
            "refinement_base_limit": screen_config.refinement_catalog_count,
            "refinement_guard_cost": screen_config.refinement_guard_cost,
            "refinement_hard_limit": screen_config.maximum_refinement_catalog_count,
            "final_catalog_limit": screen_config.final_catalog_count,
            "tie_key": [
                "best_single_delta_at_zero_satellite_cost",
                "catalog_number",
                "hypothesis_id",
            ],
        },
        "satellite_cost_ranking_policy": {
            "ranking_satellite_cost": 0.0,
            "final_satellite_cost": config.satellite_cost,
            "episode_cost_included_during_ranking": config.episode_cost,
            "activation_threshold_definition": (
                "maximum nonnegative per-satellite cost preserving a negative single delta"
            ),
        },
    }
    document["joint_search"] = {
        "exact_only_over_shortlisted_catalogues_and_retained_nuisance_states": True,
        "shortlisted_catalog_numbers": list(shortlisted_catalog_numbers),
        "retained_state_count": document["nuisance_state_search"]["retained_state_count"],
        "retained_state_space_exhausted": document["nuisance_state_search"][
            "retained_state_space_exhausted"
        ],
        "selected_catalog_numbers": selected_catalog_numbers,
    }
    document["caveats"].extend(
        [
            "coarse-to-fine catalogue pruning can miss a catalogue favored only on the fine grid",
            (
                "the catalogue universe excludes rise/set objects because per-probe visibility "
                "is absent"
            ),
            (
                "catalogue ranking exhausts the declared delay grids but not continuous "
                "CFO-offset space"
            ),
            "the top-three grouped replay does not solve unrestricted satellite count",
            "TLE bytes are digest-bound but snapshot acquisition causality is not verified here",
        ]
    )
    return document


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--score-calibration", type=Path, required=True)
    parser.add_argument("--start-s", type=float, required=True)
    parser.add_argument("--end-s", type=float, required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--cell-duration-s", type=float, default=0.1)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--allow-left-censored", action="store_true")
    parser.add_argument("--allow-right-censored", action="store_true")
    parser.add_argument("--cfo-sigma-hz", type=float, default=100.0)
    parser.add_argument("--satellite-cost", type=float, default=5.25)
    parser.add_argument("--episode-cost", type=float, default=5.75)
    parser.add_argument("--huber-threshold", type=float, default=1.345)
    parser.add_argument("--delay-min-s", type=float, default=-2.0)
    parser.add_argument("--delay-max-s", type=float, default=2.0)
    parser.add_argument("--delay-step-s", type=float, default=0.1)
    parser.add_argument("--delay-prior-mean-s", type=float, default=0.0)
    parser.add_argument("--delay-prior-sigma-s", type=float, default=0.5)
    parser.add_argument("--duplicate-cfo-tolerance-hz", type=float, default=0.0)
    parser.add_argument("--resolution-epoch-tolerance-samples", type=int, default=1)
    parser.add_argument("--resolution-tracking-cfo-tolerance-hz", type=float, default=500.0)
    parser.add_argument("--mode-bin-hz", type=float, default=100.0)
    parser.add_argument("--mode-half-width-hz", type=float, default=300.0)
    parser.add_argument("--modes-per-delay", type=int, default=2)
    parser.add_argument("--retained-states-per-catalog", type=int, default=4)
    parser.add_argument("--maximum-state-combinations", type=int, default=256)
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--catalogue-name-prefix", default="STARLINK")
    parser.add_argument("--geometry-spacing-s", type=float, default=0.5)
    parser.add_argument("--coarse-delay-step-s", type=float, default=0.5)
    parser.add_argument("--coarse-modes-per-delay", type=int, default=1)
    parser.add_argument("--refinement-catalog-count", type=int, default=32)
    parser.add_argument("--refinement-guard-cost", type=float, default=0.0)
    parser.add_argument("--maximum-refinement-catalog-count", type=int, default=64)
    parser.add_argument("--final-catalog-count", type=int, choices=(2, 3), default=3)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    expected_tle_digest = str(arguments.tle_sha256)
    if not expected_tle_digest.startswith("sha256:"):
        expected_tle_digest = f"sha256:{expected_tle_digest}"
    config = raw_replay.RawReplayConfig(
        cell_duration_s=arguments.cell_duration_s,
        minimum_active_duration_s=arguments.minimum_active_duration_s,
        allow_left_censored=arguments.allow_left_censored,
        allow_right_censored=arguments.allow_right_censored,
        cfo_sigma_hz=arguments.cfo_sigma_hz,
        satellite_cost=arguments.satellite_cost,
        episode_cost=arguments.episode_cost,
        huber_threshold=arguments.huber_threshold,
        delay_min_s=arguments.delay_min_s,
        delay_max_s=arguments.delay_max_s,
        delay_step_s=arguments.delay_step_s,
        delay_prior_mean_s=arguments.delay_prior_mean_s,
        delay_prior_sigma_s=arguments.delay_prior_sigma_s,
        duplicate_cfo_tolerance_hz=arguments.duplicate_cfo_tolerance_hz,
        resolution_epoch_tolerance_samples=arguments.resolution_epoch_tolerance_samples,
        resolution_tracking_cfo_tolerance_hz=arguments.resolution_tracking_cfo_tolerance_hz,
        mode_bin_hz=arguments.mode_bin_hz,
        mode_half_width_hz=arguments.mode_half_width_hz,
        modes_per_delay=arguments.modes_per_delay,
        retained_states_per_catalog=arguments.retained_states_per_catalog,
        maximum_state_combinations=arguments.maximum_state_combinations,
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    screen_config = CatalogueScreenConfig(
        name_prefix=arguments.catalogue_name_prefix,
        geometry_spacing_s=arguments.geometry_spacing_s,
        coarse_delay_step_s=arguments.coarse_delay_step_s,
        coarse_modes_per_delay=arguments.coarse_modes_per_delay,
        refinement_catalog_count=arguments.refinement_catalog_count,
        refinement_guard_cost=arguments.refinement_guard_cost,
        maximum_refinement_catalog_count=arguments.maximum_refinement_catalog_count,
        final_catalog_count=arguments.final_catalog_count,
    )
    document = screen_raw_catalogue_window(
        dataset=_read_json(arguments.input),
        dataset_path=arguments.input,
        calibration_document=_read_json(arguments.score_calibration),
        calibration_path=arguments.score_calibration,
        tle_path=arguments.tle,
        expected_tle_digest=expected_tle_digest,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
        screen_config=screen_config,
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
