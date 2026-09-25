#!/usr/bin/env python3
"""Match recent reset-debiased ramp rates to causal Starlink TLE predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.ramp_tle_association import (
    CandidateRateSeries,
    RampRateAssociationConfig,
    RampRateSeries,
    associate_ramp_rates,
)
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader, TleSnapshotRef
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    PropagatedWindow,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import ObservedTracks, observe_grid

DEFAULT_INPUTS = Path("reports/figures/2026_08_24_recent_50_doppler/inputs.json")
DEFAULT_RESULTS = Path("reports/figures/2026_08_24_recent_50_doppler/results")
DEFAULT_TLE_ROOT = Path("/var/lib/leo/tle")
DEFAULT_TLE_AUTHORITY_ROOT = Path("/var/lib/leo/tle")
DEFAULT_OUTPUT = Path("reports/figures/2026_08_24_recent_50_doppler/ramp-tle-associations.json")
PROVIDER = "space-track"
PRIMARY_ELEVATION_DEG = 60.0
CONTROL_ELEVATION_DEG = 10.0
TLE_COMPLETENESS_FRACTION = 0.90
RATE_GRID_STEP_S = 0.125
RATE_NUISANCE_MODELS_HZ_S = (25.0, 200.0, 1_000_000.0)
SITE_UNCERTAINTY_M = 50.0
SITE_PROVENANCE_STRESS_RADIUS_M = 10_000.0
PILOT_RF_HALF_WIDTH_HZ = 937_500.0
NS_PER_S = 1_000_000_000

OBSERVER = ObserverSiteV1(
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    altitude_m=-29.0,
    label="reviewed-spinnaker-sausalito-not-capture-bound",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--tle-root", type=Path, default=DEFAULT_TLE_ROOT)
    parser.add_argument(
        "--tle-authority-root",
        type=Path,
        default=DEFAULT_TLE_AUTHORITY_ROOT,
        help="provenance path from which a read-only analysis mirror was staged",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--only-label")
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _result_path(root: Path, row: dict[str, Any]) -> Path:
    suffix = str(row["session_id"]).rsplit("-", 1)[-1]
    return root / f"{row['label']}-{suffix}.json"


def complete_catalogues(
    archive: TleArchiveReader,
) -> tuple[
    tuple[TleSnapshotRef, ...],
    dict[str, ElementSetCatalogue],
    tuple[dict[str, object], ...],
]:
    """Parse snapshots and reject conspicuously incomplete catalogues."""

    parsed: dict[str, ElementSetCatalogue] = {}
    inventory = []
    snapshots = archive.list_snapshots(PROVIDER)
    for snapshot in snapshots:
        catalogue = parse_element_sets(archive.read(snapshot))
        starlink_count = sum(name.upper().startswith("STARLINK") for name in catalogue.names)
        parsed[snapshot.digest] = catalogue
        inventory.append(
            {
                "collected_utc_ns": snapshot.collected_utc_ns,
                "digest": snapshot.digest,
                "byte_size": snapshot.byte_size,
                "object_count": len(catalogue),
                "starlink_object_count": starlink_count,
            }
        )
    if not inventory:
        raise ValueError("no TLE snapshots are available")
    maximum = max(int(item["starlink_object_count"]) for item in inventory)
    minimum = math.ceil(TLE_COMPLETENESS_FRACTION * maximum)
    complete = tuple(
        snapshot
        for snapshot, item in zip(snapshots, inventory, strict=True)
        if int(item["starlink_object_count"]) >= minimum
    )
    if not complete:
        raise ValueError("no TLE snapshot passes the catalogue completeness gate")
    public = tuple(
        {
            **item,
            "completeness_gate_count": minimum,
            "accepted_as_complete": int(item["starlink_object_count"]) >= minimum,
        }
        for item in inventory
    )
    return complete, parsed, public


def causal_snapshot_triplet(
    snapshots: tuple[TleSnapshotRef, ...], anchor_utc_ns: int
) -> tuple[TleSnapshotRef | None, TleSnapshotRef, TleSnapshotRef | None]:
    """Return previous, latest-at-or-before-capture, and next valid snapshots."""

    causal = tuple(item for item in snapshots if item.collected_utc_ns <= anchor_utc_ns)
    if not causal:
        raise ValueError("no complete TLE snapshot predates the capture")
    primary = causal[-1]
    index = snapshots.index(primary)
    previous = snapshots[index - 1] if index > 0 else None
    following = snapshots[index + 1] if index + 1 < len(snapshots) else None
    return previous, primary, following


def _stream(row: dict[str, Any], stream_id: str) -> dict[str, Any]:
    matches = tuple(item for item in row["streams"] if item["stream_id"] == stream_id)
    if len(matches) != 1:
        raise ValueError(f"selected stream is absent or duplicated: {stream_id}")
    return matches[0]


def _radio_series(result: dict[str, Any]) -> tuple[RampRateSeries, dict[str, Any]]:
    selected = result.get("selected")
    if result.get("status") != "complete" or not isinstance(selected, dict):
        raise ValueError("raw-Doppler result is not complete")
    analysis = selected["result"]
    ramps = tuple(
        sorted(
            (
                item
                for item in analysis["ramps"]
                if item.get("slope_sigma_hz_s") is not None
                and float(item["slope_sigma_hz_s"]) > 0.0
            ),
            key=lambda item: float(item["center_time_s"]),
        )
    )
    series = RampRateSeries(
        time_s=tuple(float(item["center_time_s"]) for item in ramps),
        rate_hz_s=tuple(float(item["slope_hz_s"]) for item in ramps),
        sigma_hz_s=tuple(float(item["slope_sigma_hz_s"]) for item in ramps),
    )
    return series, selected


def _rate_grid(first_sample_utc_ns: int, series: RampRateSeries) -> tuple[SamplingGrid, np.ndarray]:
    start_s = min(series.time_s) - 1.0
    end_s = max(series.time_s) + 1.0
    step_ns = round(RATE_GRID_STEP_S * NS_PER_S)
    start_ns = first_sample_utc_ns + math.floor(start_s / RATE_GRID_STEP_S) * step_ns
    end_ns = first_sample_utc_ns + math.ceil(end_s / RATE_GRID_STEP_S) * step_ns
    count = (end_ns - start_ns) // step_ns + 1
    utc_ns = tuple(start_ns + index * step_ns for index in range(count))
    grid = SamplingGrid(utc_ns=utc_ns, anchor_index=count // 2, spacing_s=RATE_GRID_STEP_S)
    relative_s = (np.asarray(utc_ns, dtype=np.float64) - first_sample_utc_ns) / NS_PER_S
    return grid, relative_s


def _doppler_rate_bank(
    observed: ObservedTracks,
    grid_time_s: np.ndarray,
    rf_frequency_hz: float,
) -> np.ndarray:
    shift = doppler_shift_hz(rf_frequency_hz, observed.range_rate_km_s)
    return np.gradient(shift, grid_time_s, axis=1, edge_order=2)


def _candidate_series(
    catalogue: ElementSetCatalogue,
    observed: ObservedTracks,
    grid_time_s: np.ndarray,
    rate_bank: np.ndarray,
    series: RampRateSeries,
    *,
    elevation_threshold_deg: float,
    anchor_utc_ns: int,
) -> tuple[tuple[CandidateRateSeries, ...], tuple[int, ...]]:
    ramp_times = np.asarray(series.time_s, dtype=float)
    epochs = catalogue.element_epoch_utc_ns()
    candidates = []
    indices = []
    for index, (name, catalog_number) in enumerate(
        zip(catalogue.names, catalogue.satellite_numbers, strict=True)
    ):
        if not name.upper().startswith("STARLINK") or not observed.usable[index]:
            continue
        elevation = np.interp(ramp_times, grid_time_s, observed.elevation_deg[index])
        altitude = np.interp(ramp_times, grid_time_s, observed.altitude_km[index])
        if (
            float(np.min(elevation)) < elevation_threshold_deg
            or float(np.min(altitude)) < MINIMUM_PLAUSIBLE_ALTITUDE_KM
        ):
            continue
        epoch = epochs[index]
        candidates.append(
            CandidateRateSeries(
                object_name=name,
                catalog_number=catalog_number,
                predicted_rate_hz_s=tuple(
                    float(value) for value in np.interp(ramp_times, grid_time_s, rate_bank[index])
                ),
                peak_elevation_deg=float(np.max(elevation)),
                minimum_elevation_deg=float(np.min(elevation)),
                element_epoch_utc_ns=epoch,
                element_age_s=abs(anchor_utc_ns - epoch) / NS_PER_S,
            )
        )
        indices.append(index)
    return tuple(candidates), tuple(indices)


def _association_models(
    series: RampRateSeries,
    candidates: tuple[CandidateRateSeries, ...],
) -> dict[str, object]:
    output = {}
    for bound in RATE_NUISANCE_MODELS_HZ_S:
        key = "free" if bound > 100_000.0 else f"bounded_{bound:g}"
        output[key] = asdict(
            associate_ramp_rates(
                series,
                candidates,
                RampRateAssociationConfig(nuisance_rate_bound_hz_s=bound),
                limit=10,
            )
        )
    return output


def _top_summary(model: dict[str, Any]) -> dict[str, object]:
    ranked = model["ranked"]
    if not ranked:
        return {"candidate_count": 0, "best": None}
    best = ranked[0]
    return {
        "candidate_count": model["candidate_count"],
        "best": {
            "catalog_number": best["candidate"]["catalog_number"],
            "object_name": best["candidate"]["object_name"],
            "train_standardized_rms": best["metrics"]["train_standardized_rms"],
            "holdout_standardized_rms": best["metrics"]["holdout_standardized_rms"],
            "fitted_rate_nuisance_hz_s": best["metrics"]["fitted_rate_nuisance_hz_s"],
        },
        "runner_up_train_standardized_margin": model["runner_up_train_standardized_margin"],
    }


def _single_model(
    series: RampRateSeries,
    candidates: tuple[CandidateRateSeries, ...],
) -> dict[str, Any]:
    if not candidates:
        return {"candidate_count": 0, "best": None}
    model = asdict(
        associate_ramp_rates(
            series,
            candidates,
            RampRateAssociationConfig(nuisance_rate_bound_hz_s=200.0),
            limit=10,
        )
    )
    return _top_summary(model)


def _alternate_snapshot_association(
    snapshot: TleSnapshotRef | None,
    catalogues: dict[str, ElementSetCatalogue],
    grid: SamplingGrid,
    grid_time_s: np.ndarray,
    series: RampRateSeries,
    first_sample_utc_ns: int,
    rf_frequency_hz: float,
) -> dict[str, object]:
    if snapshot is None:
        return {"available": False, "reason": "no_adjacent_complete_snapshot"}
    catalogue = catalogues[snapshot.digest]
    propagated = propagate_grid(catalogue, grid)
    observed = observe_grid(propagated, OBSERVER, grid)
    rate_bank = _doppler_rate_bank(observed, grid_time_s, rf_frequency_hz)
    candidates, _indices = _candidate_series(
        catalogue,
        observed,
        grid_time_s,
        rate_bank,
        series,
        elevation_threshold_deg=PRIMARY_ELEVATION_DEG,
        anchor_utc_ns=first_sample_utc_ns + round(float(np.mean(series.time_s)) * NS_PER_S),
    )
    return {
        "available": True,
        "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        "snapshot_digest": snapshot.digest,
        **_single_model(series, candidates),
    }


def _shifted_sites(radius_m: float) -> tuple[tuple[str, ObserverSiteV1], ...]:
    latitude_delta = radius_m / 111_320.0
    longitude_delta = radius_m / (111_320.0 * math.cos(math.radians(OBSERVER.latitude_deg)))
    return (
        (
            "north",
            OBSERVER.model_copy(update={"latitude_deg": OBSERVER.latitude_deg + latitude_delta}),
        ),
        (
            "south",
            OBSERVER.model_copy(update={"latitude_deg": OBSERVER.latitude_deg - latitude_delta}),
        ),
        (
            "east",
            OBSERVER.model_copy(update={"longitude_deg": OBSERVER.longitude_deg + longitude_delta}),
        ),
        (
            "west",
            OBSERVER.model_copy(update={"longitude_deg": OBSERVER.longitude_deg - longitude_delta}),
        ),
    )


def _site_identity_stress(
    *,
    catalogue: ElementSetCatalogue,
    propagated: PropagatedWindow,
    grid_time_s: np.ndarray,
    grid: SamplingGrid,
    series: RampRateSeries,
    first_sample_utc_ns: int,
    rf_frequency_hz: float,
) -> dict[str, object]:
    directions = []
    for direction, site in _shifted_sites(SITE_PROVENANCE_STRESS_RADIUS_M):
        observed = observe_grid(propagated, site, grid)
        rate_bank = _doppler_rate_bank(observed, grid_time_s, rf_frequency_hz)
        candidates, _indices = _candidate_series(
            catalogue,
            observed,
            grid_time_s,
            rate_bank,
            series,
            elevation_threshold_deg=PRIMARY_ELEVATION_DEG,
            anchor_utc_ns=first_sample_utc_ns + round(float(np.mean(series.time_s)) * NS_PER_S),
        )
        directions.append({"direction": direction, **_single_model(series, candidates)})
    return {
        "radius_m": SITE_PROVENANCE_STRESS_RADIUS_M,
        "reason": "reviewed observer preset is not capture-bound GPS authority",
        "directions": directions,
    }


def _one_object_rate(
    catalogue: ElementSetCatalogue,
    catalog_number: int,
    grid: SamplingGrid,
    grid_time_s: np.ndarray,
    observer: ObserverSiteV1,
    rf_frequency_hz: float,
) -> tuple[np.ndarray, PropagatedWindow, ObservedTracks, int]:
    try:
        index = catalogue.satellite_numbers.index(catalog_number)
    except ValueError as error:
        raise ValueError("candidate is absent from sensitivity catalogue") from error
    propagated = propagate_grid(catalogue, grid, indices=[index])
    observed = observe_grid(propagated, observer, grid)
    rate = _doppler_rate_bank(observed, grid_time_s, rf_frequency_hz)[0]
    return rate, propagated, observed, index


def _centered_rms(values: np.ndarray) -> float:
    centered = values - float(np.mean(values))
    return float(np.sqrt(np.mean(centered**2)))


def _snapshot_sensitivity(
    snapshot: TleSnapshotRef | None,
    catalogues: dict[str, ElementSetCatalogue],
    catalog_number: int,
    grid: SamplingGrid,
    grid_time_s: np.ndarray,
    ramp_times_s: np.ndarray,
    observer: ObserverSiteV1,
    rf_frequency_hz: float,
    primary_rate: np.ndarray,
) -> dict[str, object]:
    if snapshot is None:
        return {"available": False, "reason": "no_adjacent_complete_snapshot"}
    catalogue = catalogues[snapshot.digest]
    if catalog_number not in catalogue.satellite_numbers:
        return {
            "available": False,
            "reason": "candidate_absent_from_adjacent_snapshot",
            "snapshot_digest": snapshot.digest,
            "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        }
    rate, _propagated, _observed, index = _one_object_rate(
        catalogue,
        catalog_number,
        grid,
        grid_time_s,
        observer,
        rf_frequency_hz,
    )
    difference = np.interp(ramp_times_s, grid_time_s, rate - primary_rate)
    epoch = catalogue.element_epoch_utc_ns()[index]
    return {
        "available": True,
        "snapshot_digest": snapshot.digest,
        "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        "element_epoch_utc_ns": epoch,
        "raw_rate_rms_hz_s": float(np.sqrt(np.mean(difference**2))),
        "raw_rate_max_absolute_hz_s": float(np.max(np.abs(difference))),
        "constant_rate_nuisance_removed_rms_hz_s": _centered_rms(difference),
    }


def _best_error_budget(
    *,
    best: dict[str, Any],
    catalogue: ElementSetCatalogue,
    previous: TleSnapshotRef | None,
    following: TleSnapshotRef | None,
    catalogues: dict[str, ElementSetCatalogue],
    grid: SamplingGrid,
    grid_time_s: np.ndarray,
    propagated: PropagatedWindow,
    rate_bank: np.ndarray,
    candidate_indices: tuple[int, ...],
    series: RampRateSeries,
    stream: dict[str, Any],
) -> dict[str, object]:
    catalog_number = int(best["candidate"]["catalog_number"])
    catalogue_index = catalogue.satellite_numbers.index(catalog_number)
    bank_position = candidate_indices.index(catalogue_index)
    primary_rate = rate_bank[catalogue_index]
    ramp_times = np.asarray(series.time_s, dtype=float)
    nominal = np.interp(ramp_times, grid_time_s, primary_rate)
    timing_half_width_s = (
        max(
            int(stream["first_sample_estimate_utc_ns"])
            - int(stream["first_sample_earliest_utc_ns"]),
            int(stream["first_sample_latest_utc_ns"]) - int(stream["first_sample_estimate_utc_ns"]),
        )
        / NS_PER_S
    )
    early = np.interp(ramp_times - timing_half_width_s, grid_time_s, primary_rate)
    late = np.interp(ramp_times + timing_half_width_s, grid_time_s, primary_rate)
    timing = np.maximum(np.abs(early - nominal), np.abs(late - nominal))

    coarse_time = grid_time_s[::2]
    current_observed = observe_grid(propagated, OBSERVER, grid)
    shift = doppler_shift_hz(
        float(stream["rf_center_frequency_hz"]),
        current_observed.range_rate_km_s[catalogue_index],
    )
    coarse_rate = np.gradient(shift[::2], coarse_time, edge_order=2)
    finite_difference = np.interp(ramp_times, coarse_time, coarse_rate) - nominal

    selected_propagated = PropagatedWindow(
        utc_ns=propagated.utc_ns,
        position_teme_km=propagated.position_teme_km[catalogue_index : catalogue_index + 1],
        velocity_teme_km_s=propagated.velocity_teme_km_s[catalogue_index : catalogue_index + 1],
        error_code=propagated.error_code[catalogue_index : catalogue_index + 1],
    )
    sites = tuple(site for _direction, site in _shifted_sites(SITE_UNCERTAINTY_M))
    site_differences = []
    for site in sites:
        shifted = observe_grid(selected_propagated, site, grid)
        shifted_rate = _doppler_rate_bank(
            shifted,
            grid_time_s,
            float(stream["rf_center_frequency_hz"]),
        )[0]
        site_differences.append(np.interp(ramp_times, grid_time_s, shifted_rate) - nominal)
    return {
        "candidate_bank_position": bank_position,
        "capture_timing_half_width_s": timing_half_width_s,
        "timing_max_absolute_rate_effect_hz_s": float(np.max(timing)),
        "timing_rate_effect_rms_hz_s": float(np.sqrt(np.mean(timing**2))),
        "finite_difference_step_s": RATE_GRID_STEP_S,
        "finite_difference_coarse_comparison_step_s": 2.0 * RATE_GRID_STEP_S,
        "finite_difference_rate_rms_hz_s": float(np.sqrt(np.mean(finite_difference**2))),
        "site_position_uncertainty_m": SITE_UNCERTAINTY_M,
        "site_max_rate_rms_hz_s": max(
            float(np.sqrt(np.mean(values**2))) for values in site_differences
        ),
        "site_max_nuisance_removed_rate_rms_hz_s": max(
            _centered_rms(values) for values in site_differences
        ),
        "pilot_rf_half_width_hz": PILOT_RF_HALF_WIDTH_HZ,
        "rf_scale_max_rate_effect_hz_s": float(np.max(np.abs(nominal)))
        * PILOT_RF_HALF_WIDTH_HZ
        / float(stream["rf_center_frequency_hz"]),
        "previous_snapshot": _snapshot_sensitivity(
            previous,
            catalogues,
            catalog_number,
            grid,
            grid_time_s,
            ramp_times,
            OBSERVER,
            float(stream["rf_center_frequency_hz"]),
            primary_rate,
        ),
        "following_snapshot_noncausal_sensitivity_only": _snapshot_sensitivity(
            following,
            catalogues,
            catalog_number,
            grid,
            grid_time_s,
            ramp_times,
            OBSERVER,
            float(stream["rf_center_frequency_hz"]),
            primary_rate,
        ),
    }


def associate_one(
    *,
    row: dict[str, Any],
    raw_result: dict[str, Any],
    snapshots: tuple[TleSnapshotRef, ...],
    catalogues: dict[str, ElementSetCatalogue],
) -> dict[str, object]:
    series, selected = _radio_series(raw_result)
    candidate = selected["candidate"]
    stream = _stream(row, str(candidate["stream_id"]))
    first_ns = int(stream["first_sample_estimate_utc_ns"])
    previous, primary_snapshot, following = causal_snapshot_triplet(snapshots, first_ns)
    catalogue = catalogues[primary_snapshot.digest]
    grid, grid_time_s = _rate_grid(first_ns, series)
    propagated = propagate_grid(catalogue, grid)
    observed = observe_grid(propagated, OBSERVER, grid)
    rate_bank = _doppler_rate_bank(
        observed,
        grid_time_s,
        float(stream["rf_center_frequency_hz"]),
    )
    primary_candidates, primary_indices = _candidate_series(
        catalogue,
        observed,
        grid_time_s,
        rate_bank,
        series,
        elevation_threshold_deg=PRIMARY_ELEVATION_DEG,
        anchor_utc_ns=first_ns + round(float(np.mean(series.time_s)) * NS_PER_S),
    )
    control_candidates, _control_indices = _candidate_series(
        catalogue,
        observed,
        grid_time_s,
        rate_bank,
        series,
        elevation_threshold_deg=CONTROL_ELEVATION_DEG,
        anchor_utc_ns=first_ns + round(float(np.mean(series.time_s)) * NS_PER_S),
    )
    if not primary_candidates:
        raise ValueError("no Starlink object remains above the primary elevation gate")
    models = _association_models(series, primary_candidates)
    control_models = _association_models(series, control_candidates)
    primary_model = models["bounded_200"]
    best = primary_model["ranked"][0]
    diagnostics = selected["result"]["diagnostics"]
    return {
        "schema": "org.leo.research.ramp-tle-association/v1",
        "label": row["label"],
        "session_id": row["session_id"],
        "run_id": row["run_id"],
        "stream_id": candidate["stream_id"],
        "radio_id": stream["radio_id"],
        "receiver_id": candidate["receiver_id"],
        "branch_id": candidate["branch_id"],
        "starlink_channel": stream["starlink_channel"],
        "starlink_edge": stream["starlink_edge"],
        "rf_center_frequency_hz": stream["rf_center_frequency_hz"],
        "first_sample_estimate_utc_ns": first_ns,
        "observer": OBSERVER.model_dump(mode="json"),
        "observer_capture_bound": False,
        "primary_elevation_gate_deg": PRIMARY_ELEVATION_DEG,
        "control_elevation_gate_deg": CONTROL_ELEVATION_DEG,
        "tle_snapshot_policy": "latest complete snapshot collected at or before first sample",
        "primary_tle_snapshot": {
            "collected_utc_ns": primary_snapshot.collected_utc_ns,
            "digest": primary_snapshot.digest,
            "object_count": len(catalogue),
        },
        "radio_rate_evidence": {
            "ramp_count": len(series.time_s),
            "overall_glrt_rate_hz_s": diagnostics["overall_glrt_rate_hz_s"],
            "overall_glrt_rate_sigma_hz_s": diagnostics["overall_glrt_rate_sigma_hz_s"],
            "local_corrected_rate_hz_s": diagnostics["local_corrected_rate_hz_s"],
            "local_conditional_sigma_hz_s": diagnostics["local_conditional_sigma_hz_s"],
            "local_practical_sigma_hz_s": diagnostics["local_practical_sigma_hz_s"],
            "local_p025_hz_s": diagnostics["local_p025_hz_s"],
            "local_p975_hz_s": diagnostics["local_p975_hz_s"],
            "rate_correction_hz_s": diagnostics["rate_correction_hz_s"],
            "strict_gate_rate_spread_hz_s": diagnostics["strict_gate_rate_spread_hz_s"],
            "odd_validation_reduction_percent": diagnostics["odd_validation_reduction_percent"],
            "bic_progression_minus_common": diagnostics["bic_progression_minus_common"],
            "measured_ramp_rates": asdict(series),
        },
        "primary_models": models,
        "broad_sky_control_models": control_models,
        "association_sensitivity": {
            "best_identity_by_rate_nuisance_model": {
                name: _top_summary(model)["best"] for name, model in models.items()
            },
            "broad_sky_control": _top_summary(control_models["bounded_200"]),
            "previous_complete_snapshot": _alternate_snapshot_association(
                previous,
                catalogues,
                grid,
                grid_time_s,
                series,
                first_ns,
                float(stream["rf_center_frequency_hz"]),
            ),
            "following_complete_snapshot_noncausal_sensitivity_only": (
                _alternate_snapshot_association(
                    following,
                    catalogues,
                    grid,
                    grid_time_s,
                    series,
                    first_ns,
                    float(stream["rf_center_frequency_hz"]),
                )
            ),
            "observer_site_provenance_stress": _site_identity_stress(
                catalogue=catalogue,
                propagated=propagated,
                grid_time_s=grid_time_s,
                grid=grid,
                series=series,
                first_sample_utc_ns=first_ns,
                rf_frequency_hz=float(stream["rf_center_frequency_hz"]),
            ),
        },
        "best_candidate_error_budget": _best_error_budget(
            best=best,
            catalogue=catalogue,
            previous=previous,
            following=following,
            catalogues=catalogues,
            grid=grid,
            grid_time_s=grid_time_s,
            propagated=propagated,
            rate_bank=rate_bank,
            candidate_indices=primary_indices,
            series=series,
            stream=stream,
        ),
        "identity_claim": "candidate_only",
        "unidentifiable_rate_terms": [
            "receiver oscillator or LNB drift",
            "transmitter frequency-plan drift",
            "sample-clock scale error beyond configured RF scaling",
        ],
    }


def main() -> None:
    arguments = _arguments()
    inputs = _load(arguments.inputs)
    rows = tuple(inputs.get("dwells", ()))
    archive = TleArchiveReader(arguments.tle_root)
    snapshots, catalogues, inventory = complete_catalogues(archive)
    output = []
    for row in rows:
        if arguments.only_label is not None and row["label"] != arguments.only_label:
            continue
        path = _result_path(arguments.results, row)
        if not path.is_file():
            output.append(
                {
                    "label": row["label"],
                    "session_id": row["session_id"],
                    "status": "raw_result_missing",
                }
            )
            continue
        raw_result = _load(path)
        try:
            associated = associate_one(
                row=row,
                raw_result=raw_result,
                snapshots=snapshots,
                catalogues=catalogues,
            )
        except (ValueError, RuntimeError) as error:
            associated = {
                "label": row["label"],
                "session_id": row["session_id"],
                "status": "association_unavailable",
                "reason": f"{type(error).__name__}: {error}",
            }
        else:
            associated["status"] = "complete"
        output.append(associated)
        print(f"{row['label']}: {associated['status']}", flush=True)
    document = {
        "schema": "org.leo.research.recent-ramp-tle-associations/v1",
        "inputs_path": str(arguments.inputs),
        "inputs_digest": _digest(arguments.inputs),
        "raw_results_root": str(arguments.results),
        "tle_root": str(arguments.tle_root),
        "tle_authority_root": str(arguments.tle_authority_root),
        "tle_provider": PROVIDER,
        "tle_catalogue_completeness_fraction": TLE_COMPLETENESS_FRACTION,
        "tle_snapshot_inventory": inventory,
        "observer": OBSERVER.model_dump(mode="json"),
        "observer_capture_bound": False,
        "dwell_count": len(output),
        "complete_association_count": sum(item["status"] == "complete" for item in output),
        "dwells": output,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
