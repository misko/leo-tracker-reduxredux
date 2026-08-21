#!/usr/bin/env python3
"""Render a per-dwell Standard GLRT and zenith-cone TLE Doppler-rate report.

The tool is read-only with respect to the catalog, sealed analysis artifacts,
TLE archive, and RF corpus. It writes only the requested retrospective report
bundle beneath ``--output-root``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.acquisition.starlink_tuning import STARLINK_LNB_LO_HZ
from leo.analysis.research.tle_doppler_alignment import (
    ThresholdInterval,
    threshold_intervals,
)
from leo.catalog.database import create_catalog_engine
from leo.catalog.models import (
    AnalysisProduct,
    AnalysisRun,
    AnalysisScope,
    CaptureSession,
    CurrentAnalysis,
    RunSubjectBinding,
)
from leo.contracts.cfo_dealias import (
    DealiasedTrajectoryBankV3,
    Glrt64FinalTrajectoryTableV3,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import ObservedTracks, observe_grid
from leo.storage import BulkUriResolver

DEFAULT_DATABASE_URL = "postgresql+psycopg:///leo_tracker"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_TLE_ROOT = Path("/var/lib/leo/tle")
DEFAULT_LATITUDE_DEG = 37.858988
DEFAULT_LONGITUDE_DEG = -122.478103
DEFAULT_ALTITUDE_M = -29.0
DEFAULT_CONE_HALF_ANGLE_DEG = 30.0
GRID_SPACING_S = 0.25
_NS_PER_S = 1_000_000_000
EPOCH_SEARCH_S = 2.5
EPOCH_STEP_S = 0.05
PREDICTION_PADDING_S = 35.0
MAXIMUM_NUISANCE_DRIFT_HZ_S = 200.0
MAXIMUM_HOLDOUT_RMS_HZ = 500.0
MINIMUM_RUNNER_UP_MARGIN_HZ = 100.0
MINIMUM_TIME_CONTROL_ADVANTAGE_HZ = 100.0
MINIMUM_OVERLAP_S = 10.0
MINIMUM_OVERLAP_FRACTION = 0.5
RATE_COMPATIBILITY_HZ_S = 2_500.0
TRAIN_FRACTIONS = (0.5, 0.6, 0.7)
TIGHTER_DRIFT_FRACTION = 0.8
TIME_CONTROL_SHIFTS_S = (-30.0, 30.0)


@dataclass(frozen=True, slots=True)
class CohortRun:
    run_id: str
    session_id: str
    pipeline_release_id: str
    observed_start_at: datetime


@dataclass(frozen=True, slots=True)
class PathEvidence:
    binding: StandardPathInputBindV3
    scope_digest: str
    raw_table: dict[str, Any]
    raw_product: AnalysisProduct
    dealiased_bank: DealiasedTrajectoryBankV3
    dealiased_product: AnalysisProduct
    final_table: Glrt64FinalTrajectoryTableV3
    final_product: AnalysisProduct
    rf_frequency_hz: int

    @property
    def label(self) -> str:
        return f"{self.binding.stream_id}/RX{self.binding.receiver_id}"


@dataclass(frozen=True, slots=True)
class ConeSatellite:
    catalogue_index: int
    object_name: str
    catalog_number: int
    peak_elevation_deg: float
    element_epoch_utc_ns: int
    element_age_s: float
    intervals: tuple[ThresholdInterval, ...]


@dataclass(frozen=True, slots=True)
class FinalTrack:
    label: str
    path: PathEvidence
    row: Any
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True, slots=True)
class TrackObservations:
    time_s: np.ndarray
    cfo_hz: np.ndarray


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=DEFAULT_TLE_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--session-id", action="append", dest="session_ids", required=True)
    parser.add_argument("--provider", default="space-track")
    parser.add_argument("--latitude-deg", type=float, default=DEFAULT_LATITUDE_DEG)
    parser.add_argument("--longitude-deg", type=float, default=DEFAULT_LONGITUDE_DEG)
    parser.add_argument("--altitude-m", type=float, default=DEFAULT_ALTITUDE_M)
    parser.add_argument(
        "--gps-source",
        default="reviewed spinnaker-sausalito preset; not capture-bound GPS authority",
    )
    parser.add_argument(
        "--cone-half-angle-deg",
        type=float,
        default=DEFAULT_CONE_HALF_ANGLE_DEG,
    )
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _cohort(database: Session, session_ids: tuple[str, ...]) -> tuple[CohortRun, ...]:
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("exact session IDs must be unique")
    observed = func.coalesce(CaptureSession.observed_start_at, CaptureSession.created_at)
    rows = database.execute(
        select(AnalysisRun, CaptureSession, observed)
        .join(CurrentAnalysis, CurrentAnalysis.run_id == AnalysisRun.id)
        .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
        .where(
            AnalysisRun.state == "succeeded",
            AnalysisRun.pipeline_lane == "standard",
            CaptureSession.id.in_(session_ids),
            CaptureSession.source_type != "test",
        )
    ).all()
    by_session = {capture.id: (run, start) for run, capture, start in rows}
    missing = [session_id for session_id in session_ids if session_id not in by_session]
    if missing:
        raise ValueError("sessions lack current succeeded Standard runs: " + ", ".join(missing))
    return tuple(
        CohortRun(
            run_id=by_session[session_id][0].id,
            session_id=session_id,
            pipeline_release_id=by_session[session_id][0].pipeline_release_id,
            observed_start_at=by_session[session_id][1],
        )
        for session_id in session_ids
    )


def _read_verified_json(resolver: BulkUriResolver, product: AnalysisProduct) -> dict[str, Any]:
    payload = resolver.resolve(product.logical_uri).read_bytes()
    digest = _sha256(payload)
    if digest != product.digest:
        raise ValueError(f"artifact digest mismatch: {product.logical_uri}")
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError(f"artifact is not a JSON object: {product.logical_uri}")
    return document


def _validate_raw_table(document: dict[str, Any]) -> None:
    if (
        document.get("schema_version") != 2
        or document.get("algorithm_version") != "standard-glrt64-trajectory-table-v2"
        or document.get("frequency_model")
        != "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
    ):
        raise ValueError("raw GLRT trajectory table has an unexpected contract")
    rows = document.get("trajectories")
    if not isinstance(rows, list):
        raise ValueError("raw GLRT trajectory table lacks trajectories")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("raw GLRT trajectory row is not an object")
        degree = int(row["polynomial_degree"])
        coefficients = row["coefficients_hz"]
        numbers = (
            float(row["start_s"]),
            float(row["end_s"]),
            float(row["reference_time_s"]),
            *(float(value) for value in coefficients),
        )
        if degree not in (1, 2, 3) or len(coefficients) != degree + 1:
            raise ValueError("raw GLRT trajectory geometry is inconsistent")
        if numbers[1] < numbers[0] or any(not math.isfinite(value) for value in numbers):
            raise ValueError("raw GLRT trajectory values are invalid")


def _path_evidence(
    database: Session,
    resolver: BulkUriResolver,
    run: CohortRun,
) -> tuple[PathEvidence, ...]:
    bindings = database.execute(
        select(RunSubjectBinding, AnalysisScope)
        .join(AnalysisScope, AnalysisScope.id == RunSubjectBinding.scope_id)
        .where(
            RunSubjectBinding.run_id == run.run_id,
            AnalysisScope.kind == "receiver_path",
        )
    ).all()
    products = database.execute(
        select(AnalysisProduct, AnalysisScope)
        .join(AnalysisScope, AnalysisScope.id == AnalysisProduct.scope_id)
        .where(
            AnalysisProduct.run_id == run.run_id,
            AnalysisProduct.kind.in_(
                (
                    "standard.glrt64-trajectory-table",
                    "standard.dealiased-trajectory-bank",
                    "standard.glrt64-final-trajectory-table",
                )
            ),
            AnalysisProduct.available.is_(True),
        )
    ).all()
    by_key: dict[tuple[int, str], AnalysisProduct] = {}
    for product, scope in products:
        key = (scope.id, product.kind)
        if key in by_key:
            raise ValueError(f"duplicate trajectory product for scope {scope.id}")
        by_key[key] = product

    result = []
    for registration, scope in bindings:
        binding = StandardPathInputBindV3.model_validate(registration.document)
        raw_product = by_key.get((scope.id, "standard.glrt64-trajectory-table"))
        dealiased_product = by_key.get((scope.id, "standard.dealiased-trajectory-bank"))
        final_product = by_key.get((scope.id, "standard.glrt64-final-trajectory-table"))
        if raw_product is None or dealiased_product is None or final_product is None:
            raise ValueError(
                f"path lacks raw, de-aliased, or final trajectory evidence: {scope.id}"
            )
        if (
            raw_product.schema_version != 2
            or dealiased_product.schema_version != 3
            or final_product.schema_version != 3
        ):
            raise ValueError(
                "path trajectory schema is not raw V2/de-aliased V3/final V3: "
                f"{scope.id}"
            )
        raw = _read_verified_json(resolver, raw_product)
        _validate_raw_table(raw)
        dealiased = DealiasedTrajectoryBankV3.model_validate(
            _read_verified_json(resolver, dealiased_product)
        )
        final = Glrt64FinalTrajectoryTableV3.model_validate(
            _read_verified_json(resolver, final_product)
        )
        result.append(
            PathEvidence(
                binding=binding,
                scope_digest=scope.canonical_digest,
                raw_table=raw,
                raw_product=raw_product,
                dealiased_bank=dealiased,
                dealiased_product=dealiased_product,
                final_table=final,
                final_product=final_product,
                rf_frequency_hz=binding.tuned_center_frequency_hz + STARLINK_LNB_LO_HZ,
            )
        )
    if len(result) != 4:
        raise ValueError(f"expected four receiver paths for {run.session_id}, found {len(result)}")
    return tuple(
        sorted(result, key=lambda item: (item.binding.stream_id, item.binding.receiver_id))
    )


def _nominal_capture(paths: tuple[PathEvidence, ...]) -> tuple[int, float]:
    durations = {
        path.binding.declared_sample_count / path.binding.sample_rate_hz for path in paths
    }
    if len(durations) != 1:
        raise ValueError("receiver paths disagree on nominal capture duration")
    starts = sorted(path.binding.timing.first_estimate_utc_ns for path in paths)
    start_ns = (starts[1] + starts[2]) // 2
    return start_ns, durations.pop()


def _grid(start_utc_ns: int, duration_s: float) -> SamplingGrid:
    per_side = math.ceil(duration_s / (2.0 * GRID_SPACING_S))
    anchor_ns = start_utc_ns + round(duration_s * _NS_PER_S / 2.0)
    step_ns = round(GRID_SPACING_S * _NS_PER_S)
    instants = tuple(
        anchor_ns + (index - per_side) * step_ns for index in range(2 * per_side + 1)
    )
    return SamplingGrid(instants, per_side, GRID_SPACING_S)


def _cone_satellites(
    catalogue: ElementSetCatalogue,
    tracks: ObservedTracks,
    sample_times_s: np.ndarray,
    *,
    elevation_threshold_deg: float,
    anchor_utc_ns: int,
) -> tuple[ConeSatellite, ...]:
    plausible = tracks.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    selected = np.flatnonzero(
        tracks.usable
        & plausible
        & (tracks.elevation_deg.max(axis=1) >= elevation_threshold_deg)
    )
    epochs = catalogue.element_epoch_utc_ns()
    result = []
    for raw_index in selected:
        index = int(raw_index)
        intervals = threshold_intervals(
            sample_times_s,
            tracks.elevation_deg[index],
            threshold=elevation_threshold_deg,
        )
        if not intervals:
            continue
        epoch_ns = epochs[index]
        result.append(
            ConeSatellite(
                catalogue_index=index,
                object_name=catalogue.names[index][:64],
                catalog_number=catalogue.satellite_numbers[index],
                peak_elevation_deg=float(tracks.elevation_deg[index].max()),
                element_epoch_utc_ns=epoch_ns,
                element_age_s=abs(anchor_utc_ns - epoch_ns) / _NS_PER_S,
                intervals=intervals,
            )
        )
    return tuple(sorted(result, key=lambda item: (item.object_name, item.catalog_number)))


def _path_offset_s(path: PathEvidence, dwell_start_ns: int) -> float:
    return (path.binding.timing.first_estimate_utc_ns - dwell_start_ns) / _NS_PER_S


def _all_final_tracks(
    paths: tuple[PathEvidence, ...], dwell_start_ns: int
) -> tuple[FinalTrack, ...]:
    candidates = []
    for path in paths:
        offset = _path_offset_s(path, dwell_start_ns)
        for row in path.final_table.trajectories:
            candidates.append((path, row, offset + row.start_s, offset + row.end_s))
    candidates.sort(
        key=lambda item: (
            -(item[3] - item[2]),
            -len(item[1].observation_ids),
            -(item[1].median_block_corrected_margin or -math.inf),
            item[0].label,
            item[1].trajectory_id,
        )
    )
    return tuple(
        FinalTrack(label=f"T{index}", path=path, row=row, start_s=start, end_s=end)
        for index, (path, row, start, end) in enumerate(candidates, start=1)
    )


def _satellite_rates(
    path: PathEvidence,
    satellites: tuple[ConeSatellite, ...],
    observed_tracks: ObservedTracks,
    sample_times_s: np.ndarray,
) -> dict[int, np.ndarray]:
    result = {}
    for satellite in satellites:
        shift = doppler_shift_hz(
            path.rf_frequency_hz,
            observed_tracks.range_rate_km_s[satellite.catalogue_index],
        )
        result[satellite.catalog_number] = np.gradient(shift, sample_times_s, edge_order=2)
    return result


def _satellite_doppler(
    path: PathEvidence,
    satellites: tuple[ConeSatellite, ...],
    observed_tracks: ObservedTracks,
) -> dict[int, np.ndarray]:
    """Return predicted Doppler series for rows ordered like ``satellites``."""

    if observed_tracks.range_rate_km_s.shape[0] != len(satellites):
        raise ValueError("extended prediction rows disagree with cone satellites")
    return {
        satellite.catalog_number: doppler_shift_hz(
            path.rf_frequency_hz,
            observed_tracks.range_rate_km_s[index],
        )
        for index, satellite in enumerate(satellites)
    }


def _interval_mask(
    sample_times_s: np.ndarray,
    intervals: tuple[ThresholdInterval, ...],
) -> np.ndarray:
    mask = np.zeros(sample_times_s.shape, dtype=bool)
    for interval in intervals:
        mask |= (sample_times_s >= interval.start_s) & (sample_times_s <= interval.end_s)
    return mask


def _linear_rate_hz_s(coefficients_hz: tuple[float, ...] | list[float]) -> float:
    """Return the CFO polynomial's rate at its declared reference time."""

    if not 2 <= len(coefficients_hz) <= 4:
        raise ValueError("trajectory polynomial must have two to four coefficients")
    coefficients = tuple(float(value) for value in coefficients_hz)
    if any(not math.isfinite(value) for value in coefficients):
        raise ValueError("trajectory coefficients must be finite")
    # Coefficients are highest-power first.  At t == reference_time_s, every
    # differentiated nonlinear term is multiplied by zero, leaving this term.
    return coefficients[-2]


def _track_path_offset_s(track: FinalTrack) -> float:
    return track.start_s - float(track.row.start_s)


def _track_cfo(track: FinalTrack, dwell_times_s: np.ndarray) -> np.ndarray:
    local_times = np.asarray(dwell_times_s, dtype=np.float64) - _track_path_offset_s(track)
    return _evaluate_polynomial(
        track.row,
        local_times,
        coefficients_key="absolute_coefficients_hz",
    )


def _track_rate(track: FinalTrack, dwell_times_s: np.ndarray) -> np.ndarray:
    """Evaluate the instantaneous derivative of one sealed CFO polynomial."""

    coefficients = np.asarray(track.row.absolute_coefficients_hz, dtype=np.float64)
    derivative = np.polyder(coefficients)
    local_times = np.asarray(dwell_times_s, dtype=np.float64) - _track_path_offset_s(track)
    return np.polyval(derivative, local_times - float(track.row.reference_time_s))


def _track_observations(track: FinalTrack) -> TrackObservations:
    wanted = set(track.row.observation_ids)
    by_id = {
        item.observation_id: item
        for item in track.path.dealiased_bank.observations
        if item.observation_id in wanted
    }
    if set(by_id) != wanted:
        raise ValueError(f"final trajectory {track.row.trajectory_id} lacks canonical observations")
    lift_hz = float(
        track.row.absolute_coefficients_hz[-1]
        - track.row.canonical_coefficients_hz[-1]
    )
    ordered = sorted(by_id.values(), key=lambda item: (item.time_s, item.observation_id))
    offset_s = _track_path_offset_s(track)
    return TrackObservations(
        time_s=np.asarray([offset_s + item.time_s for item in ordered], dtype=np.float64),
        cfo_hz=np.asarray(
            [item.component_cfo_hz + lift_hz for item in ordered], dtype=np.float64
        ),
    )


def _overlap_segments(
    track: FinalTrack,
    satellite: ConeSatellite,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (start, end)
        for interval in satellite.intervals
        if (start := max(track.start_s, interval.start_s))
        < (end := min(track.end_s, interval.end_s))
    )


def _segments_mask(times_s: np.ndarray, segments: tuple[tuple[float, float], ...]) -> np.ndarray:
    mask = np.zeros(np.asarray(times_s).shape, dtype=bool)
    for start, end in segments:
        mask |= (times_s >= start) & (times_s <= end)
    return mask


def _interval_rate_metrics(
    track: FinalTrack,
    satellite: ConeSatellite,
    prediction_times_s: np.ndarray,
    predicted_doppler_hz: np.ndarray,
    *,
    epoch_adjustment_s: float = 0.0,
) -> dict[str, float] | None:
    segments = _overlap_segments(track, satellite)
    if not segments:
        return None
    mask = _segments_mask(prediction_times_s, segments)
    times = np.asarray(prediction_times_s[mask], dtype=np.float64)
    if times.size < 3 or np.ptp(times) <= 0:
        return None
    measured = _track_cfo(track, times)
    predicted = np.interp(
        times + epoch_adjustment_s,
        prediction_times_s,
        predicted_doppler_hz,
    )
    centered = times - float(np.mean(times))
    measured_slope = float(np.polyfit(centered, measured, 1)[0])
    predicted_slope = float(np.polyfit(centered, predicted, 1)[0])
    measured_rate = _track_rate(track, times)
    predicted_rate = np.gradient(predicted, times, edge_order=2)
    difference = measured_rate - predicted_rate
    overlap_duration_s = float(sum(end - start for start, end in segments))
    return {
        "overlap_start_s": float(times[0]),
        "overlap_end_s": float(times[-1]),
        "overlap_duration_s": overlap_duration_s,
        "overlap_fraction": overlap_duration_s / track.duration_s,
        "measured_linear_rate_hz_s": measured_slope,
        "predicted_linear_rate_hz_s": predicted_slope,
        "signed_linear_rate_difference_hz_s": measured_slope - predicted_slope,
        "absolute_linear_rate_difference_hz_s": abs(measured_slope - predicted_slope),
        "instantaneous_rate_rms_difference_hz_s": float(
            np.sqrt(np.mean(difference**2))
        ),
    }


def _temporal_split(times_s: np.ndarray, fraction: float) -> tuple[np.ndarray, np.ndarray]:
    if times_s.size < 6 or not 0.0 < fraction < 1.0:
        raise ValueError("held-out matching requires six observations and a valid split")
    order = np.argsort(times_s, kind="stable")
    cutoff = int(np.clip(math.ceil(fraction * order.size), 3, order.size - 3))
    train = np.zeros(order.size, dtype=bool)
    train[order[:cutoff]] = True
    return train, ~train


def _fit_nuisance(
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


def _evaluate_candidate_shift(
    observations: TrackObservations,
    prediction_times_s: np.ndarray,
    predicted_doppler_hz: np.ndarray,
    train: np.ndarray,
    shift_s: float,
    maximum_drift_hz_s: float,
) -> dict[str, Any] | None:
    shifted = observations.time_s + shift_s
    if shifted.min() < prediction_times_s[0] or shifted.max() > prediction_times_s[-1]:
        return None
    predicted = np.interp(shifted, prediction_times_s, predicted_doppler_hz)
    residual, reference_s, offset_hz, drift_hz_s = _fit_nuisance(
        observations.time_s,
        observations.cfo_hz - predicted,
        train,
        maximum_drift_hz_s,
    )
    holdout = ~train
    return {
        "epoch_adjustment_s": float(shift_s),
        "train_residual_rms_hz": float(np.sqrt(np.mean(residual[train] ** 2))),
        "holdout_residual_rms_hz": float(np.sqrt(np.mean(residual[holdout] ** 2))),
        "full_residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "nuisance_reference_s": reference_s,
        "fitted_frequency_offset_hz": offset_hz,
        "nuisance_drift_hz_s": drift_hz_s,
        "residual_hz": residual,
    }


def _rank_track_candidates(
    track: FinalTrack,
    satellites: tuple[ConeSatellite, ...],
    prediction_times_s: np.ndarray,
    predicted_by_satellite: dict[int, np.ndarray],
    *,
    train_fraction: float,
    maximum_drift_hz_s: float,
    retain_timing_profile: bool = False,
) -> tuple[dict[str, Any], ...]:
    source = _track_observations(track)
    shifts = np.arange(-EPOCH_SEARCH_S, EPOCH_SEARCH_S + EPOCH_STEP_S / 2, EPOCH_STEP_S)
    ranked = []
    for satellite in satellites:
        segments = _overlap_segments(track, satellite)
        overlap_duration_s = sum(end - start for start, end in segments)
        overlap_fraction = overlap_duration_s / track.duration_s
        selected = _segments_mask(source.time_s, segments)
        if (
            overlap_duration_s < MINIMUM_OVERLAP_S
            or overlap_fraction < MINIMUM_OVERLAP_FRACTION
            or np.count_nonzero(selected) < 6
        ):
            continue
        observations = TrackObservations(source.time_s[selected], source.cfo_hz[selected])
        train, _ = _temporal_split(observations.time_s, train_fraction)
        profile = []
        best = None
        for shift_s in shifts:
            evaluated = _evaluate_candidate_shift(
                observations,
                prediction_times_s,
                predicted_by_satellite[satellite.catalog_number],
                train,
                float(shift_s),
                maximum_drift_hz_s,
            )
            if evaluated is None:
                continue
            profile.append(
                {
                    "epoch_adjustment_s": evaluated["epoch_adjustment_s"],
                    "train_residual_rms_hz": evaluated["train_residual_rms_hz"],
                    "holdout_residual_rms_hz": evaluated["holdout_residual_rms_hz"],
                }
            )
            if best is None or (
                evaluated["train_residual_rms_hz"],
                evaluated["holdout_residual_rms_hz"],
            ) < (
                best["train_residual_rms_hz"],
                best["holdout_residual_rms_hz"],
            ):
                best = evaluated
        if best is None:
            continue
        controls = []
        for shift_s in TIME_CONTROL_SHIFTS_S:
            control = _evaluate_candidate_shift(
                observations,
                prediction_times_s,
                predicted_by_satellite[satellite.catalog_number],
                train,
                shift_s,
                maximum_drift_hz_s,
            )
            if control is not None:
                controls.append(control["holdout_residual_rms_hz"])
        rate = _interval_rate_metrics(
            track,
            satellite,
            prediction_times_s,
            predicted_by_satellite[satellite.catalog_number],
            epoch_adjustment_s=best["epoch_adjustment_s"],
        )
        if rate is None:
            continue
        control_rms = min(controls) if controls else None
        ranked.append(
            {
                "object_name": satellite.object_name,
                "catalog_number": satellite.catalog_number,
                "peak_elevation_deg": satellite.peak_elevation_deg,
                "overlap_start_s": rate["overlap_start_s"],
                "overlap_end_s": rate["overlap_end_s"],
                "overlap_duration_s": overlap_duration_s,
                "overlap_fraction": overlap_fraction,
                "observation_count": int(observations.time_s.size),
                "train_end_s": float(np.max(observations.time_s[train])),
                "holdout_start_s": float(np.min(observations.time_s[~train])),
                **{key: value for key, value in best.items() if key != "residual_hz"},
                **rate,
                "epoch_at_search_boundary": bool(
                    abs(abs(best["epoch_adjustment_s"]) - EPOCH_SEARCH_S)
                    <= EPOCH_STEP_S / 2 + 1e-9
                ),
                "time_control_best_holdout_rms_hz": control_rms,
                "time_control_advantage_hz": (
                    None
                    if control_rms is None
                    else control_rms - best["holdout_residual_rms_hz"]
                ),
                "timing_profile": profile if retain_timing_profile else [],
            }
        )
    ranked.sort(
        key=lambda item: (
            item["holdout_residual_rms_hz"],
            item["train_residual_rms_hz"],
            item["catalog_number"],
        )
    )
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
        if retain_timing_profile and index > 3:
            item["timing_profile"] = []
    return tuple(ranked)


def _ranking_gate(ranked: tuple[dict[str, Any], ...], *, require_control: bool) -> dict[str, Any]:
    best = ranked[0] if ranked else None
    margin = (
        ranked[1]["holdout_residual_rms_hz"] - best["holdout_residual_rms_hz"]
        if best is not None and len(ranked) > 1
        else None
    )
    control_passed = bool(
        best
        and (
            not require_control
            or (
                best["time_control_advantage_hz"] is not None
                and best["time_control_advantage_hz"] >= MINIMUM_TIME_CONTROL_ADVANTAGE_HZ
            )
        )
    )
    rms_passed = bool(
        best and best["holdout_residual_rms_hz"] <= MAXIMUM_HOLDOUT_RMS_HZ
    )
    epoch_interior = bool(best and not best["epoch_at_search_boundary"])
    margin_passed = bool(best and (margin is None or margin >= MINIMUM_RUNNER_UP_MARGIN_HZ))
    passed = bool(
        best and rms_passed and epoch_interior and margin_passed and control_passed
    )
    return {
        "passed": passed,
        "best_catalog_number": None if best is None else best["catalog_number"],
        "best_name": None if best is None else best["object_name"],
        "holdout_residual_rms_hz": (
            None if best is None else best["holdout_residual_rms_hz"]
        ),
        "margin_to_second_hz": margin,
        "epoch_adjustment_s": None if best is None else best["epoch_adjustment_s"],
        "epoch_at_search_boundary": (
            None if best is None else best["epoch_at_search_boundary"]
        ),
        "holdout_rms_passed": rms_passed,
        "epoch_interior": epoch_interior,
        "runner_up_margin_passed": margin_passed,
        "time_control_passed": control_passed,
    }


def _analyze_track_matches(
    track: FinalTrack,
    satellites: tuple[ConeSatellite, ...],
    prediction_times_s: np.ndarray,
    predicted_by_satellite: dict[int, np.ndarray],
) -> dict[str, Any]:
    primary = _rank_track_candidates(
        track,
        satellites,
        prediction_times_s,
        predicted_by_satellite,
        train_fraction=0.6,
        maximum_drift_hz_s=MAXIMUM_NUISANCE_DRIFT_HZ_S,
        retain_timing_profile=True,
    )
    primary_gate = _ranking_gate(primary, require_control=True)
    sensitivity = []
    cases = [(fraction, MAXIMUM_NUISANCE_DRIFT_HZ_S) for fraction in (0.5, 0.7)]
    cases.append((0.6, MAXIMUM_NUISANCE_DRIFT_HZ_S * TIGHTER_DRIFT_FRACTION))
    for fraction, bound in cases:
        ranked = _rank_track_candidates(
            track,
            satellites,
            prediction_times_s,
            predicted_by_satellite,
            train_fraction=fraction,
            maximum_drift_hz_s=bound,
        )
        sensitivity.append(
            {
                "train_fraction": fraction,
                "maximum_nuisance_drift_hz_s": bound,
                **_ranking_gate(ranked, require_control=False),
            }
        )
    stable_identity = bool(
        primary_gate["best_catalog_number"] is not None
        and all(
            item["best_catalog_number"] == primary_gate["best_catalog_number"]
            for item in sensitivity
        )
    )
    stable = bool(
        stable_identity
        and primary_gate["passed"]
        and all(item["passed"] for item in sensitivity)
    )
    rate_compatible = bool(
        primary
        and min(item["absolute_linear_rate_difference_hz_s"] for item in primary)
        <= RATE_COMPATIBILITY_HZ_S
    )
    classification = (
        "stable_candidate_association"
        if stable
        else "trajectory_compatible_candidate"
        if primary_gate["passed"]
        else "rate_compatible_but_ambiguous"
        if rate_compatible
        else "no_compatible_satellite"
    )
    return {
        "classification": classification,
        "rate_compatible": rate_compatible,
        "trajectory_candidate_count": len(primary),
        "primary_gate": primary_gate,
        "stability": {
            "passed": stable,
            "same_catalog_number_across_cases": stable_identity,
            "sensitivity_cases": sensitivity,
        },
        "trajectory_matches": list(primary),
    }


def _track_satellite_matches(
    track: FinalTrack,
    satellites: tuple[ConeSatellite, ...],
    predicted_doppler: dict[int, np.ndarray],
    prediction_times_s: np.ndarray,
) -> tuple[dict[str, Any], ...]:
    rows = []
    for satellite in satellites:
        rate = _interval_rate_metrics(
            track,
            satellite,
            prediction_times_s,
            predicted_doppler[satellite.catalog_number],
        )
        if rate is None:
            continue
        rows.append(
            {
                "object_name": satellite.object_name,
                "catalog_number": satellite.catalog_number,
                **rate,
                "adequate_overlap": bool(
                    rate["overlap_duration_s"] >= MINIMUM_OVERLAP_S
                    and rate["overlap_fraction"] >= MINIMUM_OVERLAP_FRACTION
                ),
            }
        )
    rows.sort(
        key=lambda item: (
            not item["adequate_overlap"],
            item["absolute_linear_rate_difference_hz_s"],
            item["catalog_number"],
            item["object_name"],
        )
    )
    return tuple(rows)


def _evaluate_polynomial(row: Any, times_s: np.ndarray, *, coefficients_key: str) -> np.ndarray:
    coefficients = np.asarray(
        row[coefficients_key] if isinstance(row, dict) else getattr(row, coefficients_key),
        dtype=np.float64,
    )
    reference = (
        float(row["reference_time_s"])
        if isinstance(row, dict)
        else float(row.reference_time_s)
    )
    return np.polyval(coefficients, times_s - reference)


def _plot_raw(
    path: Path,
    run: CohortRun,
    paths: tuple[PathEvidence, ...],
    duration_s: float,
    dwell_start_ns: int,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    colors = {"linear": "#277da1", "quadratic": "#f8961e", "cubic": "#9b5de5"}
    for axis, evidence in zip(axes.flat, paths, strict=True):
        offset = _path_offset_s(evidence, dwell_start_ns)
        labeled: set[tuple[str, bool]] = set()
        for row in evidence.raw_table["trajectories"]:
            times = np.linspace(float(row["start_s"]), float(row["end_s"]), 160)
            model = str(row["model"])
            selected = bool(row["selected_for_correction"])
            key = (model, selected)
            label = None
            if key not in labeled:
                label = f"{model} · {'selected' if selected else 'unselected'}"
                labeled.add(key)
            axis.plot(
                times + offset,
                _evaluate_polynomial(row, times, coefficients_key="coefficients_hz") / 1_000,
                color=colors.get(model, "#59636e"),
                linewidth=2.3 if selected else 1.0,
                alpha=0.95 if selected else 0.38,
                label=label,
            )
        axis.set_title(
            f"{evidence.label} · {len(evidence.raw_table['trajectories'])} raw fits",
            loc="left",
        )
        axis.set_xlim(0, duration_s)
        axis.grid(alpha=0.16)
        axis.legend(fontsize=7, loc="best")
    for axis in axes[:, 0]:
        axis.set_ylabel("baseband CFO (kHz)")
    for axis in axes[-1, :]:
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        f"Raw GLRT-64 trajectory fits · {run.session_id}\n"
        "pre-dealias standard.glrt64-trajectory-table.v2",
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_final(
    path: Path,
    run: CohortRun,
    paths: tuple[PathEvidence, ...],
    all_tracks: tuple[FinalTrack, ...],
    duration_s: float,
    dwell_start_ns: int,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    top_labels = {track.row.trajectory_id: track.label for track in all_tracks[:3]}
    highlight = {"T1": "#d1495b", "T2": "#00798c", "T3": "#edae49"}
    by_path = {item.label: item for item in paths}
    for axis, path_label in zip(axes.flat, sorted(by_path), strict=True):
        evidence = by_path[path_label]
        offset = _path_offset_s(evidence, dwell_start_ns)
        for row in evidence.final_table.trajectories:
            times = np.linspace(row.start_s, row.end_s, 160)
            top_label = top_labels.get(row.trajectory_id)
            color = "#404b57" if top_label is None else highlight[top_label]
            axis.plot(
                times + offset,
                _evaluate_polynomial(row, times, coefficients_key="absolute_coefficients_hz")
                / 1_000,
                color=color,
                linewidth=3.0 if top_label else 1.4,
                alpha=0.98 if top_label else 0.62,
                label=(
                    f"{top_label} · longest retained" if top_label else "other retained final"
                ),
            )
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        if unique:
            axis.legend(unique.values(), unique.keys(), fontsize=7, loc="best")
        axis.set_title(
            f"{evidence.label} · {len(evidence.final_table.trajectories)} final tracks",
            loc="left",
        )
        axis.set_xlim(0, duration_s)
        axis.grid(alpha=0.16)
    for axis in axes[:, 0]:
        axis.set_ylabel("baseband CFO (kHz)")
    for axis in axes[-1, :]:
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        f"Sealed final GLRT-64 trajectories · {run.session_id}\n"
        "standard.glrt64-final-trajectory-table.v3 · top three by duration highlighted",
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_overlay(
    path: Path,
    run: CohortRun,
    paths: tuple[PathEvidence, ...],
    all_tracks: tuple[FinalTrack, ...],
    satellites: tuple[ConeSatellite, ...],
    rates_by_path: dict[str, dict[int, np.ndarray]],
    sample_times_s: np.ndarray,
    duration_s: float,
    dwell_start_ns: int,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(18, 12), sharex=True, sharey=True)
    palette = plt.get_cmap("turbo")
    satellite_colors = {
        item.catalog_number: palette(index / max(1, len(satellites) - 1))
        for index, item in enumerate(satellites)
    }
    top_labels = {track.row.trajectory_id: track.label for track in all_tracks[:3]}
    highlight = {"T1": "#111111", "T2": "#111111", "T3": "#111111"}
    by_path = {item.label: item for item in paths}
    tracks_by_path: dict[str, list[FinalTrack]] = {item.label: [] for item in paths}
    for track in all_tracks:
        tracks_by_path[track.path.label].append(track)

    satellite_handles = []
    for axis, path_label in zip(axes.flat, sorted(by_path), strict=True):
        evidence = by_path[path_label]
        rates = rates_by_path[path_label]
        for satellite in satellites:
            mask = _interval_mask(sample_times_s, satellite.intervals)
            values = np.where(mask, rates[satellite.catalog_number], np.nan)
            (line,) = axis.plot(
                sample_times_s,
                values,
                color=satellite_colors[satellite.catalog_number],
                linewidth=1.05,
                alpha=0.78,
                label=f"{satellite.object_name} ({satellite.catalog_number})",
            )
            if axis is axes.flat[0]:
                satellite_handles.append(line)
        for track in tracks_by_path[path_label]:
            times = np.linspace(track.start_s, track.end_s, max(80, round(track.duration_s * 20)))
            rate = _track_rate(track, times)
            top_label = top_labels.get(track.row.trajectory_id)
            axis.plot(
                times,
                rate,
                color="#20252b" if top_label is None else highlight[top_label],
                linewidth=3.2 if top_label else 1.8,
                linestyle="--" if top_label else "-",
                alpha=1.0 if top_label else 0.72,
                zorder=10,
            )
            reference_time_s = (
                _path_offset_s(track.path, dwell_start_ns) + track.row.reference_time_s
            )
            if track.start_s <= reference_time_s <= track.end_s:
                axis.scatter(
                    [reference_time_s],
                    [_linear_rate_hz_s(track.row.absolute_coefficients_hz)],
                    color="#111111",
                    s=18 if top_label else 9,
                    alpha=1.0 if top_label else 0.72,
                    zorder=11,
                )
            if top_label:
                midpoint = len(times) // 2
                axis.annotate(
                    top_label,
                    (times[midpoint], rate[midpoint]),
                    xytext=(3, 4),
                    textcoords="offset points",
                    fontsize=8,
                    fontweight="bold",
                    color="#111111",
                    zorder=11,
                )
        axis.axhline(0.0, color="#67717e", linewidth=0.6, alpha=0.5)
        axis.set_xlim(0, duration_s)
        axis.set_title(
            f"{path_label} · RF {evidence.rf_frequency_hz / 1e9:.6f} GHz",
            loc="left",
        )
        axis.grid(alpha=0.16)
    for axis in axes[:, 0]:
        axis.set_ylabel("Doppler rate / detected CFO rate (Hz/s)")
    for axis in axes[-1, :]:
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        f"Measured and predicted Doppler rates · {run.session_id}\n"
        "colored curves: TLE prediction at 60°+ elevation · "
        "black curves: instantaneous derivative of sealed radio CFO polynomial",
        fontweight="bold",
    )
    if satellite_handles:
        figure.legend(
            satellite_handles,
            [handle.get_label() for handle in satellite_handles],
            loc="lower center",
            ncol=5,
            fontsize=7,
            frameon=False,
        )
    figure.tight_layout(rect=(0, 0.11, 1, 0.96))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _candidate_dense_times(
    track: FinalTrack,
    satellite: ConeSatellite,
    *,
    spacing_s: float = 0.1,
) -> np.ndarray:
    pieces = [
        np.linspace(start, end, max(3, round((end - start) / spacing_s) + 1))
        for start, end in _overlap_segments(track, satellite)
    ]
    return np.concatenate(pieces) if pieces else np.empty(0, dtype=np.float64)


def _aligned_candidate_cfo(
    times_s: np.ndarray,
    match: dict[str, Any],
    prediction_times_s: np.ndarray,
    predicted_doppler_hz: np.ndarray,
) -> np.ndarray:
    geometric = np.interp(
        times_s + match["epoch_adjustment_s"],
        prediction_times_s,
        predicted_doppler_hz,
    )
    nuisance = match["fitted_frequency_offset_hz"] + match["nuisance_drift_hz_s"] * (
        times_s - match["nuisance_reference_s"]
    )
    return geometric + nuisance


def _plot_match_trajectories(
    path: Path,
    run: CohortRun,
    tracks: tuple[FinalTrack, ...],
    analyses: tuple[dict[str, Any], ...],
    satellites: tuple[ConeSatellite, ...],
    prediction_times_s: np.ndarray,
    doppler_by_path: dict[str, dict[int, np.ndarray]],
    duration_s: float,
) -> None:
    figure, axes = plt.subplots(3, 2, figsize=(17, 14), sharex="col", squeeze=False)
    colors = ("#d1495b", "#00798c", "#7a5195")
    satellite_by_id = {item.catalog_number: item for item in satellites}
    for row_index in range(3):
        if row_index >= len(tracks):
            for axis in axes[row_index]:
                axis.set_visible(False)
            continue
        track = tracks[row_index]
        analysis = analyses[row_index]
        observations = _track_observations(track)
        cfo_axis, rate_axis = axes[row_index]
        cfo_axis.scatter(
            observations.time_s,
            observations.cfo_hz / 1_000,
            s=14,
            color="#20252b",
            alpha=0.68,
            label="measured CFO observations",
            zorder=5,
        )
        track_times = np.linspace(track.start_s, track.end_s, 400)
        rate_axis.plot(
            track_times,
            _track_rate(track, track_times),
            color="#20252b",
            linewidth=2.4,
            label="measured instantaneous rate",
            zorder=6,
        )
        matches = analysis["trajectory_matches"][:3]
        if not matches:
            for axis in (cfo_axis, rate_axis):
                axis.text(
                    0.5,
                    0.5,
                    "No satellite meets the 10 s / 50% overlap gate",
                    transform=axis.transAxes,
                    ha="center",
                    va="center",
                    color="#59636e",
                )
        for color, match in zip(colors, matches, strict=False):
            satellite = satellite_by_id[match["catalog_number"]]
            times = _candidate_dense_times(track, satellite)
            if not times.size:
                continue
            predicted = doppler_by_path[track.path.label][match["catalog_number"]]
            cfo_axis.plot(
                times,
                _aligned_candidate_cfo(times, match, prediction_times_s, predicted) / 1_000,
                color=color,
                linewidth=1.8,
                label=f"#{match['rank']} {match['object_name']}",
            )
            predicted_rate = np.gradient(predicted, prediction_times_s, edge_order=2)
            rate_axis.plot(
                times,
                np.interp(
                    times + match["epoch_adjustment_s"],
                    prediction_times_s,
                    predicted_rate,
                ),
                color=color,
                linewidth=1.7,
                label=f"#{match['rank']} {match['object_name']}",
            )
            rate_axis.plot(
                [match["overlap_start_s"], match["overlap_end_s"]],
                [match["predicted_linear_rate_hz_s"]] * 2,
                color=color,
                linewidth=1.0,
                linestyle=":",
            )
            rate_axis.plot(
                [match["overlap_start_s"], match["overlap_end_s"]],
                [match["measured_linear_rate_hz_s"]] * 2,
                color="#20252b",
                linewidth=0.9,
                linestyle=":",
                alpha=0.7,
            )
        cfo_axis.set_title(
            f"{track.label} · aligned CFO · {analysis['classification'].replace('_', ' ')}",
            loc="left",
        )
        rate_axis.set_title(f"{track.label} · instantaneous and interval-fitted rates", loc="left")
        for axis in (cfo_axis, rate_axis):
            axis.set_xlim(0, duration_s)
            axis.grid(alpha=0.16)
            handles, labels = axis.get_legend_handles_labels()
            unique = dict(zip(labels, handles, strict=True))
            if unique:
                axis.legend(unique.values(), unique.keys(), fontsize=7, loc="best")
    for axis in axes[:, 0]:
        axis.set_ylabel("receiver CFO (kHz)")
    for axis in axes[:, 1]:
        axis.set_ylabel("Doppler / CFO rate (Hz/s)")
    for axis in axes[-1, :]:
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        f"Top-track TLE trajectory comparisons · {run.session_id}\n"
        "CFO predictions include fitted offset and bounded drift; dotted rates are "
        "same-interval linear fits",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_match_diagnostics(
    path: Path,
    run: CohortRun,
    tracks: tuple[FinalTrack, ...],
    analyses: tuple[dict[str, Any], ...],
    satellites: tuple[ConeSatellite, ...],
    prediction_times_s: np.ndarray,
    doppler_by_path: dict[str, dict[int, np.ndarray]],
    duration_s: float,
) -> None:
    figure, axes = plt.subplots(3, 2, figsize=(17, 14), squeeze=False)
    colors = ("#d1495b", "#00798c", "#7a5195")
    satellite_by_id = {item.catalog_number: item for item in satellites}
    for row_index in range(3):
        if row_index >= len(tracks):
            for axis in axes[row_index]:
                axis.set_visible(False)
            continue
        track = tracks[row_index]
        analysis = analyses[row_index]
        observations = _track_observations(track)
        residual_axis, timing_axis = axes[row_index]
        matches = analysis["trajectory_matches"][:3]
        if not matches:
            for axis in (residual_axis, timing_axis):
                axis.text(
                    0.5,
                    0.5,
                    "No satellite meets the 10 s / 50% overlap gate",
                    transform=axis.transAxes,
                    ha="center",
                    va="center",
                    color="#59636e",
                )
        for color, match in zip(colors, matches, strict=False):
            satellite = satellite_by_id[match["catalog_number"]]
            selected = _segments_mask(observations.time_s, _overlap_segments(track, satellite))
            times = observations.time_s[selected]
            predicted = doppler_by_path[track.path.label][match["catalog_number"]]
            residual = observations.cfo_hz[selected] - _aligned_candidate_cfo(
                times,
                match,
                prediction_times_s,
                predicted,
            )
            residual_axis.plot(
                times,
                residual,
                marker=".",
                markersize=4,
                linewidth=1.0,
                color=color,
                label=f"#{match['rank']} {match['object_name']}",
            )
            profile = match["timing_profile"]
            timing_axis.plot(
                [item["epoch_adjustment_s"] for item in profile],
                [item["train_residual_rms_hz"] for item in profile],
                color=color,
                linewidth=1.5,
                label=f"#{match['rank']} {match['object_name']} · train",
            )
            timing_axis.scatter(
                [match["epoch_adjustment_s"]],
                [match["train_residual_rms_hz"]],
                color=color,
                s=28,
                zorder=5,
            )
        if matches:
            residual_axis.axvspan(
                matches[0]["holdout_start_s"],
                duration_s,
                color="#67717e",
                alpha=0.07,
                label="best-candidate holdout interval",
            )
        residual_axis.axhline(0.0, color="#67717e", linewidth=0.7)
        residual_axis.set_xlim(0, duration_s)
        residual_axis.set_title(f"{track.label} · held-out-auditable CFO residuals", loc="left")
        timing_axis.set_title(f"{track.label} · bounded TLE timing search", loc="left")
        timing_axis.axvline(-EPOCH_SEARCH_S, color="#67717e", linewidth=0.6)
        timing_axis.axvline(EPOCH_SEARCH_S, color="#67717e", linewidth=0.6)
        for axis in (residual_axis, timing_axis):
            axis.grid(alpha=0.16)
            handles, labels = axis.get_legend_handles_labels()
            unique = dict(zip(labels, handles, strict=True))
            if unique:
                axis.legend(unique.values(), unique.keys(), fontsize=7, loc="best")
    for axis in axes[:, 0]:
        axis.set_ylabel("CFO residual (Hz)")
    for axis in axes[:, 1]:
        axis.set_ylabel("training RMS (Hz)")
    axes[-1, 0].set_xlabel("capture time (s)")
    axes[-1, 1].set_xlabel("TLE epoch adjustment (s)")
    figure.suptitle(
        f"Association residual and timing diagnostics · {run.session_id}\n"
        "Markers show train-selected timing optima; held-out RMS remains the ranking metric",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _format_utc(utc_ns: int) -> str:
    return datetime.fromtimestamp(utc_ns / _NS_PER_S, tz=UTC).isoformat(timespec="milliseconds")


def _format_interval(interval: ThresholdInterval) -> str:
    start = f"{interval.start_s:.2f}"
    end = f"{interval.end_s:.2f}"
    return ("≤" if interval.clipped_at_start else "") + start + "–" + end + (
        "≤" if interval.clipped_at_end else ""
    )


def _dwell_document(
    run: CohortRun,
    paths: tuple[PathEvidence, ...],
    archive: TleArchiveReader,
    observer: ObserverSiteV1,
    *,
    provider: str,
    elevation_threshold_deg: float,
    output_root: Path,
) -> dict[str, Any]:
    dwell_start_ns, duration_s = _nominal_capture(paths)
    grid = _grid(dwell_start_ns, duration_s)
    sample_times_s = np.asarray(grid.offsets_s(), dtype=np.float64) + duration_s / 2.0
    snapshot = archive.select_nearest(grid.anchor_utc_ns, provider=provider)
    catalogue = parse_element_sets(archive.read(snapshot))
    observed_tracks = observe_grid(propagate_grid(catalogue, grid), observer, grid)
    satellites = _cone_satellites(
        catalogue,
        observed_tracks,
        sample_times_s,
        elevation_threshold_deg=elevation_threshold_deg,
        anchor_utc_ns=grid.anchor_utc_ns,
    )
    all_tracks = _all_final_tracks(paths, dwell_start_ns)
    capture_doppler_by_path = {
        path.label: {
            satellite.catalog_number: doppler_shift_hz(
                path.rf_frequency_hz,
                observed_tracks.range_rate_km_s[satellite.catalogue_index],
            )
            for satellite in satellites
        }
        for path in paths
    }
    rates_by_path = {
        path.label: _satellite_rates(path, satellites, observed_tracks, sample_times_s)
        for path in paths
    }
    prediction_grid = _grid(
        dwell_start_ns - round(PREDICTION_PADDING_S * _NS_PER_S),
        duration_s + 2.0 * PREDICTION_PADDING_S,
    )
    prediction_times_s = (
        np.asarray(prediction_grid.offsets_s(), dtype=np.float64) + duration_s / 2.0
    )
    prediction_tracks = observe_grid(
        propagate_grid(
            catalogue,
            prediction_grid,
            indices=[item.catalogue_index for item in satellites],
        ),
        observer,
        prediction_grid,
    )
    doppler_by_path = {
        path.label: _satellite_doppler(path, satellites, prediction_tracks) for path in paths
    }
    top_tracks = []
    top_track_objects = all_tracks[:3]
    match_analyses = tuple(
        _analyze_track_matches(
            track,
            satellites,
            prediction_times_s,
            doppler_by_path[track.path.label],
        )
        for track in top_track_objects
    )
    for track, analysis in zip(top_track_objects, match_analyses, strict=True):
        matches = _track_satellite_matches(
            track,
            satellites,
            capture_doppler_by_path[track.path.label],
            sample_times_s,
        )
        top_tracks.append(
            {
                "label": track.label,
                "trajectory_id": track.row.trajectory_id,
                "path": track.path.label,
                "start_s": track.start_s,
                "end_s": track.end_s,
                "duration_s": track.duration_s,
                "observation_count": len(track.row.observation_ids),
                "polynomial_degree": track.row.polynomial_degree,
                "measured_rate_hz_s": _linear_rate_hz_s(
                    track.row.absolute_coefficients_hz
                ),
                "rate_reference_time_s": (
                    _path_offset_s(track.path, dwell_start_ns)
                    + track.row.reference_time_s
                ),
                "replay_tier": track.row.replay_tier.value,
                "automatic_correction_eligible": track.row.automatic_correction_eligible,
                "median_block_corrected_margin": track.row.median_block_corrected_margin,
                "visible_satellites": [item["object_name"] for item in matches],
                "rate_matches": list(matches),
                "matching": analysis,
            }
        )

    stem = run.session_id.removeprefix("cap-")
    raw_name = f"{stem}-raw-glrt-tracks.png"
    final_name = f"{stem}-final-tracks.png"
    overlay_name = f"{stem}-cone-doppler-rate-overlay.png"
    trajectories_name = f"{stem}-tle-match-trajectories.png"
    diagnostics_name = f"{stem}-tle-match-diagnostics.png"
    _plot_raw(output_root / raw_name, run, paths, duration_s, dwell_start_ns)
    _plot_final(
        output_root / final_name,
        run,
        paths,
        all_tracks,
        duration_s,
        dwell_start_ns,
    )
    _plot_overlay(
        output_root / overlay_name,
        run,
        paths,
        all_tracks,
        satellites,
        rates_by_path,
        sample_times_s,
        duration_s,
        dwell_start_ns,
    )
    _plot_match_trajectories(
        output_root / trajectories_name,
        run,
        top_track_objects,
        match_analyses,
        satellites,
        prediction_times_s,
        doppler_by_path,
        duration_s,
    )
    _plot_match_diagnostics(
        output_root / diagnostics_name,
        run,
        top_track_objects,
        match_analyses,
        satellites,
        prediction_times_s,
        doppler_by_path,
        duration_s,
    )

    return {
        "session_id": run.session_id,
        "analysis_run_id": run.run_id,
        "pipeline_release_id": run.pipeline_release_id,
        "capture_start_utc_ns": dwell_start_ns,
        "capture_end_utc_ns": dwell_start_ns + round(duration_s * _NS_PER_S),
        "duration_s": duration_s,
        "snapshot": {
            "provider": snapshot.provider,
            "collected_utc_ns": snapshot.collected_utc_ns,
            "digest": snapshot.digest,
            "byte_size": snapshot.byte_size,
        },
        "catalogue_object_count": len(catalogue),
        "raw_track_count": sum(len(path.raw_table["trajectories"]) for path in paths),
        "final_track_count": len(all_tracks),
        "paths": [
            {
                "label": path.label,
                "scope_digest": path.scope_digest,
                "rf_frequency_hz": path.rf_frequency_hz,
                "raw_track_count": len(path.raw_table["trajectories"]),
                "final_track_count": len(path.final_table.trajectories),
                "raw_product_uri": path.raw_product.logical_uri,
                "raw_product_digest": path.raw_product.digest,
                "dealiased_product_uri": path.dealiased_product.logical_uri,
                "dealiased_product_digest": path.dealiased_product.digest,
                "final_product_uri": path.final_product.logical_uri,
                "final_product_digest": path.final_product.digest,
            }
            for path in paths
        ],
        "cone_satellites": [
            {
                "object_name": satellite.object_name,
                "catalog_number": satellite.catalog_number,
                "peak_elevation_deg": satellite.peak_elevation_deg,
                "element_epoch_utc_ns": satellite.element_epoch_utc_ns,
                "element_age_s": satellite.element_age_s,
                "intervals": [asdict(interval) for interval in satellite.intervals],
            }
            for satellite in satellites
        ],
        "top_tracks": top_tracks,
        "figures": {
            "raw": raw_name,
            "final": final_name,
            "overlay": overlay_name,
            "trajectories": trajectories_name,
            "diagnostics": diagnostics_name,
        },
    }


def _markdown(document: dict[str, Any], figure_relative_root: str) -> str:
    observer = document["observer"]
    classified = [
        (dwell, track)
        for dwell in document["dwells"]
        for track in dwell["top_tracks"]
    ]
    classification_counts = {
        name: sum(track["matching"]["classification"] == name for _, track in classified)
        for name in (
            "stable_candidate_association",
            "trajectory_compatible_candidate",
            "rate_compatible_but_ambiguous",
            "no_compatible_satellite",
        )
    }
    scored = [
        (track["matching"]["primary_gate"]["holdout_residual_rms_hz"], dwell, track)
        for dwell, track in classified
        if track["matching"]["primary_gate"]["holdout_residual_rms_hz"] is not None
    ]
    best_scored = min(scored, key=lambda item: item[0]) if scored else None
    lines = [
        "# Five-dwell GLRT track and zenith-cone TLE report",
        "",
        f"Generated: `{document['generated_utc']}`",
        "",
        "Status: retrospective candidate evidence only; no spacecraft identity is claimed.",
        "",
        "## Reading the report",
        "",
        "For each dwell, the first figure shows the pre-dealias raw GLRT trajectory "
        "fits and the second shows the sealed final retained tracks. The top-three "
        "table ranks final tracks by duration, then observation count, then median "
        "corrected GLRT margin. This is an explicit inspection ordering, not a new "
        "scientific confidence score.",
        "",
        f"A {document['cone_half_angle_deg']:.0f}° cone centered on zenith means "
        f"elevation ≥ {document['elevation_threshold_deg']:.0f}°. The observer is "
        f"the reviewed Sausalito preset ({observer['latitude_deg']:.6f}, "
        f"{observer['longitude_deg']:.6f}, {observer['altitude_m']:.0f} m). "
        "Visibility intervals are clipped to the nominal 60-second capture and "
        "threshold crossings are linearly interpolated from a 0.25-second propagation grid.",
        "",
        "The rate overlay uses **Doppler rate in Hz/s**, not absolute CFO. Unknown "
        "constant receiver/LNB offsets do not affect this derivative. The matching "
        "panels separately compare CFO evolution after fitting only a constant offset "
        "and a bounded linear nuisance drift.",
        "",
        "The black radio curves are the complete derivatives of the sealed linear, "
        "quadratic, or cubic CFO polynomials. For each track–satellite overlap, both "
        "measured and predicted CFO are also reduced to linear slopes over exactly the "
        "same timestamps. This keeps scalar rate comparisons interval matched.",
        "",
        "Full-trajectory matching uses the underlying de-aliased CFO observations. A "
        "small TLE timing adjustment is selected on the earlier 60% of observations, "
        "along with one free CFO offset and a nuisance drift bounded to ±200 Hz/s. "
        "Satellites are ranked by residual RMS on the later, unseen 40%. A stable "
        "candidate must remain best under 50/50, 60/40, and 70/30 splits and a 20% "
        "tighter drift bound; it must also beat the runner-up and ±30-second time controls.",
        "",
        "## Terminology",
        "",
        "| Term | Units | Meaning in this report |",
        "|---|---:|---|",
        "| Doppler shift | Hz | Geometric received-minus-transmitted frequency shift. |",
        "| Doppler rate / Doppler drift | Hz/s | Time derivative of Doppler shift; "
        "approximately constant and negative near closest approach. |",
        "| CFO | Hz | Radio-measured carrier-frequency offset: Doppler plus receiver, "
        "LNB, and transmitter offsets. |",
        "| Reference-time rate | Hz/s | Instantaneous derivative of the sealed radio CFO "
        "polynomial at `reference_time_s`. |",
        "| Interval-fitted rate | Hz/s | Linear slope fitted over the exact common "
        "track–cone interval, computed identically for radio and TLE series. |",
        "| Predicted rate | Hz/s | Numerical time derivative of TLE/SGP4 geometric "
        "Doppler shift at the path's RF center. |",
        "| Linear-rate residual | Hz/s | Signed or absolute difference between the two "
        "interval-fitted slopes. |",
        "| Instantaneous-rate RMS | Hz/s RMS | RMS difference between the complete "
        "measured and predicted rate curves over their overlap. |",
        "| Held-out CFO RMS | Hz | CFO trajectory error on observations not used to fit "
        "timing, frequency offset, or nuisance drift. |",
        "| Nuisance drift | Hz/s | Bounded residual receiver/LNB/transmitter-clock drift; "
        "it is not the geometric Doppler rate. |",
        "| Doppler-rate curvature | Hz/s² | Change in Doppler rate; not plotted as a "
        "radio measurement in the overlay. |",
        "",
        "## Cross-dwell preliminary result",
        "",
        f"Across the {len(classified)} inspected top tracks, "
        f"{classification_counts['stable_candidate_association']} pass every stable-candidate "
        f"gate, {classification_counts['trajectory_compatible_candidate']} are trajectory-"
        "compatible without stability, "
        f"{classification_counts['rate_compatible_but_ambiguous']} are rate-compatible but "
        f"ambiguous, and {classification_counts['no_compatible_satellite']} have no adequate "
        "rate-compatible candidate.",
        "",
    ]
    if best_scored is not None:
        best_rms, best_dwell, best_track = best_scored
        best_gate = best_track["matching"]["primary_gate"]
        lines.extend(
            [
                f"The smallest held-out RMS is {best_rms:.1f} Hz for "
                f"{best_dwell['session_id']} {best_track['label']} against "
                f"{best_gate['best_name']}; it still does not pass the complete gate set. "
                "This report therefore finds no satellite identity in these five dwells.",
                "",
            ]
        )
    for dwell_index, dwell in enumerate(document["dwells"], start=1):
        figures = dwell["figures"]
        lines.extend(
            [
                f"## Dwell {dwell_index}: `{dwell['session_id']}`",
                "",
                f"Sealed run: `{dwell['analysis_run_id']}`",
                "",
                f"Capture: `{_format_utc(dwell['capture_start_utc_ns'])}` to "
                f"`{_format_utc(dwell['capture_end_utc_ns'])}`",
                "",
                f"Inventory: {dwell['raw_track_count']} raw GLRT fits, "
                f"{dwell['final_track_count']} final tracks, "
                f"{len(dwell['cone_satellites'])} Starlink satellites entering the cone.",
                "",
                "### Raw GLRT tracks",
                "",
                f"![Raw GLRT tracks for {dwell['session_id']}]"
                f"({figure_relative_root}/{figures['raw']})",
                "",
                "### Final tracks",
                "",
                f"![Final tracks for {dwell['session_id']}]"
                f"({figure_relative_root}/{figures['final']})",
                "",
                "### Three longest final tracks",
                "",
                "| Track | Path | Interval (s) | Duration | Observations | Degree | "
                "Reference-time rate | Median corrected GLRT | Replay | "
                "Cone satellites during track, "
                "closest rate first |",
                "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for track in dwell["top_tracks"]:
            visible = ", ".join(track["visible_satellites"]) or "none"
            margin = track["median_block_corrected_margin"]
            displayed_start_s = max(0.0, float(track["start_s"]))
            displayed_end_s = min(float(dwell["duration_s"]), float(track["end_s"]))
            lines.append(
                f"| **{track['label']}** `{track['trajectory_id'][7:15]}` | "
                f"{track['path']} | {displayed_start_s:.2f}–{displayed_end_s:.2f} | "
                f"{track['duration_s']:.2f} s | {track['observation_count']} | "
                f"{track['polynomial_degree']} | "
                f"{track['measured_rate_hz_s']:+.1f} Hz/s | "
                f"{'—' if margin is None else f'{margin:.4f}'} | "
                f"{track['replay_tier']} | {visible} |"
            )
        lines.extend(
            [
                "",
                "### Interval-matched scalar rate comparison",
                "",
                "Only satellites overlapping at least 10 seconds and 50% of the measured "
                "track enter these top-three rate tables. Shorter geometric overlaps remain "
                "listed in the cone inventory below.",
                "",
            ]
        )
        for track in dwell["top_tracks"]:
            closest = [item for item in track["rate_matches"] if item["adequate_overlap"]][:3]
            lines.extend(
                [
                    f"#### {track['label']}",
                    "",
                    "| Rank | Satellite | NORAD | Overlap | Measured slope | Predicted slope | "
                    "Signed Δ | Instantaneous RMS |",
                    "|---:|---|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for rank, item in enumerate(closest, start=1):
                lines.append(
                    f"| {rank} | {item['object_name']} | {item['catalog_number']} | "
                    f"{item['overlap_duration_s']:.2f} s ({item['overlap_fraction']:.0%}) | "
                    f"{item['measured_linear_rate_hz_s']:+.1f} Hz/s | "
                    f"{item['predicted_linear_rate_hz_s']:+.1f} Hz/s | "
                    f"{item['signed_linear_rate_difference_hz_s']:+.1f} Hz/s | "
                    f"{item['instantaneous_rate_rms_difference_hz_s']:.1f} Hz/s |"
                )
            if not closest:
                lines.append("| — | No cone overlap | — | — | — | — | — | — |")
            lines.append("")
        lines.extend(
            [
                "### Held-out full-trajectory matching",
                "",
            ]
        )
        for track in dwell["top_tracks"]:
            matching = track["matching"]
            primary = matching["primary_gate"]
            margin_display = (
                "—"
                if primary["margin_to_second_hz"] is None
                else f"{primary['margin_to_second_hz']:.1f} Hz"
            )
            lines.extend(
                [
                    f"#### {track['label']}: `{matching['classification']}`",
                    "",
                    f"Stable winner across sensitivity cases: "
                    f"`{matching['stability']['passed']}`; primary runner-up margin: "
                    f"`{margin_display}`.",
                    "",
                    "Primary gates — "
                    f"held-out RMS: `{primary['holdout_rms_passed']}`; "
                    f"interior timing optimum: `{primary['epoch_interior']}`; "
                    f"runner-up margin: `{primary['runner_up_margin_passed']}`; "
                    f"time controls: `{primary['time_control_passed']}`.",
                    "",
                    "| Rank | Satellite | NORAD | Held-out RMS | Train RMS | Epoch Δt | "
                    "Nuisance drift | Linear-rate Δ | Time-control advantage |",
                    "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for item in matching["trajectory_matches"][:3]:
                control = item["time_control_advantage_hz"]
                lines.append(
                    f"| {item['rank']} | {item['object_name']} | {item['catalog_number']} | "
                    f"{item['holdout_residual_rms_hz']:.1f} Hz | "
                    f"{item['train_residual_rms_hz']:.1f} Hz | "
                    f"{item['epoch_adjustment_s']:+.2f} s | "
                    f"{item['nuisance_drift_hz_s']:+.1f} Hz/s | "
                    f"{item['signed_linear_rate_difference_hz_s']:+.1f} Hz/s | "
                    f"{'—' if control is None else f'{control:+.1f} Hz'} |"
                )
            if not matching["trajectory_matches"]:
                lines.append(
                    "| — | Insufficient ≥10 s / ≥50% cone overlap | — | — | — | — | "
                    "— | — | — |"
                )
            lines.append("")
        lines.extend(
            [
                "",
                "### Satellites inside the 30° zenith cone",
                "",
                "Intervals marked `≤` touch a capture boundary and may continue outside it.",
                "",
                "| Starlink satellite | NORAD | Peak elevation | Visible capture interval(s) | "
                "Visible UTC interval(s) |",
                "|---|---:|---:|---|---|",
            ]
        )
        for satellite in dwell["cone_satellites"]:
            intervals = [ThresholdInterval(**item) for item in satellite["intervals"]]
            relative = "; ".join(_format_interval(item) for item in intervals)
            utc = "; ".join(
                f"{_format_utc(dwell['capture_start_utc_ns'] + round(item.start_s * _NS_PER_S))} "
                f"to {_format_utc(dwell['capture_start_utc_ns'] + round(item.end_s * _NS_PER_S))}"
                for item in intervals
            )
            lines.append(
                f"| {satellite['object_name']} | {satellite['catalog_number']} | "
                f"{satellite['peak_elevation_deg']:.1f}° | {relative} s | {utc} |"
            )
        lines.extend(
            [
                "",
                "### TLE Doppler-rate overlay",
                "",
                f"![TLE and detected Doppler-rate overlay for {dwell['session_id']}]"
                f"({figure_relative_root}/{figures['overlay']})",
                "",
                "Black curves are instantaneous derivatives of all sealed final CFO "
                "polynomials; the heavier labelled curves are T1–T3. The marker identifies "
                "the polynomial reference-time rate. Colored predicted-rate curves are "
                "shown only while the named satellite is inside the cone. Each receiver "
                "panel uses its actual tuned RF center.",
                "",
                "### Top-three trajectory and rate comparisons",
                "",
                f"![Top-three TLE trajectory comparisons for {dwell['session_id']}]"
                f"({figure_relative_root}/{figures['trajectories']})",
                "",
                "Left panels align each candidate's geometric Doppler to the measured CFO "
                "with the fitted offset and bounded nuisance drift. Right panels compare "
                "instantaneous rates; dotted segments are the same-interval linear slopes.",
                "",
                "### Residual and timing-sensitivity diagnostics",
                "",
                f"![TLE match diagnostics for {dwell['session_id']}]"
                f"({figure_relative_root}/{figures['diagnostics']})",
                "",
                "Residual panels retain the observation-level errors for the three best "
                "candidates. Timing panels show the complete ±2.5-second training search; "
                "a boundary optimum is rejected rather than interpreted as an association.",
                "",
            ]
        )
    lines.extend(
        [
            "## Provenance and limits",
            "",
            "All raw and final JSON artifacts were re-read from immutable bulk storage and "
            "verified against their catalog SHA-256 digests. The local TLE reader likewise "
            "re-verifies its selected snapshot. The JSON evidence beside the figures records "
            "every source URI/digest, cone interval, observation-level held-out fit, "
            "timing search, stability case, control result, and rate residual.",
            "",
            f"GPS source: `{document['gps_source']}`. The location is not capture-bound "
            "authority. The nominal first-sample estimate is used for each 60-second plot; "
            "the much wider recorded last-sample uncertainty is not drawn as extra capture "
            "duration. Satellite visibility means geometric TLE visibility within this "
            "zenith cone, not antenna gain, payload activity, or proof that a detected track "
            "came from that spacecraft. The 10-second/50% overlap, 500 Hz held-out RMS, "
            "100 Hz runner-up margin, and 100 Hz time-control advantage are preliminary "
            "diagnostic gates inherited from the legacy experiment, not calibrated false-"
            "identification probabilities for this receiver corpus.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = _arguments()
    if not 0.0 < args.cone_half_angle_deg < 90.0:
        raise ValueError("cone half-angle must be between zero and 90 degrees")
    elevation_threshold_deg = 90.0 - args.cone_half_angle_deg
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    observer = ObserverSiteV1(
        latitude_deg=args.latitude_deg,
        longitude_deg=args.longitude_deg,
        altitude_m=args.altitude_m,
        label="preliminary-sausalito-zenith-cone",
    )
    engine = create_catalog_engine(args.database_url)
    resolver = BulkUriResolver(args.bulk_root, allowed_namespaces=("analysis",), create=False)
    archive = TleArchiveReader(args.tle_root)
    with Session(engine) as database:
        cohort = _cohort(database, tuple(args.session_ids))
        dwells = [
            _dwell_document(
                run,
                _path_evidence(database, resolver, run),
                archive,
                observer,
                provider=args.provider,
                elevation_threshold_deg=elevation_threshold_deg,
                output_root=output_root,
            )
            for run in cohort
        ]
    engine.dispose()
    document = {
        "schema_version": 3,
        "analysis_kind": "five-dwell-standard-glrt-tle-zenith-cone-report",
        "generated_utc": datetime.now(UTC).isoformat(),
        "candidate_only": True,
        "specificity_claimed": False,
        "observer": observer.model_dump(mode="json"),
        "gps_source": args.gps_source,
        "cone_half_angle_deg": args.cone_half_angle_deg,
        "elevation_threshold_deg": elevation_threshold_deg,
        "grid_spacing_s": GRID_SPACING_S,
        "doppler_overlay_quantity": (
            "instantaneous derivative of the sealed radio CFO polynomial versus "
            "time-varying TLE-predicted Doppler rate in hertz per second"
        ),
        "measured_rate_estimator": (
            "complete derivative of the highest-power-first absolute CFO polynomial; "
            "scalar comparisons refit both measured and predicted CFO over the exact overlap"
        ),
        "matching_configuration": {
            "epoch_search_s": EPOCH_SEARCH_S,
            "epoch_step_s": EPOCH_STEP_S,
            "maximum_nuisance_drift_hz_s": MAXIMUM_NUISANCE_DRIFT_HZ_S,
            "maximum_holdout_rms_hz": MAXIMUM_HOLDOUT_RMS_HZ,
            "minimum_runner_up_margin_hz": MINIMUM_RUNNER_UP_MARGIN_HZ,
            "minimum_time_control_advantage_hz": MINIMUM_TIME_CONTROL_ADVANTAGE_HZ,
            "minimum_overlap_s": MINIMUM_OVERLAP_S,
            "minimum_overlap_fraction": MINIMUM_OVERLAP_FRACTION,
            "rate_compatibility_hz_s": RATE_COMPATIBILITY_HZ_S,
            "train_fractions": TRAIN_FRACTIONS,
            "tighter_drift_fraction": TIGHTER_DRIFT_FRACTION,
            "time_control_shifts_s": TIME_CONTROL_SHIFTS_S,
        },
        "dwells": dwells,
    }
    (output_root / "five-dwell-cone-evidence.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    relative_root = os.path.relpath(output_root, start=args.report_path.parent)
    args.report_path.write_text(
        _markdown(document, relative_root),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
