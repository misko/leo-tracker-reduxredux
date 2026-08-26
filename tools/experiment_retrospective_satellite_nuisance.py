#!/usr/bin/env python3
"""Run the frozen retrospective Starlink/nuisance association experiment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from numpy.typing import NDArray

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.satellite_nuisance_association import (
    CandidateFitBank,
    MeasurementTrack,
    chronological_block_mask,
    chronological_mask,
    fit_hierarchical_candidates,
    fit_offset_candidates,
    fit_radio_polynomial_null,
    permute_fit_response_within_paths,
)
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    parse_element_set_records,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset

ROOT = Path(__file__).parents[1]
DEFAULT_PROTOCOL = ROOT / "config/analysis/retrospective-satellite-nuisance-protocol-v1.json"
DEFAULT_OUTPUT_ROOT = ROOT / "reports/figures/2026_08_26_retrospective_satellite_nuisance"
SCHEMA = "org.leo.research.retrospective-satellite-nuisance-evidence/v1"
PROTOCOL_SCHEMA = "org.leo.research.retrospective-satellite-nuisance-protocol/v1"
BIN_NS = 20_000_000
COARSE_SPACING_S = 0.1

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class BoundTrack:
    capture_id: str
    bundle_id: str
    data_kind: str
    track: MeasurementTrack
    utc_ns: IntArray
    rf_frequency_hz: float
    primary: bool


@dataclass(frozen=True, slots=True)
class CandidatePopulation:
    catalogue_indices: IntArray
    norad_ids: IntArray
    names: tuple[str, ...]
    prediction_hz: FloatArray
    minimum_elevation_deg: FloatArray
    maximum_elevation_deg: FloatArray
    coarse_candidate_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{label} is not a canonical SHA-256")
    return value


def _iso_utc(utc_ns: int) -> str:
    seconds, nanoseconds = divmod(utc_ns, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{prefix}.{nanoseconds:09d}Z"


def load_protocol(path: Path) -> dict[str, Any]:
    """Load and re-verify every frozen local authority before evaluation."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unsupported satellite nuisance protocol schema")
    required_root = {
        "schema",
        "authority",
        "measurement_inputs",
        "tle_inputs",
        "observer_and_geometry",
        "measurement_reduction",
        "models",
        "evaluation",
        "promotion_gates",
        "failure_policy",
    }
    if set(document) != required_root:
        raise ValueError("satellite nuisance protocol root keys drifted")
    authority = document["authority"]
    if not isinstance(authority, dict):
        raise ValueError("protocol authority is malformed")
    for field in (
        "holdout_foundation_forbidden",
        "pre_fix_forbidden",
        "newer_or_dynamic_capture_discovery_forbidden",
        "capture_substitution_forbidden",
        "protocol_freeze_precedes_candidate_evaluation",
    ):
        if authority.get(field) is not True:
            raise ValueError(f"authority field {field} must fail closed")
    policy_path = ROOT / str(authority["dataset_policy_path"])
    if _sha256(policy_path) != _canonical_sha(
        authority["dataset_policy_sha256"], "dataset policy digest"
    ):
        raise ValueError("dataset policy digest drifted")
    policy = load_doppler_dataset_policy(policy_path)
    required_ids = tuple(str(item) for item in authority["required_capture_ids"])
    allowed: set[str] = set()
    for role_name in authority["allowed_policy_roles"]:
        allowed.update(policy.role(str(role_name)).capture_ids)
    if not set(required_ids) <= allowed:
        raise ValueError("protocol contains a capture outside its allowed roles")
    if set(required_ids) & set(policy.role("holdout_foundation").capture_ids):
        raise ValueError("holdout-foundation capture entered retrospective association")

    measurements = document["measurement_inputs"]
    if not isinstance(measurements, dict):
        raise ValueError("measurement input bindings are malformed")
    for name in ("multi_radio_frame_ledger", "long_150802_ledger"):
        binding = measurements[name]
        source = ROOT / str(binding["path"])
        if _sha256(source) != _canonical_sha(binding["sha256"], f"{name} digest"):
            raise ValueError(f"{name} digest drifted")

    tle_inputs = document["tle_inputs"]
    if not isinstance(tle_inputs, dict):
        raise ValueError("TLE input bindings are malformed")
    snapshots = tle_inputs["snapshots"]
    if set(snapshots) != set(required_ids):
        raise ValueError("TLE binding set disagrees with capture authority")
    for capture_id, binding in snapshots.items():
        tle_path = Path(str(binding["raw_path"]))
        if _sha256(tle_path) != _canonical_sha(binding["raw_sha256"], "TLE digest"):
            raise ValueError(f"TLE digest drifted for {capture_id}")
        retrieved = datetime.fromisoformat(str(binding["retrieved_at"]).replace("Z", "+00:00"))
        first = datetime.fromtimestamp(int(binding["first_measurement_utc_ns"]) / 1e9, UTC)
        if not retrieved < first:
            raise ValueError(f"TLE does not strictly predate {capture_id}")
    sensitivity = tle_inputs["source_sensitivity"][required_ids[-1]]
    sensitivity_path = Path(str(sensitivity["raw_path"]))
    if _sha256(sensitivity_path) != _canonical_sha(
        sensitivity["raw_sha256"], "latest-causal TLE digest"
    ):
        raise ValueError("latest-causal 150802 TLE sensitivity digest drifted")
    return document


def _path_radio(path_id: str) -> str:
    parts = path_id.split("/")
    if len(parts) != 3 or not parts[1].startswith("radio_pluto_"):
        raise ValueError(f"malformed path identity: {path_id}")
    return parts[1]


def _measurement_track(
    rows: list[tuple[int, str, str, float, float]],
) -> tuple[MeasurementTrack, IntArray]:
    if len(rows) < 6:
        raise ValueError("measurement bundle contains too few rows")
    rows.sort(key=lambda item: (item[0], item[1]))
    path_ids = tuple(sorted({item[1] for item in rows}))
    radio_ids = tuple(sorted({item[2] for item in rows}))
    path_lookup = {value: index for index, value in enumerate(path_ids)}
    radio_lookup = {value: index for index, value in enumerate(radio_ids)}
    utc_ns = np.asarray([item[0] for item in rows], dtype=np.int64)
    reference_ns = int(np.median(utc_ns))
    track = MeasurementTrack(
        time_s=(utc_ns.astype(np.float64) - reference_ns) / 1e9,
        fit_cfo_hz=np.asarray([item[3] for item in rows], dtype=np.float64),
        response_cfo_hz=np.asarray([item[4] for item in rows], dtype=np.float64),
        path_index=np.asarray([path_lookup[item[1]] for item in rows], dtype=np.int64),
        radio_index=np.asarray([radio_lookup[item[2]] for item in rows], dtype=np.int64),
        path_ids=path_ids,
        radio_ids=radio_ids,
    )
    return track, utc_ns


def load_bound_tracks(protocol: dict[str, Any]) -> tuple[BoundTrack, ...]:
    """Load frozen rows and reduce multi-radio measurements to 20 ms medians."""

    inputs = protocol["measurement_inputs"]
    frame_binding = inputs["multi_radio_frame_ledger"]
    frame_path = ROOT / str(frame_binding["path"])
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    with gzip.open(frame_path, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if (
                row.get("training_supported") is not True
                or row.get("reference_utc_ns") is None
                or row.get("normalized_even_cfo_hz") is None
            ):
                continue
            capture_id = str(row["capture_session_id"])
            path_id = str(row["path_id"])
            utc_ns = int(row["reference_utc_ns"])
            grouped[(capture_id, path_id, utc_ns // BIN_NS)].append(row)
    by_capture: dict[str, list[tuple[int, str, str, float, float]]] = defaultdict(list)
    for (capture_id, path_id, _), frame_values in grouped.items():
        binned_utc_ns = int(
            round(float(np.median([int(item["reference_utc_ns"]) for item in frame_values])))
        )
        even = float(np.median([float(item["normalized_even_cfo_hz"]) for item in frame_values]))
        odd_values = [
            float(item["normalized_odd_cfo_hz"])
            for item in frame_values
            if item.get("normalized_odd_cfo_hz") is not None
        ]
        odd = float(np.median(odd_values)) if odd_values else math.nan
        by_capture[capture_id].append((binned_utc_ns, path_id, _path_radio(path_id), even, odd))

    primary_map = inputs["primary_capture_bundle"]
    tracks: list[BoundTrack] = []
    for capture_id in frame_binding["capture_ids"]:
        track, track_utc_ns = _measurement_track(by_capture[str(capture_id)])
        primary = primary_map[str(capture_id)] == "multi_radio_frame_ledger"
        tracks.append(
            BoundTrack(
                capture_id=str(capture_id),
                bundle_id="multi-radio-frames",
                data_kind="single-frame even/odd Qin CFO",
                track=track,
                utc_ns=track_utc_ns,
                rf_frequency_hz=float(frame_binding["reference_sky_frequency_hz"]),
                primary=primary,
            )
        )

    long_binding = inputs["long_150802_ledger"]
    long_path = ROOT / str(long_binding["path"])
    long_grouped: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for line in long_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        row_utc_ns = int(long_binding["stream_first_sample_utc_ns"]) + round(
            float(row[str(long_binding["measurement_time_field"])]) * 1e9
        )
        long_grouped[row_utc_ns // BIN_NS].append(
            (row_utc_ns, float(row[str(long_binding["response_field"])]))
        )
    path_id = str(long_binding["path_id"])
    radio_id = str(long_binding["physical_radio_id"])
    long_rows: list[tuple[int, str, str, float, float]] = []
    for long_values in long_grouped.values():
        binned_utc_ns = int(round(float(np.median([item[0] for item in long_values]))))
        cfo = float(np.median([item[1] for item in long_values]))
        long_rows.append((binned_utc_ns, path_id, radio_id, cfo, cfo))
    track, track_utc_ns = _measurement_track(long_rows)
    tracks.append(
        BoundTrack(
            capture_id=str(long_binding["capture_id"]),
            bundle_id="long-direct-glrt",
            data_kind="13.8 s direct-GLRT CFO",
            track=track,
            utc_ns=track_utc_ns,
            rf_frequency_hz=float(long_binding["rf_frequency_hz"]),
            primary=True,
        )
    )
    return tuple(tracks)


def _uniform_grid(start_ns: int, stop_ns: int, spacing_s: float) -> SamplingGrid:
    if stop_ns <= start_ns:
        stop_ns = start_ns + 2
    step_ns = max(1, round(spacing_s * 1e9))
    count = max(3, math.ceil((stop_ns - start_ns) / step_ns) + 1)
    values = tuple(start_ns + index * step_ns for index in range(count))
    return SamplingGrid(values, count // 2, step_ns / 1e9)


def _exact_grid(utc_ns: IntArray) -> tuple[SamplingGrid, IntArray]:
    unique, inverse = np.unique(utc_ns, return_inverse=True)
    if unique.size < 3:
        raise ValueError("candidate prediction needs at least three unique UTC bins")
    spacing_s = float(np.median(np.diff(unique)) / 1e9)
    return (
        SamplingGrid(tuple(int(value) for value in unique), unique.size // 2, spacing_s),
        np.asarray(inverse, dtype=np.int64),
    )


def candidate_population(
    catalogue: ElementSetCatalogue,
    utc_ns: IntArray,
    rf_frequency_hz: float,
    observer_name: str,
) -> CandidatePopulation:
    """Build an exact horizon union and CFO bank at actual measurement UTCs."""

    observer = resolve_preset(observer_name)
    coarse_grid = _uniform_grid(int(np.min(utc_ns)), int(np.max(utc_ns)), COARSE_SPACING_S)
    coarse = observe_grid(propagate_grid(catalogue, coarse_grid), observer, coarse_grid)
    margin = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    plausible = coarse.usable & (np.min(coarse.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    coarse_indices = np.flatnonzero(plausible & (np.max(coarse.elevation_deg, axis=1) > -margin))
    exact_grid, inverse = _exact_grid(utc_ns)
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
    prediction_unique = np.asarray(
        doppler_shift_hz(rf_frequency_hz, exact.range_rate_km_s[rows]),
        dtype=np.float64,
    )
    norad = np.asarray(
        [catalogue.satellite_numbers[int(index)] for index in indices], dtype=np.int64
    )
    return CandidatePopulation(
        catalogue_indices=indices,
        norad_ids=norad,
        names=tuple(catalogue.names[int(index)] for index in indices),
        prediction_hz=prediction_unique[:, inverse],
        minimum_elevation_deg=np.min(exact.elevation_deg[rows], axis=1),
        maximum_elevation_deg=np.max(exact.elevation_deg[rows], axis=1),
        coarse_candidate_count=int(coarse_indices.size),
    )


def _fit_hierarchy(
    track: MeasurementTrack,
    prediction: FloatArray,
    training: BoolArray,
    evaluation: BoolArray,
    model: dict[str, Any],
) -> CandidateFitBank:
    return fit_hierarchical_candidates(
        track,
        prediction,
        training,
        evaluation,
        measurement_scale_hz=float(model["measurement_scale_hz"]),
        rate_prior_sigma_hz_s=float(model["rate_departure_prior_sigma_hz_s"]),
        maximum_rate_hz_s=float(model["rate_departure_hard_bound_hz_s"]),
    )


def _rank_rows(population: CandidatePopulation, fit: CandidateFitBank) -> list[dict[str, Any]]:
    order = np.lexsort((population.norad_ids, fit.penalized_training_rms_hz))
    rows = []
    for rank, row in enumerate(order, start=1):
        rows.append(
            {
                "rank": rank,
                "catalogue_index": int(population.catalogue_indices[row]),
                "norad_id": int(population.norad_ids[row]),
                "name": population.names[row],
                "penalized_training_rms_hz": float(fit.penalized_training_rms_hz[row]),
                "training_rms_hz": float(fit.training_rms_hz[row]),
                "heldout_rms_hz": float(fit.evaluation_rms_hz[row]),
                "full_response_rms_hz": float(fit.full_response_rms_hz[row]),
                "path_offsets_hz": [float(value) for value in fit.path_offsets_hz[row]],
                "radio_rate_departures_hz_s": [
                    float(value) for value in fit.radio_rate_departures_hz_s[row]
                ],
                "minimum_elevation_deg": float(population.minimum_elevation_deg[row]),
                "maximum_elevation_deg": float(population.maximum_elevation_deg[row]),
            }
        )
    return rows


def _minimum_fit_score(
    bound: BoundTrack,
    catalogue: ElementSetCatalogue,
    utc_ns: IntArray,
    observer: str,
    training: BoolArray,
    evaluation: BoolArray,
    model: dict[str, Any],
) -> tuple[float, int, int]:
    population = candidate_population(catalogue, utc_ns, bound.rf_frequency_hz, observer)
    fit = _fit_hierarchy(bound.track, population.prediction_hz, training, evaluation, model)
    selected = int(np.argmin(fit.penalized_training_rms_hz))
    return (
        float(fit.penalized_training_rms_hz[selected]),
        int(population.norad_ids[selected]),
        int(population.norad_ids.size),
    )


def _grid_value_is_interior(value: float, minimum: float, maximum: float, step: float) -> bool:
    return not math.isclose(value, minimum, abs_tol=step / 2.0) and not math.isclose(
        value, maximum, abs_tol=step / 2.0
    )


def _support_disposition(
    bound: BoundTrack,
    reduction: dict[str, Any],
) -> tuple[bool, list[dict[str, int | str]]]:
    track = bound.track
    training = chronological_mask(track.time_s, float(reduction["chronological_training_fraction"]))
    evaluation = ~training & np.isfinite(track.response_cfo_hz)
    support_by_path: list[dict[str, int | str]] = []
    for path, path_id in enumerate(track.path_ids):
        support_by_path.append(
            {
                "path_id": path_id,
                "physical_radio_id": track.radio_ids[
                    int(track.radio_index[np.flatnonzero(track.path_index == path)[0]])
                ],
                "training_bin_count": int(np.count_nonzero(training & (track.path_index == path))),
                "evaluation_bin_count": int(
                    np.count_nonzero(evaluation & (track.path_index == path))
                ),
            }
        )
    if bound.data_kind.startswith("single-frame"):
        support_pass = (
            len(track.path_ids) >= int(reduction["multi_radio_minimum_paths"])
            and len(track.radio_ids) >= int(reduction["multi_radio_minimum_physical_radios"])
            and all(
                int(row["training_bin_count"])
                >= int(reduction["multi_radio_minimum_training_bins_per_path"])
                and int(row["evaluation_bin_count"])
                >= int(reduction["multi_radio_minimum_evaluation_bins_per_path"])
                for row in support_by_path
            )
        )
    else:
        support_pass = track.time_s.size >= int(reduction["long_track_minimum_total_bins"])
    return support_pass, support_by_path


def evaluate_bundle(
    bound: BoundTrack,
    catalogue: ElementSetCatalogue,
    protocol: dict[str, Any],
    *,
    run_controls: bool,
) -> tuple[dict[str, Any], CandidatePopulation, CandidateFitBank]:
    """Score one fixed bundle under every preregistered model and control."""

    reduction = protocol["measurement_reduction"]
    model = protocol["models"]["primary_hierarchical_receiver_nuisance"]
    evaluation_config = protocol["evaluation"]
    observer = str(protocol["observer_and_geometry"]["observer_preset"])
    track = bound.track
    training = chronological_mask(track.time_s, float(reduction["chronological_training_fraction"]))
    response_available = np.isfinite(track.response_cfo_hz)
    evaluation = ~training & response_available
    support_pass, support_by_path = _support_disposition(bound, reduction)
    if not support_pass:
        raise ValueError(f"frozen support gate failed for {bound.capture_id}/{bound.bundle_id}")

    population = candidate_population(
        catalogue,
        bound.utc_ns,
        bound.rf_frequency_hz,
        observer,
    )
    if population.norad_ids.size < 2:
        raise ValueError("candidate population has fewer than two visible Starlinks")
    baseline = fit_offset_candidates(track, population.prediction_hz, training, evaluation)
    hierarchy = _fit_hierarchy(track, population.prediction_hz, training, evaluation, model)
    baseline_rows = _rank_rows(population, baseline)
    hierarchy_rows = _rank_rows(population, hierarchy)
    winner = hierarchy_rows[0]
    runner = hierarchy_rows[1]
    linear_null = fit_radio_polynomial_null(track, training, evaluation, degree=1)
    quadratic_null = fit_radio_polynomial_null(track, training, evaluation, degree=2)

    rolling = []
    for item in evaluation_config["rolling_origins"]:
        train_mask = chronological_mask(track.time_s, float(item["training_stop_fraction"]))
        response_mask = (
            chronological_block_mask(
                track.time_s,
                float(item["training_stop_fraction"]),
                float(item["evaluation_stop_fraction"]),
            )
            & response_available
        )
        fit = _fit_hierarchy(track, population.prediction_hz, train_mask, response_mask, model)
        selected = int(np.argmin(fit.penalized_training_rms_hz))
        rolling.append(
            {
                **item,
                "winner_norad_id": int(population.norad_ids[selected]),
                "winner_penalized_training_rms_hz": float(fit.penalized_training_rms_hz[selected]),
                "winner_heldout_rms_hz": float(fit.evaluation_rms_hz[selected]),
            }
        )

    time_control = protocol["models"]["bounded_clock_time_sensitivity"]
    shifts = np.arange(
        float(time_control["minimum_shift_s"]),
        float(time_control["maximum_shift_s"]) + 0.5 * float(time_control["step_s"]),
        float(time_control["step_s"]),
    )
    time_rows = []
    for shift_s in shifts:
        shifted_utc = bound.utc_ns + round(float(shift_s) * 1e9)
        shifted_grid, inverse = _exact_grid(shifted_utc)
        observed = observe_grid(
            propagate_grid(
                catalogue,
                shifted_grid,
                indices=population.catalogue_indices.tolist(),
            ),
            resolve_preset(observer),
            shifted_grid,
        )
        prediction = np.asarray(
            doppler_shift_hz(bound.rf_frequency_hz, observed.range_rate_km_s),
            dtype=np.float64,
        )[:, inverse]
        fit = _fit_hierarchy(track, prediction, training, evaluation, model)
        selected = int(np.argmin(fit.penalized_training_rms_hz))
        time_rows.append(
            {
                "shift_s": float(shift_s),
                "winner_norad_id": int(population.norad_ids[selected]),
                "winner_penalized_training_rms_hz": float(fit.penalized_training_rms_hz[selected]),
                "winner_heldout_rms_hz": float(fit.evaluation_rms_hz[selected]),
            }
        )
    best_time = min(
        time_rows,
        key=lambda item: (
            item["winner_penalized_training_rms_hz"],
            abs(item["shift_s"]),
            item["shift_s"],
        ),
    )

    wrong_time_rows = []
    permutation_rows = []
    wrong_time_p: float | None = None
    permutation_p: float | None = None
    if run_controls:
        for offset_s in evaluation_config["wrong_time_offsets_s"]:
            score, norad, candidate_count = _minimum_fit_score(
                bound,
                catalogue,
                bound.utc_ns + int(offset_s) * 1_000_000_000,
                observer,
                training,
                evaluation,
                model,
            )
            wrong_time_rows.append(
                {
                    "time_offset_s": int(offset_s),
                    "candidate_count": candidate_count,
                    "winner_norad_id": norad,
                    "best_penalized_training_rms_hz": score,
                }
            )
        true_score = float(winner["penalized_training_rms_hz"])
        wrong_time_p = (
            1 + sum(row["best_penalized_training_rms_hz"] <= true_score for row in wrong_time_rows)
        ) / (1 + len(wrong_time_rows))

        rng = np.random.default_rng(int(evaluation_config["permutation_seed"]))
        for index in range(int(evaluation_config["permutation_count"])):
            permuted = permute_fit_response_within_paths(track, training, rng)
            fit = _fit_hierarchy(
                permuted,
                population.prediction_hz,
                training,
                evaluation,
                model,
            )
            selected = int(np.argmin(fit.penalized_training_rms_hz))
            permutation_rows.append(
                {
                    "permutation_index": index,
                    "winner_norad_id": int(population.norad_ids[selected]),
                    "best_penalized_training_rms_hz": float(
                        fit.penalized_training_rms_hz[selected]
                    ),
                }
            )
        permutation_p = (
            1 + sum(row["best_penalized_training_rms_hz"] <= true_score for row in permutation_rows)
        ) / (1 + len(permutation_rows))

    gate_values = {
        "heldout_rms_le_100_hz": float(winner["heldout_rms_hz"]) <= 100.0,
        "quadratic_advantage_ge_20_hz": (
            quadratic_null.evaluation_rms_hz - float(winner["heldout_rms_hz"])
        )
        >= 20.0,
        "training_runner_margin_ge_100_hz": (
            float(runner["penalized_training_rms_hz"]) - float(winner["penalized_training_rms_hz"])
        )
        >= 100.0,
        "heldout_runner_margin_ge_50_hz": (
            float(runner["heldout_rms_hz"]) - float(winner["heldout_rms_hz"])
        )
        >= 50.0,
        "baseline_and_hierarchy_winner_agree": (
            int(baseline_rows[0]["norad_id"]) == int(winner["norad_id"])
        ),
        "rolling_winner_stable": all(
            int(item["winner_norad_id"]) == int(winner["norad_id"]) for item in rolling
        ),
        "bounded_time_winner_stable_and_interior": (
            int(best_time["winner_norad_id"]) == int(winner["norad_id"])
            and _grid_value_is_interior(
                float(best_time["shift_s"]),
                float(time_control["minimum_shift_s"]),
                float(time_control["maximum_shift_s"]),
                float(time_control["step_s"]),
            )
        ),
        "wrong_time_fwer_le_0_05": wrong_time_p is not None and wrong_time_p <= 0.05,
        "permutation_p_le_0_05": permutation_p is not None and permutation_p <= 0.05,
    }
    candidate_evidence_pass = all(gate_values.values())
    result = {
        "capture_id": bound.capture_id,
        "bundle_id": bound.bundle_id,
        "data_kind": bound.data_kind,
        "primary": bound.primary,
        "start_utc_ns": int(np.min(bound.utc_ns)),
        "stop_utc_ns": int(np.max(bound.utc_ns)),
        "start_utc": _iso_utc(int(np.min(bound.utc_ns))),
        "stop_utc": _iso_utc(int(np.max(bound.utc_ns))),
        "duration_s": float((np.max(bound.utc_ns) - np.min(bound.utc_ns)) / 1e9),
        "measurement_bin_count": int(track.time_s.size),
        "path_count": len(track.path_ids),
        "physical_radio_count": len(track.radio_ids),
        "support_by_path": support_by_path,
        "support_gate_pass": support_pass,
        "coarse_candidate_count": population.coarse_candidate_count,
        "visible_candidate_count": int(population.norad_ids.size),
        "baseline_top10": baseline_rows[:10],
        "hierarchical_top10": hierarchy_rows[:10],
        "full_hierarchical_ranking": hierarchy_rows,
        "linear_null": asdict(linear_null),
        "quadratic_null": asdict(quadratic_null),
        "rolling_origins": rolling,
        "bounded_time_sensitivity": time_rows,
        "bounded_time_best": best_time,
        "wrong_time_controls": wrong_time_rows,
        "wrong_time_familywise_p": wrong_time_p,
        "permutation_controls": permutation_rows,
        "permutation_p": permutation_p,
        "candidate_evidence_gates": gate_values,
        "candidate_evidence_pass": candidate_evidence_pass,
        "recovered_track": True,
    }
    return result, population, hierarchy


def latest_tle_sensitivity(
    bound: BoundTrack,
    primary_catalogue: ElementSetCatalogue,
    latest_catalogue: ElementSetCatalogue,
    primary_result: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Fail if the durable and latest-causal 150802 visible results differ."""

    observer = str(protocol["observer_and_geometry"]["observer_preset"])
    reduction = protocol["measurement_reduction"]
    model = protocol["models"]["primary_hierarchical_receiver_nuisance"]
    training = chronological_mask(
        bound.track.time_s, float(reduction["chronological_training_fraction"])
    )
    evaluation = ~training & np.isfinite(bound.track.response_cfo_hz)
    primary_population = candidate_population(
        primary_catalogue, bound.utc_ns, bound.rf_frequency_hz, observer
    )
    latest_population = candidate_population(
        latest_catalogue, bound.utc_ns, bound.rf_frequency_hz, observer
    )
    primary_ids = [int(value) for value in primary_population.norad_ids]
    latest_ids = [int(value) for value in latest_population.norad_ids]
    visible_equal = primary_ids == latest_ids
    if not visible_equal:
        raise ValueError("latest-causal TLE changes the 150802 visible population")
    primary_fit = _fit_hierarchy(
        bound.track, primary_population.prediction_hz, training, evaluation, model
    )
    latest_fit = _fit_hierarchy(
        bound.track, latest_population.prediction_hz, training, evaluation, model
    )
    training_difference = float(
        np.max(np.abs(primary_fit.penalized_training_rms_hz - latest_fit.penalized_training_rms_hz))
    )
    heldout_difference = float(
        np.max(np.abs(primary_fit.evaluation_rms_hz - latest_fit.evaluation_rms_hz))
    )
    primary_order = np.lexsort(
        (primary_population.norad_ids, primary_fit.penalized_training_rms_hz)
    )
    latest_order = np.lexsort((latest_population.norad_ids, latest_fit.penalized_training_rms_hz))
    ranking_equal = np.array_equal(
        primary_population.norad_ids[primary_order], latest_population.norad_ids[latest_order]
    )
    metric_equal = training_difference <= 1e-9 and heldout_difference <= 1e-9
    expected_winner = int(primary_result["hierarchical_top10"][0]["norad_id"])
    latest_winner = int(latest_population.norad_ids[latest_order[0]])
    if not ranking_equal or not metric_equal or latest_winner != expected_winner:
        raise ValueError("latest-causal TLE changes a 150802 ranking or metric")
    return {
        "visible_population_equal": visible_equal,
        "visible_candidate_count": len(primary_ids),
        "full_ranking_equal": ranking_equal,
        "maximum_penalized_training_rms_difference_hz": training_difference,
        "maximum_heldout_rms_difference_hz": heldout_difference,
        "winner_norad_id": latest_winner,
        "all_required_metrics_identical": metric_equal,
    }


def _render_results(output_root: Path, evidence: dict[str, Any]) -> list[Path]:
    primary = [item for item in evidence["bundle_results"] if item["primary"]]
    output_root.mkdir(parents=True, exist_ok=True)
    ranking_path = output_root / "candidate-ranking-and-nulls.png"
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    for ax, result in zip(axes.flat, primary, strict=True):
        rows = result["hierarchical_top10"]
        labels = [str(row["norad_id"]) for row in rows]
        values = [row["heldout_rms_hz"] for row in rows]
        ax.bar(np.arange(len(rows)), values, color="tab:blue", alpha=0.75)
        ax.axhline(
            result["quadratic_null"]["evaluation_rms_hz"],
            color="tab:orange",
            linestyle="--",
            label="quadratic radio null",
        )
        ax.axhline(100.0, color="black", linestyle=":", label="100 Hz identity gate")
        ax.set_xticks(np.arange(len(rows)), labels, rotation=45, ha="right")
        ax.set_ylabel("Chronological held-out RMS (Hz)")
        ax.set_title(f"{result['capture_id'][4:19]} · {result['data_kind']}")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Full-catalog training winners scored on future CFO", fontsize=16)
    fig.savefig(ranking_path, dpi=180)
    plt.close(fig)

    controls_path = output_root / "baseline-hierarchy-and-controls.png"
    labels = [item["capture_id"][13:19] for item in primary]
    baseline = [item["baseline_top10"][0]["heldout_rms_hz"] for item in primary]
    hierarchy = [item["hierarchical_top10"][0]["heldout_rms_hz"] for item in primary]
    quadratic = [item["quadratic_null"]["evaluation_rms_hz"] for item in primary]
    wrong = [item["wrong_time_familywise_p"] for item in primary]
    permutation = [item["permutation_p"] for item in primary]
    x = np.arange(len(primary))
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    width = 0.25
    axes[0].bar(x - width, baseline, width, label="fixed-time offset-only")
    axes[0].bar(x, hierarchy, width, label="hierarchical receiver nuisance")
    axes[0].bar(x + width, quadratic, width, label="quadratic radio null")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Held-out RMS (Hz)")
    axes[0].set_title("Prediction, not in-sample completion")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[1].bar(x - width / 2, wrong, width, label="40-field wrong-time FWER")
    axes[1].bar(x + width / 2, permutation, width, label="20-permutation p")
    axes[1].axhline(0.05, color="black", linestyle="--", label="promotion gate")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_ylabel("Empirical p")
    axes[1].set_title("Candidate multiplicity and temporal-structure controls")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.suptitle("Retrospective association baseline and nuisance controls", fontsize=16)
    fig.savefig(controls_path, dpi=180)
    plt.close(fig)

    recovery_path = output_root / "track-recovery-and-gates.png"
    gate_names = list(primary[0]["candidate_evidence_gates"])
    gate_matrix = np.asarray(
        [[bool(item["candidate_evidence_gates"][name]) for name in gate_names] for item in primary],
        dtype=float,
    )
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), constrained_layout=True)
    counts = evidence["aggregate"]
    axes[0].bar(
        ["baseline\nrecovered", "hierarchy\nrecovered", "candidate\nevidence", "secure\nNORAD"],
        [
            counts["baseline_recovered_track_count"],
            counts["primary_recovered_track_count"],
            counts["candidate_evidence_track_count"],
            counts["secure_norad_count"],
        ],
        color=["0.55", "tab:blue", "tab:orange", "tab:green"],
    )
    axes[0].set_ylim(0, max(4.5, counts["primary_recovered_track_count"] + 0.5))
    axes[0].set_ylabel("Count")
    axes[0].set_title("A ranked track is not a secure identity")
    axes[0].grid(axis="y", alpha=0.25)
    image = axes[1].imshow(gate_matrix, cmap="RdYlGn", vmin=0.0, vmax=1.0, aspect="auto")
    axes[1].set_yticks(np.arange(len(primary)), labels)
    short_names = [
        "RMS",
        "beats quad",
        "train margin",
        "future margin",
        "nuisance stable",
        "rolling stable",
        "time stable",
        "wrong-time",
        "permutation",
    ]
    axes[1].set_xticks(np.arange(len(gate_names)), short_names, rotation=45, ha="right")
    axes[1].set_title("Complete candidate-evidence gate ledger")
    for row in range(gate_matrix.shape[0]):
        for column in range(gate_matrix.shape[1]):
            axes[1].text(
                column,
                row,
                "PASS" if gate_matrix[row, column] else "FAIL",
                ha="center",
                va="center",
                fontsize=7,
            )
    fig.colorbar(image, ax=axes[1], ticks=[0, 1], label="gate result")
    fig.suptitle("Track recovery versus secure Starlink identity", fontsize=16)
    fig.savefig(recovery_path, dpi=180)
    plt.close(fig)
    return [ranking_path, controls_path, recovery_path]


def run(protocol_path: Path, output_root: Path) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    tracks = load_bound_tracks(protocol)
    tle_bindings = protocol["tle_inputs"]["snapshots"]
    catalogue_cache: dict[str, ElementSetCatalogue] = {}
    text_cache: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    populations: dict[tuple[str, str], CandidatePopulation] = {}
    fits: dict[tuple[str, str], CandidateFitBank] = {}
    for bound in tracks:
        binding = tle_bindings[bound.capture_id]
        digest = str(binding["raw_sha256"])
        if digest not in catalogue_cache:
            text = Path(str(binding["raw_path"])).read_text(encoding="ascii")
            text_cache[digest] = text
            catalogue_cache[digest] = parse_element_sets(text)
        support_pass, support_by_path = _support_disposition(
            bound, protocol["measurement_reduction"]
        )
        if not support_pass and not bound.primary:
            results.append(
                {
                    "capture_id": bound.capture_id,
                    "bundle_id": bound.bundle_id,
                    "data_kind": bound.data_kind,
                    "primary": False,
                    "measurement_bin_count": int(bound.track.time_s.size),
                    "path_count": len(bound.track.path_ids),
                    "physical_radio_count": len(bound.track.radio_ids),
                    "support_by_path": support_by_path,
                    "support_gate_pass": False,
                    "recovered_track": False,
                    "candidate_evidence_pass": False,
                    "disposition": "diagnostic bundle failed frozen primary support minima",
                }
            )
            continue
        result, population, fit = evaluate_bundle(
            bound,
            catalogue_cache[digest],
            protocol,
            run_controls=bound.primary,
        )
        results.append(result)
        populations[(bound.capture_id, bound.bundle_id)] = population
        fits[(bound.capture_id, bound.bundle_id)] = fit

    primary_results: list[dict[str, Any]] = [item for item in results if item["primary"]]
    primary_by_capture = {item["capture_id"]: item for item in primary_results}
    long_bound = next(
        item
        for item in tracks
        if item.capture_id == "cap-20260825T150802-473cb5bbcbd6"
        and item.bundle_id == "long-direct-glrt"
    )
    primary_binding = tle_bindings[long_bound.capture_id]
    primary_digest = str(primary_binding["raw_sha256"])
    latest_binding = protocol["tle_inputs"]["source_sensitivity"][long_bound.capture_id]
    latest_text = Path(str(latest_binding["raw_path"])).read_text(encoding="ascii")
    latest_catalogue = parse_element_sets(latest_text)
    sensitivity = latest_tle_sensitivity(
        long_bound,
        catalogue_cache[primary_digest],
        latest_catalogue,
        primary_by_capture[long_bound.capture_id],
        protocol,
    )
    primary_records = {
        item.satellite_number: item.text
        for item in parse_element_set_records(text_cache[primary_digest])
    }
    latest_records = {
        item.satellite_number: item.text for item in parse_element_set_records(latest_text)
    }
    changed = sorted(
        item
        for item in set(primary_records) | set(latest_records)
        if primary_records.get(item) != latest_records.get(item)
    )
    visible_ids = set(
        int(value) for value in populations[(long_bound.capture_id, long_bound.bundle_id)].norad_ids
    )
    sensitivity["changed_catalogue_norad_ids"] = changed
    sensitivity["changed_visible_norad_ids"] = sorted(visible_ids & set(changed))
    if sensitivity["changed_visible_norad_ids"]:
        raise ValueError("latest-causal TLE changed a visible 150802 element record")

    passing_by_norad: dict[int, set[str]] = defaultdict(set)
    for result in primary_results:
        if result["candidate_evidence_pass"]:
            passing_by_norad[int(result["hierarchical_top10"][0]["norad_id"])].add(
                str(result["capture_id"])
            )
    secure = sorted(norad for norad, captures in passing_by_norad.items() if len(captures) >= 2)
    recurrence = []
    all_winners = sorted(
        {int(item["hierarchical_top10"][0]["norad_id"]) for item in primary_results}
    )
    for norad in all_winners:
        appearances = [
            {
                "capture_id": item["capture_id"],
                "candidate_evidence_pass": item["candidate_evidence_pass"],
            }
            for item in primary_results
            if int(item["hierarchical_top10"][0]["norad_id"]) == norad
        ]
        recurrence.append(
            {
                "norad_id": norad,
                "primary_capture_appearances": appearances,
                "independent_capture_count": len(appearances),
                "passing_capture_count": sum(
                    bool(item["candidate_evidence_pass"]) for item in appearances
                ),
                "secure_norad": norad in secure,
            }
        )

    baseline_future_rms = np.asarray(
        [float(item["baseline_top10"][0]["heldout_rms_hz"]) for item in primary_results],
        dtype=np.float64,
    )
    hierarchy_future_rms = np.asarray(
        [float(item["hierarchical_top10"][0]["heldout_rms_hz"]) for item in primary_results],
        dtype=np.float64,
    )
    baseline_equal_capture_rms = float(np.sqrt(np.mean(baseline_future_rms**2)))
    hierarchy_equal_capture_rms = float(np.sqrt(np.mean(hierarchy_future_rms**2)))

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "protocol": {
            "path": str(protocol_path.relative_to(ROOT)),
            "sha256": _sha256(protocol_path),
        },
        "source_provenance": {
            "dataset_policy_sha256": protocol["authority"]["dataset_policy_sha256"],
            "measurement_inputs": protocol["measurement_inputs"],
            "tle_inputs": protocol["tle_inputs"],
            "observer": protocol["observer_and_geometry"],
            "mixed_estimator_cohort": True,
            "new_rf_collected": False,
            "holdout_foundation_opened": False,
        },
        "execution_dispositions": [
            {
                "stage": "first bounded runner attempt",
                "outcome": "stopped before artifact publication at the preregistered "
                "150802 frame-diagnostic support gate",
                "correction": "retain that diagnostic as non-evaluable; keep 30/20 minima, "
                "all four primary inputs, all candidate gates, and all controls unchanged",
                "path_substitution_or_threshold_change": False,
            }
        ],
        "bundle_results": results,
        "latest_causal_150802_tle_sensitivity": sensitivity,
        "recurrence": recurrence,
        "aggregate": {
            "unique_primary_capture_count": len(primary_results),
            "diagnostic_bundle_count": len(results) - len(primary_results),
            "baseline_recovered_track_count": sum(
                bool(item["recovered_track"]) for item in primary_results
            ),
            "primary_recovered_track_count": sum(
                bool(item["recovered_track"]) for item in primary_results
            ),
            "candidate_evidence_track_count": sum(
                bool(item["candidate_evidence_pass"]) for item in primary_results
            ),
            "secure_norad_ids": secure,
            "secure_norad_count": len(secure),
            "baseline_unique_winner_count": len(
                {int(item["baseline_top10"][0]["norad_id"]) for item in primary_results}
            ),
            "primary_unique_winner_count": len(
                {int(item["hierarchical_top10"][0]["norad_id"]) for item in primary_results}
            ),
            "baseline_equal_capture_future_rms_hz": baseline_equal_capture_rms,
            "hierarchy_equal_capture_future_rms_hz": hierarchy_equal_capture_rms,
            "hierarchy_to_baseline_future_rms_ratio": (
                hierarchy_equal_capture_rms / baseline_equal_capture_rms
            ),
            "hierarchy_future_rms_win_count": int(
                np.count_nonzero(hierarchy_future_rms < baseline_future_rms)
            ),
        },
        "interpretation_limits": [
            "The cohort was already opened; upstream branch selection is not a blind "
            "acquisition test.",
            "Three primary tracks use single-frame even/odd Qin CFO; 150802 uses a "
            "direct-GLRT long arc.",
            "The catalogue is Starlink-only and geometry is conditional on a reviewed site preset.",
            "Receiver rate departures are nuisance parameters, not clock-drift or "
            "physical truth measurements.",
            "A catalog-ranked track is not a secure NORAD identity.",
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    evidence_path = output_root / "retrospective-satellite-nuisance-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    figures = _render_results(output_root, evidence)
    manifest = {
        "schema": "org.leo.research.retrospective-satellite-nuisance-artifacts/v1",
        "protocol_sha256": _sha256(protocol_path),
        "artifacts": {
            path.name: {"sha256": _sha256(path), "byte_size": path.stat().st_size}
            for path in [evidence_path, *figures]
        },
    }
    manifest_path = output_root / "artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    evidence["artifact_manifest_sha256"] = _sha256(manifest_path)
    return evidence


def main() -> None:
    arguments = _arguments()
    evidence = run(arguments.protocol.resolve(), arguments.output_root.resolve())
    print(json.dumps(evidence["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
