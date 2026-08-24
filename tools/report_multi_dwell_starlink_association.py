"""Evaluate time-specific Starlink identities across a fresh multi-dwell linear rerun.

The satellite identity and bounded epoch adjustment are selected using only the
chronologically first 60 percent of each track.  The remaining 40 percent is
reserved for model discrimination against a radio-only straight-line null.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sqlalchemy.orm import Session

from leo.acquisition.starlink_tuning import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_rf_center_frequency_hz,
)
from leo.catalog.database import create_catalog_engine
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.storage import BulkUriResolver

try:
    from tools import report_five_dwell_degree1_only as d1
    from tools import report_five_dwell_tle_cone as base
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
    import report_five_dwell_degree1_only as d1
    import report_five_dwell_tle_cone as base


DEFAULT_SESSION_IDS = (
    "cap-20260821T201522-841b2a20e151",
    "cap-20260821T193701-87f96f47e73f",
    "cap-20260821T193440-17c2e0ebef6a",
    "cap-20260821T190912-ffd441556880",
    "cap-20260821T190701-7a5d980ec1c6",
    "cap-20260821T183005-a987f97b643c",
    "cap-20260821T162727-0abff1c9aa8e",
    "cap-20260821T162517-85cfb560afe8",
    "cap-20260821T162303-580cc01dffb5",
    "cap-20260821T161404-d421b003eb3b",
    "cap-20260821T161151-dcbe9267c25e",
    "cap-20260821T160941-a38f080a2122",
    "cap-20260821T160027-658dc7f1422e",
)
DEFAULT_SOURCE_EVIDENCE = Path(
    "reports/figures/2026_08_22_thirteen_dwell_starlink_association/five-dwell-d1only-evidence.json"
)
TRAIN_FRACTION = 0.60
MINIMUM_TRACK_DURATION_S = 5.0
MINIMUM_TRACK_OBSERVATIONS = 50
MINIMUM_VISIBILITY_FRACTION = 0.95
PRIMARY_EPOCH_BOUND_S = 0.30
WIDE_EPOCH_BOUND_S = 2.0
EPOCH_STEP_S = 0.05
PREDICTION_PADDING_S = 65.0
MODEL_DRIFT_BOUNDS_HZ_S = {
    "constant_offset": 0.0,
    "lnb_bounded_25": 25.0,
    "bounded_200": 200.0,
    "free_affine": 1_000_000.0,
}
SECURE_HOLDOUT_RMS_HZ = 500.0
SECURE_HOLDOUT_ADVANTAGE_HZ = 100.0
SECURE_RUNNER_UP_MARGIN_HZ = 100.0
SECURE_SCALAR_NULL_P = 0.05
SECURE_TLE_SHAPE_SENSITIVITY_HZ = 100.0
# The known Qin pilot cluster lies within this half-width of the configured RF
# center.  LNB LO uncertainty changes baseband offset/drift; it does not change
# the RF carrier used to scale geometric Doppler.
PILOT_RF_HALF_WIDTH_HZ = 937_500.0
RF_CONFIGURATION_TOLERANCE_HZ = 10.0
SITE_UNCERTAINTY_M = 50.0


@dataclass(frozen=True, slots=True)
class TrackSeries:
    time_s: np.ndarray
    cfo_hz: np.ndarray


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_DATABASE_URL", base.DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--bulk-root", type=Path, default=base.DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=base.DEFAULT_TLE_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, default=DEFAULT_SOURCE_EVIDENCE)
    parser.add_argument("--session-id", action="append", dest="session_ids", default=[])
    parser.add_argument("--provider", default=base.REQUIRED_TLE_PROVIDER)
    parser.add_argument("--horizon-deg", type=float, default=base.DEFAULT_HORIZON_DEG)
    parser.add_argument("--maximum-selected-per-path", type=int, default=16)
    return parser.parse_args()


def _git_revision(ref: str = "main") -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd()}", "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _track_series(track: d1.SelectedLinearTrack, dwell_start_ns: int) -> TrackSeries:
    offset_s = base._path_offset_s(track.path, dwell_start_ns)
    ordered = sorted(track.observations, key=lambda item: (item.time_s, item.observation_id))
    return TrackSeries(
        time_s=np.asarray([offset_s + item.time_s for item in ordered], dtype=np.float64),
        cfo_hz=np.asarray([item.tracking_cfo_hz for item in ordered], dtype=np.float64),
    )


def _temporal_split(times_s: np.ndarray, fraction: float = TRAIN_FRACTION) -> np.ndarray:
    if times_s.size < 6 or not 0.0 < fraction < 1.0:
        raise ValueError("held-out matching requires six observations and a valid split")
    order = np.argsort(times_s, kind="stable")
    cutoff = int(np.clip(math.ceil(fraction * order.size), 3, order.size - 3))
    train = np.zeros(order.size, dtype=bool)
    train[order[:cutoff]] = True
    return train


def _fit_affine_nuisance(
    times_s: np.ndarray,
    target_hz: np.ndarray,
    train: np.ndarray,
    maximum_drift_hz_s: float,
) -> tuple[np.ndarray, float, float, float]:
    reference_s = float(np.mean(times_s[train]))
    centered = times_s - reference_s
    design = np.column_stack((np.ones(times_s.size), centered))
    coefficients, *_ = np.linalg.lstsq(design[train], target_hz[train], rcond=None)
    drift_hz_s = float(np.clip(coefficients[1], -maximum_drift_hz_s, maximum_drift_hz_s))
    offset_hz = float(np.mean(target_hz[train] - drift_hz_s * centered[train]))
    residual_hz = target_hz - offset_hz - drift_hz_s * centered
    return residual_hz, reference_s, offset_hz, drift_hz_s


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(values, dtype=np.float64) ** 2)))


def _evaluate_prediction(
    series: TrackSeries,
    prediction_times_s: np.ndarray,
    predicted_doppler_hz: np.ndarray,
    *,
    train: np.ndarray,
    maximum_drift_hz_s: float,
    epoch_bound_s: float = PRIMARY_EPOCH_BOUND_S,
) -> dict[str, Any]:
    shifts = np.arange(
        -epoch_bound_s,
        epoch_bound_s + EPOCH_STEP_S / 2.0,
        EPOCH_STEP_S,
    )
    candidates = []
    for shift_s in shifts:
        shifted = series.time_s + float(shift_s)
        if shifted.min() < prediction_times_s[0] or shifted.max() > prediction_times_s[-1]:
            continue
        predicted = np.interp(shifted, prediction_times_s, predicted_doppler_hz)
        residual, reference_s, offset_hz, drift_hz_s = _fit_affine_nuisance(
            series.time_s,
            series.cfo_hz - predicted,
            train,
            maximum_drift_hz_s,
        )
        candidates.append(
            {
                "epoch_adjustment_s": float(shift_s),
                "nuisance_reference_s": reference_s,
                "fitted_frequency_offset_hz": offset_hz,
                "nuisance_drift_hz_s": drift_hz_s,
                "train_residual_rms_hz": _rms(residual[train]),
                "holdout_residual_rms_hz": _rms(residual[~train]),
                "full_residual_rms_hz": _rms(residual),
                "holdout_residual_median_absolute_hz": float(np.median(np.abs(residual[~train]))),
            }
        )
    if not candidates:
        raise ValueError("prediction grid does not cover the requested epoch search")
    # Identity and epoch are selected only on training data.  Holdout metrics
    # are deliberately absent from this ordering key.
    return min(
        candidates,
        key=lambda item: (
            item["train_residual_rms_hz"],
            abs(item["epoch_adjustment_s"]),
            item["epoch_adjustment_s"],
        ),
    )


def _linear_null(series: TrackSeries, train: np.ndarray) -> dict[str, float]:
    residual, reference_s, offset_hz, drift_hz_s = _fit_affine_nuisance(
        series.time_s,
        series.cfo_hz,
        train,
        1_000_000.0,
    )
    return {
        "reference_s": reference_s,
        "offset_hz": offset_hz,
        "drift_hz_s": drift_hz_s,
        "train_residual_rms_hz": _rms(residual[train]),
        "holdout_residual_rms_hz": _rms(residual[~train]),
        "full_residual_rms_hz": _rms(residual),
    }


def _rank_evaluations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            item["train_residual_rms_hz"],
            item["catalog_number"],
        ),
    )


def _uniform_grid(start_ns: int, end_ns: int, spacing_s: float = 0.25) -> SamplingGrid:
    step_ns = round(spacing_s * base._NS_PER_S)
    count = max(3, math.ceil((end_ns - start_ns) / step_ns) + 1)
    instants = tuple(start_ns + index * step_ns for index in range(count))
    anchor_index = count // 2
    return SamplingGrid(instants, anchor_index, spacing_s)


def _grid_times_from_dwell(grid: SamplingGrid, dwell_start_ns: int) -> np.ndarray:
    return (np.asarray(grid.utc_ns, dtype=np.float64) - dwell_start_ns) / base._NS_PER_S


def _candidate_catalogue(
    catalogue,
    observer: ObserverSiteV1,
    dwell_start_ns: int,
    duration_s: float,
    horizon_deg: float,
) -> tuple[tuple[base.ConeSatellite, ...], Any, np.ndarray]:
    grid = base._grid(dwell_start_ns, duration_s)
    times_s = _grid_times_from_dwell(grid, dwell_start_ns)
    propagated = propagate_grid(catalogue, grid)
    observed = observe_grid(propagated, observer, grid)
    satellites = base._cone_satellites(
        catalogue,
        observed,
        times_s,
        elevation_threshold_deg=horizon_deg,
        anchor_utc_ns=dwell_start_ns,
    )
    return satellites, propagated, times_s


def _prediction_bank(
    catalogue,
    satellites: tuple[base.ConeSatellite, ...],
    observer: ObserverSiteV1,
    dwell_start_ns: int,
    duration_s: float,
) -> tuple[SamplingGrid, np.ndarray, Any, Any]:
    grid = _uniform_grid(
        dwell_start_ns - round(PREDICTION_PADDING_S * base._NS_PER_S),
        dwell_start_ns + round((duration_s + PREDICTION_PADDING_S) * base._NS_PER_S),
    )
    indices = [item.catalogue_index for item in satellites]
    propagated = propagate_grid(catalogue, grid, indices=indices)
    observed = observe_grid(propagated, observer, grid)
    return grid, _grid_times_from_dwell(grid, dwell_start_ns), propagated, observed


def _visible_fraction(
    elevation_deg: np.ndarray,
    series: TrackSeries,
    times_s: np.ndarray,
    horizon: float,
) -> float:
    values = np.interp(series.time_s, times_s, elevation_deg)
    return float(np.mean(values >= horizon))


def _scalar_lookup(source: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (dwell["session_id"], track["trajectory_id"]): track["match"]
        for dwell in source["dwells"]
        for track in dwell["top_tracks"]
    }


def _scalar_shape_identity_agree(
    scalar_match: dict[str, Any], shape_best: dict[str, Any] | None
) -> bool:
    """Require the scalar null and curve-shape tests to name one object.

    The scalar control searches the visible catalogue independently of the
    train/holdout curve fit.  A low scalar p-value for one satellite cannot be
    used as specificity evidence for a different shape-selected satellite.
    """

    scalar_best = _scalar_best_candidate(scalar_match)
    if scalar_best is None or shape_best is None:
        return False
    scalar_catalog_number = scalar_best["catalog_number"]
    shape_catalog_number = shape_best.get("catalog_number")
    if isinstance(shape_catalog_number, bool) or not isinstance(shape_catalog_number, int):
        return False
    return scalar_catalog_number == shape_catalog_number


def _scalar_best_candidate(scalar_match: dict[str, Any]) -> dict[str, Any] | None:
    """Return a well-formed scalar winner or fail closed.

    Report evidence is an external input to the shape audit.  Missing identities must not
    compare equal through ``None == None`` or crash the secure-association projection.
    """

    candidates = scalar_match.get("top_candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0]
    if not isinstance(first, dict):
        return None
    catalog_number = first.get("catalog_number")
    object_name = first.get("object_name")
    if isinstance(catalog_number, bool) or not isinstance(catalog_number, int):
        return None
    if not isinstance(object_name, str) or not object_name:
        return None
    return first


def _scalar_gate_evidence(
    scalar_match: dict[str, Any], shape_best: dict[str, Any] | None
) -> dict[str, Any]:
    """Build the scalar projection consumed by the complete secure gate."""

    scalar_best = _scalar_best_candidate(scalar_match)
    try:
        empirical_p = float(scalar_match.get("true_time_empirical_p", 1.0))
    except (TypeError, ValueError):
        empirical_p = 1.0
    if not math.isfinite(empirical_p) or not 0.0 <= empirical_p <= 1.0:
        empirical_p = 1.0
    return {
        "control": {
            "best_object_name": None if scalar_best is None else scalar_best["object_name"],
            "best_catalog_number": (None if scalar_best is None else scalar_best["catalog_number"]),
            "best_error_hz_s": scalar_match.get("best_absolute_rate_error_hz_s"),
            "true_time_rank": scalar_match.get("true_time_rank_among_true_and_null"),
            "empirical_p": empirical_p,
        },
        "wrong_time_null": bool(scalar_best is not None and empirical_p <= SECURE_SCALAR_NULL_P),
        "identity_agree": _scalar_shape_identity_agree(scalar_match, shape_best),
    }


def _validate_source_cohort(source: dict[str, Any], session_ids: tuple[str, ...]) -> None:
    if source.get("analysis_kind") != "multi_dwell_degree1_only_report_rerun":
        raise ValueError("association source is not a fresh strict-linear rerun")
    source_ids = tuple(dwell["session_id"] for dwell in source.get("dwells", ()))
    if source_ids != session_ids:
        raise ValueError("association source cohort/order differs from requested sessions")
    if source.get("radio_polynomial_degrees") != [1]:
        raise ValueError("association source is not strictly degree one")


def _candidate_metadata(satellite: base.ConeSatellite) -> dict[str, Any]:
    return {
        "object_name": satellite.object_name,
        "catalog_number": satellite.catalog_number,
        "peak_elevation_deg": satellite.peak_elevation_deg,
        "element_epoch_utc_ns": satellite.element_epoch_utc_ns,
        "element_age_s": satellite.element_age_s,
    }


def _track_models(
    track: d1.SelectedLinearTrack,
    series: TrackSeries,
    satellites: tuple[base.ConeSatellite, ...],
    prediction_times_s: np.ndarray,
    observed,
    horizon_deg: float,
    scalar_match: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[int, dict[str, Any]]]]:
    train = _temporal_split(series.time_s)
    null = _linear_null(series, train)
    by_path_doppler = doppler_shift_hz(track.path.rf_frequency_hz, observed.range_rate_km_s)
    model_rows: dict[str, list[dict[str, Any]]] = {name: [] for name in MODEL_DRIFT_BOUNDS_HZ_S}
    model_rows["bounded_200_wide_epoch"] = []
    internal: dict[str, dict[int, dict[str, Any]]] = {name: {} for name in MODEL_DRIFT_BOUNDS_HZ_S}
    internal["bounded_200_wide_epoch"] = {}
    for index, satellite in enumerate(satellites):
        visibility = _visible_fraction(
            observed.elevation_deg[index],
            series,
            prediction_times_s,
            horizon_deg,
        )
        if visibility < MINIMUM_VISIBILITY_FRACTION:
            continue
        predicted = by_path_doppler[index]
        for model_name, drift_bound in MODEL_DRIFT_BOUNDS_HZ_S.items():
            evaluated = _evaluate_prediction(
                series,
                prediction_times_s,
                predicted,
                train=train,
                maximum_drift_hz_s=drift_bound,
            )
            row = {
                **_candidate_metadata(satellite),
                "visibility_fraction": visibility,
                **evaluated,
            }
            model_rows[model_name].append(row)
            internal[model_name][satellite.catalog_number] = row
        wide_evaluated = _evaluate_prediction(
            series,
            prediction_times_s,
            predicted,
            train=train,
            maximum_drift_hz_s=MODEL_DRIFT_BOUNDS_HZ_S["bounded_200"],
            epoch_bound_s=WIDE_EPOCH_BOUND_S,
        )
        wide_row = {
            **_candidate_metadata(satellite),
            "visibility_fraction": visibility,
            **wide_evaluated,
        }
        model_rows["bounded_200_wide_epoch"].append(wide_row)
        internal["bounded_200_wide_epoch"][satellite.catalog_number] = wide_row
    public_models = {}
    for model_name, rows in model_rows.items():
        ranked = _rank_evaluations(rows)
        if not ranked:
            public_models[model_name] = {
                "candidate_count": 0,
                "best": None,
                "runner_up_training_margin_hz": None,
                "top_candidates": [],
            }
            continue
        margin = (
            ranked[1]["train_residual_rms_hz"] - ranked[0]["train_residual_rms_hz"]
            if len(ranked) > 1
            else None
        )
        public_models[model_name] = {
            "candidate_count": len(ranked),
            "best": ranked[0],
            "runner_up_training_margin_hz": margin,
            "top_candidates": ranked[:5],
        }
    primary = public_models["bounded_200"]
    best = primary["best"]
    scalar_evidence = _scalar_gate_evidence(scalar_match, best)
    holdout_advantage = (
        None if best is None else null["holdout_residual_rms_hz"] - best["holdout_residual_rms_hz"]
    )
    model_best_ids = {
        name: values["best"]["catalog_number"]
        for name, values in public_models.items()
        if values["best"] is not None
    }
    rf_evidence = _rf_frequency_evidence(track)
    secure_checks = {
        "minimum_track_duration": track.duration_s >= MINIMUM_TRACK_DURATION_S,
        "minimum_observations": series.time_s.size >= MINIMUM_TRACK_OBSERVATIONS,
        "holdout_rms": bool(best and best["holdout_residual_rms_hz"] <= SECURE_HOLDOUT_RMS_HZ),
        "beats_linear_holdout": bool(
            holdout_advantage is not None and holdout_advantage >= SECURE_HOLDOUT_ADVANTAGE_HZ
        ),
        "runner_up_training_margin": bool(
            primary["runner_up_training_margin_hz"] is not None
            and primary["runner_up_training_margin_hz"] >= SECURE_RUNNER_UP_MARGIN_HZ
        ),
        "epoch_search_interior": bool(
            best and abs(best["epoch_adjustment_s"]) < PRIMARY_EPOCH_BOUND_S - EPOCH_STEP_S / 2.0
        ),
        "scalar_wrong_time_null": scalar_evidence["wrong_time_null"],
        "scalar_shape_identity_agree": scalar_evidence["identity_agree"],
        "identity_stable_across_nuisance_models": len(set(model_best_ids.values())) == 1,
        "rf_configuration_consistent": all(
            abs(value) <= RF_CONFIGURATION_TOLERANCE_HZ
            for value in (
                rf_evidence["tag_minus_reconstructed_hz"],
                rf_evidence["tag_minus_path_hz"],
            )
        ),
    }
    result = {
        "label": track.label,
        "path": track.path.label,
        "trajectory_id": track.trajectory.trajectory_id,
        "duration_s": track.duration_s,
        "observation_count": int(series.time_s.size),
        "radio_rate_hz_s": track.rate_hz_s,
        "radio_residual_rms_hz": track.trajectory.residual_rms_hz,
        "rf_frequency_hz": track.path.rf_frequency_hz,
        "timing_half_width_s": max(
            track.path.binding.timing.first_estimate_utc_ns
            - track.path.binding.timing.first_earliest_utc_ns,
            track.path.binding.timing.first_latest_utc_ns
            - track.path.binding.timing.first_estimate_utc_ns,
        )
        / base._NS_PER_S,
        "frequency_reference": track.path.binding.frequency_reference.model_dump(mode="json"),
        "linear_null": null,
        "scalar_rate_control": scalar_evidence["control"],
        "models": public_models,
        "primary_holdout_advantage_over_linear_hz": holdout_advantage,
        "secure_checks": secure_checks,
        "secure_association": all(secure_checks.values()),
    }
    return result, internal


def _aggregate_rms(rows: list[tuple[dict[str, Any], int]], key: str) -> float | None:
    if not rows:
        return None
    total = sum(float(row[key]) ** 2 * count for row, count in rows)
    count = sum(count for _, count in rows)
    return math.sqrt(total / count)


def _dwell_hypotheses(
    track_results: list[dict[str, Any]],
    internals: list[dict[str, dict[int, dict[str, Any]]]],
) -> dict[str, Any]:
    null_holdout = _aggregate_rms(
        [(track["linear_null"], track["observation_count"]) for track in track_results],
        "holdout_residual_rms_hz",
    )
    independent_rows = []
    independent_ids = []
    for track in track_results:
        best = track["models"]["bounded_200"]["best"]
        if best is not None:
            independent_rows.append((best, track["observation_count"]))
            independent_ids.append(best["catalog_number"])
    independent_holdout = _aggregate_rms(independent_rows, "holdout_residual_rms_hz")
    free_affine_rows = []
    free_affine_ids = []
    for track in track_results:
        best = track["models"]["free_affine"]["best"]
        if best is not None:
            free_affine_rows.append((best, track["observation_count"]))
            free_affine_ids.append(best["catalog_number"])
    free_affine_holdout = _aggregate_rms(
        free_affine_rows,
        "holdout_residual_rms_hz",
    )
    common = (
        set.intersection(*(set(item["bounded_200"]) for item in internals)) if internals else set()
    )
    shared_id = None
    shared_train = None
    shared_holdout = None
    if common:
        shared_id = min(
            common,
            key=lambda catalog_number: (
                sum(
                    internal["bounded_200"][catalog_number]["train_residual_rms_hz"] ** 2
                    * track["observation_count"]
                    for track, internal in zip(track_results, internals, strict=True)
                ),
                catalog_number,
            ),
        )
        shared_rows = [
            (internal["bounded_200"][shared_id], track["observation_count"])
            for track, internal in zip(track_results, internals, strict=True)
        ]
        shared_train = _aggregate_rms(shared_rows, "train_residual_rms_hz")
        shared_holdout = _aggregate_rms(shared_rows, "holdout_residual_rms_hz")
    top_ids = [
        [item["catalog_number"] for item in track["models"]["bounded_200"]["top_candidates"]]
        for track in track_results
    ]
    unique_assignment = None
    unique_holdout = None
    if top_ids and all(top_ids):
        choices = [items[:5] for items in top_ids]
        feasible = [
            values for values in itertools.product(*choices) if len(set(values)) == len(values)
        ]
        if feasible:
            unique_assignment = min(
                feasible,
                key=lambda values: (
                    sum(
                        internals[index]["bounded_200"][catalog_number]["train_residual_rms_hz"]
                        ** 2
                        * track_results[index]["observation_count"]
                        for index, catalog_number in enumerate(values)
                    ),
                    values,
                ),
            )
            unique_rows = [
                (
                    internals[index]["bounded_200"][catalog_number],
                    track_results[index]["observation_count"],
                )
                for index, catalog_number in enumerate(unique_assignment)
            ]
            unique_holdout = _aggregate_rms(unique_rows, "holdout_residual_rms_hz")
    return {
        "radio_only_linear_holdout_rms_hz": null_holdout,
        "independent_satellites": {
            "catalog_numbers": independent_ids,
            "holdout_rms_hz": independent_holdout,
        },
        "independent_satellites_free_affine": {
            "catalog_numbers": free_affine_ids,
            "holdout_rms_hz": free_affine_holdout,
        },
        "one_shared_satellite": {
            "catalog_number": shared_id,
            "train_rms_hz": shared_train,
            "holdout_rms_hz": shared_holdout,
        },
        "one_to_one_satellites": {
            "catalog_numbers": None if unique_assignment is None else list(unique_assignment),
            "holdout_rms_hz": unique_holdout,
        },
    }


def _shape_residual(values: np.ndarray, times_s: np.ndarray) -> np.ndarray:
    train = np.ones(times_s.size, dtype=bool)
    residual, *_ = _fit_affine_nuisance(times_s, values, train, 1_000_000.0)
    return residual


def _rf_frequency_evidence(track: d1.SelectedLinearTrack) -> dict[str, Any]:
    binding = track.path.binding
    tagged_rf_hz = starlink_edge_rf_center_frequency_hz(
        binding.starlink_channel,
        binding.starlink_edge,
    )
    reconstructed_rf_hz = binding.tuned_center_frequency_hz + STARLINK_LNB_LO_HZ
    return {
        "tagged_channel_edge_rf_hz": tagged_rf_hz,
        "if_plus_documented_lo_rf_hz": reconstructed_rf_hz,
        "path_rf_hz": track.path.rf_frequency_hz,
        "tag_minus_reconstructed_hz": tagged_rf_hz - reconstructed_rf_hz,
        "tag_minus_path_hz": tagged_rf_hz - track.path.rf_frequency_hz,
        "pilot_rf_half_width_hz": PILOT_RF_HALF_WIDTH_HZ,
    }


def _previous_snapshot(archive: TleArchiveReader, snapshot, provider: str):
    snapshots = archive.list_snapshots(provider)
    try:
        index = snapshots.index(snapshot)
    except ValueError as error:
        raise ValueError("selected TLE snapshot is absent from its archive") from error
    return None if index == 0 else snapshots[index - 1]


def _tle_snapshot_sensitivity(
    track: d1.SelectedLinearTrack,
    series: TrackSeries,
    best: dict[str, Any] | None,
    satellite_by_number: dict[int, tuple[int, base.ConeSatellite]],
    prediction_times_s: np.ndarray,
    current_observed,
    current_snapshot,
    previous_snapshot,
    previous_catalogue,
    previous_observed,
    previous_index_by_number: dict[int, int],
) -> dict[str, Any]:
    if best is None:
        return {"available": False, "reason": "no_visible_candidate"}
    catalog_number = int(best["catalog_number"])
    previous_index = previous_index_by_number.get(catalog_number)
    if previous_snapshot is None:
        return {"available": False, "reason": "no_earlier_causal_snapshot"}
    if previous_index is None or previous_catalogue is None or previous_observed is None:
        return {"available": False, "reason": "candidate_absent_from_previous_snapshot"}
    current_index, current_satellite = satellite_by_number[catalog_number]
    current_curve = doppler_shift_hz(
        track.path.rf_frequency_hz,
        current_observed.range_rate_km_s[current_index],
    )
    previous_curve = doppler_shift_hz(
        track.path.rf_frequency_hz,
        previous_observed.range_rate_km_s[previous_index],
    )
    difference = np.interp(
        series.time_s,
        prediction_times_s,
        previous_curve - current_curve,
    )
    previous_catalogue_index = previous_catalogue.satellite_numbers.index(catalog_number)
    previous_epoch_ns = previous_catalogue.element_epoch_utc_ns()[previous_catalogue_index]
    return {
        "available": True,
        "previous_collected_utc_ns": previous_snapshot.collected_utc_ns,
        "previous_digest": previous_snapshot.digest,
        "collection_separation_s": (
            current_snapshot.collected_utc_ns - previous_snapshot.collected_utc_ns
        )
        / base._NS_PER_S,
        "previous_element_epoch_utc_ns": previous_epoch_ns,
        "current_element_epoch_utc_ns": current_satellite.element_epoch_utc_ns,
        "element_epoch_separation_s": (current_satellite.element_epoch_utc_ns - previous_epoch_ns)
        / base._NS_PER_S,
        "raw_frequency_rms_hz": _rms(difference),
        "raw_frequency_max_absolute_hz": float(np.max(np.abs(difference))),
        "affine_removed_shape_rms_hz": _rms(_shape_residual(difference, series.time_s)),
    }


def _best_candidate_error_budget(
    track: d1.SelectedLinearTrack,
    series: TrackSeries,
    best: dict[str, Any] | None,
    satellite_by_number: dict[int, tuple[int, base.ConeSatellite]],
    prediction_times_s: np.ndarray,
    propagated,
    observed,
    observer: ObserverSiteV1,
) -> dict[str, Any] | None:
    if best is None:
        return None
    index, satellite = satellite_by_number[best["catalog_number"]]
    current = doppler_shift_hz(track.path.rf_frequency_hz, observed.range_rate_km_s[index])
    at_observations = np.interp(series.time_s, prediction_times_s, current)
    timing_half_width_s = (
        max(
            track.path.binding.timing.first_estimate_utc_ns
            - track.path.binding.timing.first_earliest_utc_ns,
            track.path.binding.timing.first_latest_utc_ns
            - track.path.binding.timing.first_estimate_utc_ns,
        )
        / base._NS_PER_S
    )
    early = np.interp(series.time_s - timing_half_width_s, prediction_times_s, current)
    late = np.interp(series.time_s + timing_half_width_s, prediction_times_s, current)
    timing_raw = np.maximum(np.abs(early - at_observations), np.abs(late - at_observations))
    timing_shape = max(
        _rms(_shape_residual(early - at_observations, series.time_s)),
        _rms(_shape_residual(late - at_observations, series.time_s)),
    )
    latitude_delta = SITE_UNCERTAINTY_M / 111_320.0
    longitude_delta = SITE_UNCERTAINTY_M / (
        111_320.0 * math.cos(math.radians(observer.latitude_deg))
    )
    shifted_sites = (
        observer.model_copy(update={"latitude_deg": observer.latitude_deg + latitude_delta}),
        observer.model_copy(update={"latitude_deg": observer.latitude_deg - latitude_delta}),
        observer.model_copy(update={"longitude_deg": observer.longitude_deg + longitude_delta}),
        observer.model_copy(update={"longitude_deg": observer.longitude_deg - longitude_delta}),
    )
    site_raw_rms = []
    site_shape_rms = []
    propagated_grid = SamplingGrid(
        propagated.utc_ns,
        len(propagated.utc_ns) // 2,
        (propagated.utc_ns[1] - propagated.utc_ns[0]) / base._NS_PER_S,
    )
    for site in shifted_sites:
        shifted_observed = observe_grid(propagated, site, propagated_grid)
        shifted_curve = doppler_shift_hz(
            track.path.rf_frequency_hz,
            shifted_observed.range_rate_km_s[index],
        )
        difference = np.interp(series.time_s, prediction_times_s, shifted_curve) - at_observations
        site_raw_rms.append(_rms(difference))
        site_shape_rms.append(_rms(_shape_residual(difference, series.time_s)))
    centered = series.time_s - float(np.mean(series.time_s))
    predicted_rate_hz_s = float(np.polyfit(centered, at_observations, 1)[0])
    rf_evidence = _rf_frequency_evidence(track)
    return {
        "element_age_s": satellite.element_age_s,
        "capture_timing_half_width_s": timing_half_width_s,
        "timing_max_raw_frequency_effect_hz": float(np.max(timing_raw)),
        "timing_affine_removed_shape_rms_hz": timing_shape,
        "site_position_uncertainty_m": SITE_UNCERTAINTY_M,
        "site_max_raw_frequency_rms_hz": max(site_raw_rms),
        "site_max_affine_removed_shape_rms_hz": max(site_shape_rms),
        "rf_frequency_evidence": rf_evidence,
        "rf_scale_rate_effect_hz_s": abs(predicted_rate_hz_s)
        * PILOT_RF_HALF_WIDTH_HZ
        / track.path.rf_frequency_hz,
        "frequency_reference_calibrated": (
            track.path.binding.frequency_reference.reference.value == "calibrated"
        ),
    }


def _analyze_dwell(
    run: base.CohortRun,
    paths: tuple[d1.PathEvidence, ...],
    archive: TleArchiveReader,
    observer: ObserverSiteV1,
    scalar: dict[tuple[str, str], dict[str, Any]],
    *,
    provider: str,
    horizon_deg: float,
    maximum_selected: int,
) -> dict[str, Any]:
    dwell_start_ns, duration_s = base._nominal_capture(paths)
    tracks, raw_by_path, _, config_digest = d1._selected_tracks(
        paths,
        dwell_start_ns,
        maximum_selected=maximum_selected,
    )
    preselected = tracks[:3]
    eligible = tuple(
        track
        for track in preselected
        if track.duration_s >= MINIMUM_TRACK_DURATION_S
        and track.trajectory.point_count >= MINIMUM_TRACK_OBSERVATIONS
    )
    snapshot = base._select_causal_space_track_snapshot(
        archive,
        anchor_utc_ns=dwell_start_ns,
        provider=provider,
    )
    catalogue = parse_element_sets(archive.read(snapshot))
    satellites, _, _ = _candidate_catalogue(
        catalogue,
        observer,
        dwell_start_ns,
        duration_s,
        horizon_deg,
    )
    prediction_grid, prediction_times_s, propagated, observed = _prediction_bank(
        catalogue,
        satellites,
        observer,
        dwell_start_ns,
        duration_s,
    )
    satellite_by_number = {
        item.catalog_number: (index, item) for index, item in enumerate(satellites)
    }
    modeled = []
    for track in eligible:
        series = _track_series(track, dwell_start_ns)
        result, internal = _track_models(
            track,
            series,
            satellites,
            prediction_times_s,
            observed,
            horizon_deg,
            scalar[(run.session_id, track.trajectory.trajectory_id)],
        )
        modeled.append((track, series, result, internal))

    previous_snapshot = _previous_snapshot(archive, snapshot, provider)
    previous_catalogue = None
    previous_observed = None
    previous_index_by_number: dict[int, int] = {}
    if previous_snapshot is not None:
        previous_catalogue = parse_element_sets(archive.read(previous_snapshot))
        wanted = {
            int(result["models"]["bounded_200"]["best"]["catalog_number"])
            for _, _, result, _ in modeled
            if result["models"]["bounded_200"]["best"] is not None
        }
        catalogue_index_by_number = {
            catalog_number: index
            for index, catalog_number in enumerate(previous_catalogue.satellite_numbers)
        }
        present = sorted(wanted.intersection(catalogue_index_by_number))
        previous_indices = [catalogue_index_by_number[item] for item in present]
        if previous_indices:
            previous_propagated = propagate_grid(
                previous_catalogue,
                prediction_grid,
                indices=previous_indices,
            )
            previous_observed = observe_grid(
                previous_propagated,
                observer,
                prediction_grid,
            )
            previous_index_by_number = {
                catalog_number: index for index, catalog_number in enumerate(present)
            }

    track_results = []
    internals = []
    for track, series, result, internal in modeled:
        error_budget = _best_candidate_error_budget(
            track,
            series,
            result["models"]["bounded_200"]["best"],
            satellite_by_number,
            prediction_times_s,
            propagated,
            observed,
            observer,
        )
        tle_sensitivity = _tle_snapshot_sensitivity(
            track,
            series,
            result["models"]["bounded_200"]["best"],
            satellite_by_number,
            prediction_times_s,
            observed,
            snapshot,
            previous_snapshot,
            previous_catalogue,
            previous_observed,
            previous_index_by_number,
        )
        if error_budget is None:
            error_budget = {}
        error_budget["adjacent_causal_tle_sensitivity"] = tle_sensitivity
        result["error_budget"] = error_budget
        result["secure_checks"]["adjacent_tle_shape_stable"] = bool(
            tle_sensitivity["available"]
            and tle_sensitivity["affine_removed_shape_rms_hz"] <= SECURE_TLE_SHAPE_SENSITIVITY_HZ
        )
        result["secure_association"] = all(result["secure_checks"].values())
        track_results.append(result)
        internals.append(internal)
    return {
        "session_id": run.session_id,
        "analysis_run_id": run.run_id,
        "source_pipeline_release_id": run.pipeline_release_id,
        "capture_start_utc_ns": dwell_start_ns,
        "duration_s": duration_s,
        "fresh_linear_config_digest": config_digest,
        "fresh_raw_track_count": sum(len(items) for items in raw_by_path.values()),
        "preselected_track_count": len(preselected),
        "eligible_track_count": len(eligible),
        "causal_tle_snapshot": {
            "provider": snapshot.provider,
            "collected_utc_ns": snapshot.collected_utc_ns,
            "digest": snapshot.digest,
            "candidate_satellite_count": len(satellites),
            "previous_digest": (None if previous_snapshot is None else previous_snapshot.digest),
        },
        "tracks": track_results,
        "hypotheses": _dwell_hypotheses(track_results, internals),
    }


def _plot_holdout(path: Path, dwells: list[dict[str, Any]]) -> None:
    tracks = [track for dwell in dwells for track in dwell["tracks"]]
    null = np.asarray([item["linear_null"]["holdout_residual_rms_hz"] for item in tracks])
    orbital = np.asarray(
        [item["models"]["bounded_200"]["best"]["holdout_residual_rms_hz"] for item in tracks]
    )
    figure, axis = plt.subplots(figsize=(9, 8))
    limit = max(float(null.max()), float(orbital.max())) * 1.05
    axis.plot([0, limit], [0, limit], color="#687381", linestyle="--", linewidth=1)
    colors = ["#2a9d8f" if item["secure_association"] else "#d1495b" for item in tracks]
    axis.scatter(null, orbital, c=colors, s=42, alpha=0.85)
    axis.set_xlabel("radio-only linear holdout RMS (Hz)")
    axis.set_ylabel("best bounded-orbit holdout RMS (Hz)")
    axis.set_title("Held-out orbital discrimination · identity chosen on training data", loc="left")
    axis.grid(alpha=0.18)
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_hypotheses(path: Path, dwells: list[dict[str, Any]]) -> None:
    labels = [item["session_id"].split("T", 1)[-1][:6] for item in dwells]
    names = (
        ("radio_only_linear_holdout_rms_hz", "radio linear", "#687381"),
        ("independent_satellites", "independent satellites", "#277da1"),
        (
            "independent_satellites_free_affine",
            "orbit + free affine",
            "#43aa8b",
        ),
        ("one_shared_satellite", "one shared satellite", "#f8961e"),
        ("one_to_one_satellites", "one-to-one satellites", "#7a5195"),
    )
    x = np.arange(len(dwells), dtype=float)
    width = 0.16
    figure, axis = plt.subplots(figsize=(17, 7))
    for offset_index, (key, label, color) in enumerate(names):
        values = []
        for dwell in dwells:
            value = dwell["hypotheses"][key]
            if isinstance(value, dict):
                value = value["holdout_rms_hz"]
            values.append(np.nan if value is None else value)
        axis.bar(x + (offset_index - 2.0) * width, values, width, label=label, color=color)
    axis.set_xticks(x, labels, rotation=45, ha="right")
    axis.set_ylabel("aggregate holdout RMS (Hz)")
    axis.set_title("Per-dwell competing identity hypotheses", loc="left")
    axis.grid(axis="y", alpha=0.18)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_null_and_advantage(path: Path, dwells: list[dict[str, Any]]) -> None:
    tracks = [track for dwell in dwells for track in dwell["tracks"]]
    p = [item["scalar_rate_control"]["empirical_p"] for item in tracks]
    advantage = [item["primary_holdout_advantage_over_linear_hz"] for item in tracks]
    figure, axis = plt.subplots(figsize=(10, 7))
    axis.axvline(SECURE_SCALAR_NULL_P, color="#687381", linestyle="--")
    axis.axhline(SECURE_HOLDOUT_ADVANTAGE_HZ, color="#687381", linestyle="--")
    axis.scatter(p, advantage, color="#277da1", s=42, alpha=0.85)
    axis.set_xlabel("scalar-rate true-time empirical p")
    axis.set_ylabel("bounded orbit advantage over linear holdout (Hz)")
    axis.set_title("Independent time-specificity and curve-shape checks", loc="left")
    axis.grid(alpha=0.18)
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _write_track_csv(path: Path, dwells: list[dict[str, Any]]) -> None:
    fields = (
        "session_id",
        "track",
        "path",
        "duration_s",
        "observation_count",
        "radio_rate_hz_s",
        "best_object_name",
        "best_catalog_number",
        "best_train_rms_hz",
        "best_holdout_rms_hz",
        "linear_holdout_rms_hz",
        "holdout_advantage_hz",
        "scalar_empirical_p",
        "free_affine_best_catalog_number",
        "free_affine_holdout_rms_hz",
        "wide_epoch_best_catalog_number",
        "wide_epoch_adjustment_s",
        "wide_epoch_holdout_rms_hz",
        "adjacent_tle_shape_rms_hz",
        "failed_secure_checks",
        "secure_association",
    )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for dwell in dwells:
            for track in dwell["tracks"]:
                best = track["models"]["bounded_200"]["best"]
                free_affine = track["models"]["free_affine"]["best"]
                wide_epoch = track["models"]["bounded_200_wide_epoch"]["best"]
                tle_sensitivity = track["error_budget"]["adjacent_causal_tle_sensitivity"]
                writer.writerow(
                    {
                        "session_id": dwell["session_id"],
                        "track": track["label"],
                        "path": track["path"],
                        "duration_s": track["duration_s"],
                        "observation_count": track["observation_count"],
                        "radio_rate_hz_s": track["radio_rate_hz_s"],
                        "best_object_name": best["object_name"],
                        "best_catalog_number": best["catalog_number"],
                        "best_train_rms_hz": best["train_residual_rms_hz"],
                        "best_holdout_rms_hz": best["holdout_residual_rms_hz"],
                        "linear_holdout_rms_hz": track["linear_null"]["holdout_residual_rms_hz"],
                        "holdout_advantage_hz": track["primary_holdout_advantage_over_linear_hz"],
                        "scalar_empirical_p": track["scalar_rate_control"]["empirical_p"],
                        "free_affine_best_catalog_number": free_affine["catalog_number"],
                        "free_affine_holdout_rms_hz": free_affine["holdout_residual_rms_hz"],
                        "wide_epoch_best_catalog_number": wide_epoch["catalog_number"],
                        "wide_epoch_adjustment_s": wide_epoch["epoch_adjustment_s"],
                        "wide_epoch_holdout_rms_hz": wide_epoch["holdout_residual_rms_hz"],
                        "adjacent_tle_shape_rms_hz": (
                            tle_sensitivity["affine_removed_shape_rms_hz"]
                            if tle_sensitivity["available"]
                            else None
                        ),
                        "failed_secure_checks": ";".join(
                            key for key, passed in track["secure_checks"].items() if not passed
                        ),
                        "secure_association": track["secure_association"],
                    }
                )


def main() -> None:
    args = _arguments()
    session_ids = tuple(args.session_ids) or DEFAULT_SESSION_IDS
    if len(session_ids) < 10:
        raise ValueError("multi-dwell association requires at least ten unique dwells")
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("session IDs must be unique")
    source = json.loads(args.source_evidence.read_text())
    _validate_source_cohort(source, session_ids)
    scalar = _scalar_lookup(source)
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    engine = create_catalog_engine(args.database_url)
    resolver = BulkUriResolver(args.bulk_root, allowed_namespaces=("analysis",), create=False)
    archive = TleArchiveReader(args.tle_root)
    observer = ObserverSiteV1(
        latitude_deg=base.DEFAULT_LATITUDE_DEG,
        longitude_deg=base.DEFAULT_LONGITUDE_DEG,
        altitude_m=base.DEFAULT_ALTITUDE_M,
        label="reviewed-spinnaker-sausalito-not-capture-bound",
    )
    with Session(engine) as database:
        cohort = base._cohort(database, session_ids)
        dwells = [
            _analyze_dwell(
                run,
                d1._path_evidence(database, resolver, run),
                archive,
                observer,
                scalar,
                provider=args.provider,
                horizon_deg=args.horizon_deg,
                maximum_selected=args.maximum_selected_per_path,
            )
            for run in cohort
        ]
    tracks = [track for dwell in dwells for track in dwell["tracks"]]
    linear_holdout = [track["linear_null"]["holdout_residual_rms_hz"] for track in tracks]
    primary_holdout = [
        track["models"]["bounded_200"]["best"]["holdout_residual_rms_hz"] for track in tracks
    ]
    free_affine_holdout = [
        track["models"]["free_affine"]["best"]["holdout_residual_rms_hz"] for track in tracks
    ]
    evidence = {
        "schema_version": 1,
        "analysis_kind": "multi_dwell_starlink_train_holdout_association",
        "analysis_main_commit": _git_revision(),
        "origin_main_commit": _git_revision("origin/main"),
        "analysis_tool_sha256": _sha256(Path(__file__)),
        "degree1_tool_sha256": _sha256(Path(d1.__file__)),
        "source_evidence_sha256": _sha256(args.source_evidence),
        "source_fresh_rerun_generated_utc": source["generated_utc"],
        "session_count": len(dwells),
        "eligible_track_count": len(tracks),
        "secure_association_count": sum(item["secure_association"] for item in tracks),
        "summary": {
            "median_linear_holdout_rms_hz": float(np.median(linear_holdout)),
            "median_primary_orbit_holdout_rms_hz": float(np.median(primary_holdout)),
            "median_free_affine_orbit_holdout_rms_hz": float(np.median(free_affine_holdout)),
            "primary_orbit_track_win_count": sum(
                orbital < linear
                for linear, orbital in zip(
                    linear_holdout,
                    primary_holdout,
                    strict=True,
                )
            ),
            "primary_orbit_advantage_100hz_count": sum(
                linear - orbital >= SECURE_HOLDOUT_ADVANTAGE_HZ
                for linear, orbital in zip(
                    linear_holdout,
                    primary_holdout,
                    strict=True,
                )
            ),
            "free_affine_orbit_track_win_count": sum(
                orbital < linear
                for linear, orbital in zip(
                    linear_holdout,
                    free_affine_holdout,
                    strict=True,
                )
            ),
            "scalar_wrong_time_pass_count": sum(
                track["scalar_rate_control"]["empirical_p"] <= SECURE_SCALAR_NULL_P
                for track in tracks
            ),
            "primary_orbit_dwell_win_count": sum(
                dwell["hypotheses"]["independent_satellites"]["holdout_rms_hz"]
                < dwell["hypotheses"]["radio_only_linear_holdout_rms_hz"]
                for dwell in dwells
            ),
            "free_affine_orbit_dwell_win_count": sum(
                dwell["hypotheses"]["independent_satellites_free_affine"]["holdout_rms_hz"]
                < dwell["hypotheses"]["radio_only_linear_holdout_rms_hz"]
                for dwell in dwells
            ),
        },
        "observer": observer.model_dump(mode="json"),
        "method": {
            "track_preselection": "three longest fresh degree-1 tracks before TLE matching",
            "minimum_track_duration_s": MINIMUM_TRACK_DURATION_S,
            "minimum_track_observations": MINIMUM_TRACK_OBSERVATIONS,
            "train_fraction": TRAIN_FRACTION,
            "identity_selection_uses_holdout": False,
            "radio_track_membership_uses_full_span": True,
            "holdout_scope": (
                "catalog identity, epoch, and nuisance selection only; radio track membership "
                "was fitted before the split using the full selected trajectory"
            ),
            "primary_epoch_bound_s": PRIMARY_EPOCH_BOUND_S,
            "diagnostic_wide_epoch_bound_s": WIDE_EPOCH_BOUND_S,
            "nuisance_models_hz_s": MODEL_DRIFT_BOUNDS_HZ_S,
            "horizon_deg": args.horizon_deg,
            "minimum_visibility_fraction": MINIMUM_VISIBILITY_FRACTION,
            "secure_thresholds": {
                "holdout_rms_hz": SECURE_HOLDOUT_RMS_HZ,
                "holdout_advantage_hz": SECURE_HOLDOUT_ADVANTAGE_HZ,
                "runner_up_training_margin_hz": SECURE_RUNNER_UP_MARGIN_HZ,
                "scalar_wrong_time_empirical_p": SECURE_SCALAR_NULL_P,
                "adjacent_tle_shape_sensitivity_hz": SECURE_TLE_SHAPE_SENSITIVITY_HZ,
                "rf_configuration_tolerance_hz": RF_CONFIGURATION_TOLERANCE_HZ,
            },
        },
        "dwells": dwells,
    }
    evidence_path = output_root / "multi-dwell-starlink-association.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    _write_track_csv(output_root / "multi-dwell-track-summary.csv", dwells)
    _plot_holdout(output_root / "heldout-orbital-discrimination.png", dwells)
    _plot_hypotheses(output_root / "dwell-hypothesis-comparison.png", dwells)
    _plot_null_and_advantage(output_root / "time-null-versus-curve-advantage.png", dwells)
    print(
        json.dumps(
            {
                "session_count": len(dwells),
                "eligible_track_count": len(tracks),
                "secure_association_count": evidence["secure_association_count"],
                "evidence_path": str(evidence_path),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
