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
from leo.contracts.cfo_dealias import Glrt64FinalTrajectoryTableV3
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
        final_product = by_key.get((scope.id, "standard.glrt64-final-trajectory-table"))
        if raw_product is None or final_product is None:
            raise ValueError(f"path lacks raw or final trajectory evidence: {scope.id}")
        if raw_product.schema_version != 2 or final_product.schema_version != 3:
            raise ValueError(f"path trajectory schema is not V2/V3: {scope.id}")
        raw = _read_verified_json(resolver, raw_product)
        _validate_raw_table(raw)
        final = Glrt64FinalTrajectoryTableV3.model_validate(
            _read_verified_json(resolver, final_product)
        )
        result.append(
            PathEvidence(
                binding=binding,
                scope_digest=scope.canonical_digest,
                raw_table=raw,
                raw_product=raw_product,
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


def _track_rate(track: FinalTrack, sample_times_s: np.ndarray) -> np.ndarray:
    """Repeat one radio-side rate estimate over the track's display support."""

    rate_hz_s = _linear_rate_hz_s(track.row.absolute_coefficients_hz)
    return np.full(sample_times_s.shape, rate_hz_s, dtype=np.float64)


def _track_satellite_matches(
    track: FinalTrack,
    satellites: tuple[ConeSatellite, ...],
    rates: dict[int, np.ndarray],
    sample_times_s: np.ndarray,
) -> tuple[dict[str, Any], ...]:
    detected_rate = _track_rate(track, sample_times_s)
    rows = []
    for satellite in satellites:
        mask = (
            (sample_times_s >= track.start_s)
            & (sample_times_s <= track.end_s)
            & _interval_mask(sample_times_s, satellite.intervals)
        )
        if not np.any(mask):
            continue
        difference = detected_rate[mask] - rates[satellite.catalog_number][mask]
        rows.append(
            {
                "object_name": satellite.object_name,
                "catalog_number": satellite.catalog_number,
                "overlap_start_s": float(sample_times_s[mask][0]),
                "overlap_end_s": float(sample_times_s[mask][-1]),
                "rate_rms_difference_hz_s": float(np.sqrt(np.mean(difference**2))),
            }
        )
    rows.sort(
        key=lambda item: (
            item["rate_rms_difference_hz_s"],
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
                    [rate[0]],
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
        "black segments: radio-side CFO-rate estimate",
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
    rates_by_path = {
        path.label: _satellite_rates(path, satellites, observed_tracks, sample_times_s)
        for path in paths
    }
    top_tracks = []
    for track in all_tracks[:3]:
        matches = _track_satellite_matches(
            track,
            satellites,
            rates_by_path[track.path.label],
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
            }
        )

    stem = run.session_id.removeprefix("cap-")
    raw_name = f"{stem}-raw-glrt-tracks.png"
    final_name = f"{stem}-final-tracks.png"
    overlay_name = f"{stem}-cone-doppler-rate-overlay.png"
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
        },
    }


def _markdown(document: dict[str, Any], figure_relative_root: str) -> str:
    observer = document["observer"]
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
        "The overlay uses **Doppler rate in Hz/s**, not absolute CFO. That is the "
        "quantity that can be overlaid truthfully because these Standard products "
        "declare `uncalibrated_prior`; an unknown constant CFO offset cannot affect a rate.",
        "",
        "For the radio measurement, the report uses the linear coefficient of each "
        "sealed CFO polynomial: the instantaneous CFO rate at its declared reference "
        "time. It is drawn as one horizontal black segment over the track support, with "
        "a black marker at the reference time. The segment is a constant-rate summary, "
        "not the derivative of the polynomial's quadratic or cubic terms.",
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
        "| Measured rate | Hz/s | Linear coefficient of the sealed radio CFO polynomial "
        "at `reference_time_s`; used as the radio-side Doppler-rate proxy. |",
        "| Predicted rate | Hz/s | Numerical time derivative of TLE/SGP4 geometric "
        "Doppler shift at the path's RF center. |",
        "| Rate residual | Hz/s RMS | RMS difference between one measured-rate estimate "
        "and a candidate satellite's predicted rate over their overlapping interval. |",
        "| Doppler-rate curvature | Hz/s² | Change in Doppler rate; not plotted as a "
        "radio measurement in the overlay. |",
        "",
    ]
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
                "Measured rate | Median corrected GLRT | Replay | Cone satellites during track, "
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
                "Closest cone-restricted predicted Doppler rates for each measured rate:",
                "",
            ]
        )
        for track in dwell["top_tracks"]:
            closest = track["rate_matches"][:3]
            summary = ", ".join(
                f"{item['object_name']} ({item['rate_rms_difference_hz_s']:.1f} Hz/s RMS)"
                for item in closest
            )
            lines.append(f"- **{track['label']}**: {summary or 'no cone overlap'}.")
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
                "Black segments are all sealed final detected CFO-rate tracks; dashed black "
                "segments labelled T1–T3 are the three tracks in the table. Each black "
                "segment is one measured rate estimate, and its marker identifies the "
                "polynomial reference time. Colored predicted-rate curves are shown only "
                "while the named satellite is inside the cone. Each receiver panel uses "
                "its actual tuned RF center.",
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
            "every source URI/digest, cone interval, top-track ordering, and rate residual.",
            "",
            f"GPS source: `{document['gps_source']}`. The location is not capture-bound "
            "authority. The nominal first-sample estimate is used for each 60-second plot; "
            "the much wider recorded last-sample uncertainty is not drawn as extra capture "
            "duration. Satellite visibility means geometric TLE visibility within this "
            "zenith cone, not antenna gain, payload activity, or proof that a detected track "
            "came from that spacecraft.",
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
        "schema_version": 2,
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
            "constant radio-side CFO-rate estimate versus time-varying TLE-predicted "
            "Doppler rate in hertz per second"
        ),
        "measured_rate_estimator": (
            "linear coefficient of the highest-power-first absolute CFO polynomial; "
            "instantaneous derivative at reference_time_s"
        ),
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
