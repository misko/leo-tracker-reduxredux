#!/usr/bin/env python3
"""Compare recent sealed Standard CFO trajectories with retrospective TLE Doppler.

This is a read-only research tool.  It selects current, succeeded, live Standard
runs; verifies and validates their final V3 trajectory tables; propagates the
verified local TLE archive; and writes candidate-only evidence outside the
production catalog.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter
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

from leo.acquisition.starlink_tuning import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_rf_center_frequency_hz,
)
from leo.analysis.research.tle_doppler_alignment import (
    ObservedCfoTrajectory,
    PredictedDopplerTrajectory,
    RankedAlignment,
    rank_predictions,
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
from leo.operations.tle_archive import TleArchiveReader, TleSnapshotRef
from leo.sky.doppler import doppler_shift_hz, fit_doppler_polynomial
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import observe_grid
from leo.storage import BulkUriResolver

DEFAULT_DATABASE_URL = "postgresql+psycopg:///leo_tracker"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_TLE_ROOT = Path("/var/lib/leo/tle")
DEFAULT_LATITUDE_DEG = 37.858988
DEFAULT_LONGITUDE_DEG = -122.478103
DEFAULT_ALTITUDE_M = -29.0
DEFAULT_NULL_SHIFTS_S = (-600, -300, 300, 600)
GRID_SPACING_S = 0.5
_NS_PER_S = 1_000_000_000


@dataclass(frozen=True, slots=True)
class CohortRun:
    run_id: str
    session_id: str
    pipeline_release_id: str
    observed_start_at: datetime
    sealed_at: datetime


@dataclass(frozen=True, slots=True)
class StandardPathEvidence:
    binding: StandardPathInputBindV3
    table: Glrt64FinalTrajectoryTableV3
    product_id: int
    product_uri: str
    product_digest: str
    rf_frequency_hz: int

    @property
    def path_id(self) -> str:
        return f"{self.binding.session_id}/{self.binding.stream_id}/rx-{self.binding.receiver_id}"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=DEFAULT_TLE_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dwell-count", type=int, default=5)
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="an exact completed session to analyze; repeatable and ordered",
    )
    parser.add_argument("--provider", default="space-track")
    parser.add_argument("--latitude-deg", type=float, default=DEFAULT_LATITUDE_DEG)
    parser.add_argument("--longitude-deg", type=float, default=DEFAULT_LONGITUDE_DEG)
    parser.add_argument("--altitude-m", type=float, default=DEFAULT_ALTITUDE_M)
    parser.add_argument(
        "--gps-source",
        default="reviewed spinnaker-sausalito preset; not capture-bound GPS authority",
    )
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--rank-limit", type=int, default=5)
    parser.add_argument(
        "--null-shift-s",
        type=int,
        action="append",
        dest="null_shifts_s",
        help="retrospective time shift for chance-alignment controls; repeatable",
    )
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _cohort(
    database: Session,
    limit: int,
    *,
    session_ids: tuple[str, ...] = (),
) -> tuple[CohortRun, ...]:
    if not 1 <= limit <= 100:
        raise ValueError("dwell count must be between one and 100")
    observed = func.coalesce(CaptureSession.observed_start_at, CaptureSession.created_at)
    statement = (
        select(AnalysisRun, CaptureSession, observed)
        .join(CurrentAnalysis, CurrentAnalysis.run_id == AnalysisRun.id)
        .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
        .where(
            AnalysisRun.state == "succeeded",
            AnalysisRun.pipeline_lane == "standard",
            CaptureSession.source_type != "test",
        )
    )
    rows: list[Any]
    if session_ids:
        if len(session_ids) != len(set(session_ids)):
            raise ValueError("exact session IDs must be unique")
        rows = list(database.execute(statement.where(CaptureSession.id.in_(session_ids))).all())
        by_session = {capture.id: (run, capture, start) for run, capture, start in rows}
        missing = [session_id for session_id in session_ids if session_id not in by_session]
        if missing:
            raise ValueError(
                "exact sessions are not current succeeded live Standard analyses: "
                + ", ".join(missing)
            )
        rows = [by_session[session_id] for session_id in session_ids]
        limit = len(session_ids)
    else:
        rows = list(
            database.execute(
                statement.order_by(observed.desc(), CaptureSession.id).limit(limit)
            ).all()
        )
    result = []
    for run, _capture, observed_start in rows:
        if run.sealed_at is None:
            raise ValueError(f"succeeded run is not sealed: {run.id}")
        result.append(
            CohortRun(
                run_id=run.id,
                session_id=run.session_id,
                pipeline_release_id=run.pipeline_release_id,
                observed_start_at=observed_start,
                sealed_at=run.sealed_at,
            )
        )
    if len(result) != limit:
        raise ValueError(f"requested {limit} completed dwells but resolved {len(result)}")
    return tuple(result)


def _path_evidence(
    database: Session,
    resolver: BulkUriResolver,
    run: CohortRun,
) -> tuple[StandardPathEvidence, ...]:
    binding_rows = database.execute(
        select(RunSubjectBinding, AnalysisScope)
        .join(AnalysisScope, AnalysisScope.id == RunSubjectBinding.scope_id)
        .where(
            RunSubjectBinding.run_id == run.run_id,
            AnalysisScope.kind == "receiver_path",
        )
        .order_by(AnalysisScope.stream_id, AnalysisScope.receiver_id)
    ).all()
    product_rows = database.execute(
        select(AnalysisProduct, AnalysisScope)
        .join(AnalysisScope, AnalysisScope.id == AnalysisProduct.scope_id)
        .where(
            AnalysisProduct.run_id == run.run_id,
            AnalysisProduct.kind == "standard.glrt64-final-trajectory-table",
            AnalysisProduct.schema_version == 3,
            AnalysisProduct.available.is_(True),
        )
    ).all()
    products = {scope.id: product for product, scope in product_rows}
    if len(products) != len(product_rows):
        raise ValueError(f"run has duplicate final trajectory products: {run.run_id}")

    result = []
    for registration, scope in binding_rows:
        binding = StandardPathInputBindV3.model_validate(registration.document)
        product = products.get(scope.id)
        if product is None:
            raise ValueError(f"path lacks a final V3 trajectory table: {scope.canonical_digest}")
        path = resolver.resolve(product.logical_uri)
        payload = path.read_bytes()
        observed_digest = _sha256(payload)
        if observed_digest != product.digest:
            raise ValueError(
                f"trajectory product digest mismatch for {product.logical_uri}: "
                f"{observed_digest} != {product.digest}"
            )
        table = Glrt64FinalTrajectoryTableV3.model_validate_json(payload)
        expected_rf_frequency_hz = starlink_edge_rf_center_frequency_hz(
            binding.starlink_channel,
            binding.starlink_edge,
        )
        rf_frequency_hz = binding.tuned_center_frequency_hz + STARLINK_LNB_LO_HZ
        if abs(rf_frequency_hz - expected_rf_frequency_hz) > 10:
            raise ValueError(f"path tuning does not close to RF: {scope.canonical_digest}")
        result.append(
            StandardPathEvidence(
                binding=binding,
                table=table,
                product_id=product.id,
                product_uri=product.logical_uri,
                product_digest=product.digest,
                rf_frequency_hz=rf_frequency_hz,
            )
        )
    if set(products) != {scope.id for _, scope in binding_rows}:
        raise ValueError(
            f"run final trajectory inventory differs from its path bindings: {run.run_id}"
        )
    return tuple(result)


def _sampling_grid(start_utc_ns: int, end_utc_ns: int, *, shift_s: int = 0) -> SamplingGrid:
    if end_utc_ns <= start_utc_ns:
        raise ValueError("prediction interval must be positive")
    anchor = (start_utc_ns + end_utc_ns) // 2
    half_span_ns = max(anchor - start_utc_ns, end_utc_ns - anchor)
    step_ns = round(GRID_SPACING_S * _NS_PER_S)
    per_side = max(1, math.ceil(half_span_ns / step_ns))
    shifted_anchor = anchor + shift_s * _NS_PER_S
    instants = tuple(
        shifted_anchor + (index - per_side) * step_ns for index in range(2 * per_side + 1)
    )
    return SamplingGrid(instants, per_side, GRID_SPACING_S)


def _predictions(
    catalogue: ElementSetCatalogue,
    observer: ObserverSiteV1,
    *,
    start_utc_ns: int,
    end_utc_ns: int,
    rf_frequencies_hz: tuple[int, ...],
    horizon_mask_deg: float,
    shift_s: int = 0,
) -> dict[int, tuple[PredictedDopplerTrajectory, ...]]:
    shifted_grid = _sampling_grid(start_utc_ns, end_utc_ns, shift_s=shift_s)
    propagated = propagate_grid(catalogue, shifted_grid)
    tracks = observe_grid(propagated, observer, shifted_grid)
    margin_deg = MAX_ANGULAR_RATE_DEG_S * shifted_grid.spacing_s / 2.0
    plausible = tracks.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    possible = (
        tracks.usable
        & plausible
        & (tracks.elevation_deg.max(axis=1) > horizon_mask_deg - margin_deg)
    )
    indices = np.flatnonzero(possible)
    offsets_s = np.asarray(shifted_grid.offsets_s(), dtype=np.float64)
    unshifted_reference_ns = shifted_grid.anchor_utc_ns - shift_s * _NS_PER_S
    epochs = catalogue.element_epoch_utc_ns()
    result: dict[int, tuple[PredictedDopplerTrajectory, ...]] = {}
    for frequency_hz in rf_frequencies_hz:
        rows = []
        for index in indices:
            row = int(index)
            shift_hz = doppler_shift_hz(frequency_hz, tracks.range_rate_km_s[row])
            polynomial = fit_doppler_polynomial(
                offsets_s,
                shift_hz,
                downlink_frequency_hz=frequency_hz,
                reference_utc_ns=unshifted_reference_ns,
            )
            peak = float(tracks.elevation_deg[row].max())
            epoch_ns = epochs[row]
            rows.append(
                PredictedDopplerTrajectory(
                    object_name=catalogue.names[row][:64],
                    catalog_number=catalogue.satellite_numbers[row],
                    reference_utc_ns=unshifted_reference_ns,
                    start_utc_ns=start_utc_ns,
                    end_utc_ns=end_utc_ns,
                    frequency_at_reference_hz=polynomial.frequency_at_reference_hz,
                    slope_hz_s=polynomial.slope_hz_s,
                    acceleration_hz_s2=polynomial.acceleration_hz_s2,
                    jerk_hz_s3=polynomial.jerk_hz_s3,
                    element_epoch_utc_ns=epoch_ns,
                    element_age_s=abs(shifted_grid.anchor_utc_ns - epoch_ns) / 1e9,
                    peak_elevation_deg=peak,
                    boundary_uncertain=peak <= horizon_mask_deg + margin_deg,
                )
            )
        result[frequency_hz] = tuple(sorted(rows, key=lambda item: item.catalog_number))
    return result


def _observed(path: StandardPathEvidence) -> tuple[ObservedCfoTrajectory, ...]:
    timing = path.binding.timing
    return tuple(
        ObservedCfoTrajectory(
            trajectory_id=item.trajectory_id,
            path_id=path.path_id,
            polynomial_degree=item.polynomial_degree,
            reference_time_s=item.reference_time_s,
            coefficients_hz=item.absolute_coefficients_hz,
            start_s=item.start_s,
            end_s=item.end_s,
            first_estimate_utc_ns=timing.first_estimate_utc_ns,
            first_earliest_utc_ns=timing.first_earliest_utc_ns,
            first_latest_utc_ns=timing.first_latest_utc_ns,
        )
        for item in path.table.trajectories
    )


def _snapshot_document(snapshot: TleSnapshotRef) -> dict[str, Any]:
    return {
        "provider": snapshot.provider,
        "collected_utc_ns": snapshot.collected_utc_ns,
        "digest": snapshot.digest,
        "byte_size": snapshot.byte_size,
    }


def _ranking_document(item: RankedAlignment) -> dict[str, Any]:
    return {
        "rank": item.rank,
        "prediction": asdict(item.prediction),
        "nominal": asdict(item.nominal),
        "earliest_score": item.earliest_score,
        "latest_score": item.latest_score,
        "best_timing_score": item.best_timing_score,
        "worst_timing_score": item.worst_timing_score,
    }


def _analyze_dwell(
    run: CohortRun,
    paths: tuple[StandardPathEvidence, ...],
    archive: TleArchiveReader,
    observer: ObserverSiteV1,
    *,
    provider: str,
    horizon_mask_deg: float,
    rank_limit: int,
    null_shifts_s: tuple[int, ...],
) -> dict[str, Any]:
    start_ns = min(item.binding.timing.first_earliest_utc_ns for item in paths)
    end_ns = max(item.binding.timing.last_latest_utc_ns for item in paths)
    anchor_ns = (start_ns + end_ns) // 2
    snapshot = archive.select_nearest(anchor_ns, provider=provider)
    catalogue = parse_element_sets(archive.read(snapshot))
    frequencies = tuple(sorted({item.rf_frequency_hz for item in paths}))
    primary = _predictions(
        catalogue,
        observer,
        start_utc_ns=start_ns,
        end_utc_ns=end_ns,
        rf_frequencies_hz=frequencies,
        horizon_mask_deg=horizon_mask_deg,
    )
    null_sets = {
        shift: _predictions(
            catalogue,
            observer,
            start_utc_ns=start_ns,
            end_utc_ns=end_ns,
            rf_frequencies_hz=frequencies,
            horizon_mask_deg=horizon_mask_deg,
            shift_s=shift,
        )
        for shift in null_shifts_s
    }

    tracks = []
    for path in paths:
        for observed in _observed(path):
            ranking = rank_predictions(
                observed,
                primary[path.rf_frequency_hz],
                limit=rank_limit,
            )
            if not ranking:
                raise ValueError(
                    f"no TLE candidate overlaps observed track {observed.trajectory_id}"
                )
            null_scores = {}
            for shift, by_frequency in null_sets.items():
                shifted = rank_predictions(
                    observed,
                    by_frequency[path.rf_frequency_hz],
                    limit=1,
                )
                null_scores[str(shift)] = (
                    None if not shifted else shifted[0].nominal.comparison_score
                )
            real_score = ranking[0].nominal.comparison_score
            finite_null = [float(value) for value in null_scores.values() if value is not None]
            tracks.append(
                {
                    "path_id": path.path_id,
                    "stream_id": path.binding.stream_id,
                    "radio_id": path.binding.radio_id,
                    "receiver_id": path.binding.receiver_id,
                    "physical_receiver_id": path.binding.physical_receiver_id,
                    "starlink_channel": path.binding.starlink_channel,
                    "starlink_edge": path.binding.starlink_edge.value,
                    "rf_frequency_hz": path.rf_frequency_hz,
                    "frequency_reference": path.binding.frequency_reference.reference.value,
                    "trajectory_id": observed.trajectory_id,
                    "trajectory_start_s": observed.start_s,
                    "trajectory_end_s": observed.end_s,
                    "trajectory_degree": observed.polynomial_degree,
                    "product_id": path.product_id,
                    "product_uri": path.product_uri,
                    "product_digest": path.product_digest,
                    "observed": asdict(observed),
                    "rankings": [_ranking_document(item) for item in ranking],
                    "top_two_score_margin": (
                        None
                        if len(ranking) < 2
                        else ranking[1].nominal.comparison_score - real_score
                    ),
                    "null_best_scores": null_scores,
                    "real_better_than_null_count": sum(real_score < value for value in finite_null),
                    "null_comparison_count": len(finite_null),
                }
            )

    return {
        "session_id": run.session_id,
        "analysis_run_id": run.run_id,
        "pipeline_release_id": run.pipeline_release_id,
        "observed_start_at": run.observed_start_at.isoformat(),
        "sealed_at": run.sealed_at.isoformat(),
        "prediction_start_utc_ns": start_ns,
        "prediction_end_utc_ns": end_ns,
        "snapshot": _snapshot_document(snapshot),
        "catalogue_object_count": len(catalogue),
        "possible_prediction_counts": {
            str(frequency): len(primary[frequency]) for frequency in frequencies
        },
        "path_count": len(paths),
        "observed_track_count": len(tracks),
        "tracks": tracks,
    }


def _flatten_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for dwell in document["dwells"]:
        for track in dwell["tracks"]:
            for candidate in track["rankings"]:
                prediction = candidate["prediction"]
                nominal = candidate["nominal"]
                rows.append(
                    {
                        "session_id": dwell["session_id"],
                        "analysis_run_id": dwell["analysis_run_id"],
                        "pipeline_release_id": dwell["pipeline_release_id"],
                        "path_id": track["path_id"],
                        "trajectory_id": track["trajectory_id"],
                        "rf_frequency_hz": track["rf_frequency_hz"],
                        "rank": candidate["rank"],
                        "catalog_number": prediction["catalog_number"],
                        "object_name": prediction["object_name"],
                        "peak_elevation_deg": prediction["peak_elevation_deg"],
                        "element_age_s": prediction["element_age_s"],
                        "boundary_uncertain": prediction["boundary_uncertain"],
                        "comparison_score": nominal["comparison_score"],
                        "detrended_frequency_rms_hz": nominal["detrended_frequency_rms_hz"],
                        "slope_rms_difference_hz_s": nominal["slope_rms_difference_hz_s"],
                        "acceleration_rms_difference_hz_s2": nominal[
                            "acceleration_rms_difference_hz_s2"
                        ],
                        "jerk_rms_difference_hz_s3": nominal["jerk_rms_difference_hz_s3"],
                        "best_timing_score": candidate["best_timing_score"],
                        "worst_timing_score": candidate["worst_timing_score"],
                        "top_two_score_margin": track["top_two_score_margin"],
                        "real_better_than_null_count": track["real_better_than_null_count"],
                        "null_comparison_count": track["null_comparison_count"],
                    }
                )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("alignment result has no candidate rows")
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _plot_overview(path: Path, document: dict[str, Any]) -> None:
    dwells = document["dwells"]
    figure, axes = plt.subplots(len(dwells), 1, figsize=(15, 3.2 * len(dwells)), squeeze=False)
    for axis, dwell in zip(axes[:, 0], dwells, strict=True):
        real = np.asarray(
            [track["rankings"][0]["nominal"]["comparison_score"] for track in dwell["tracks"]]
        )
        null = np.asarray(
            [
                np.median(
                    [value for value in track["null_best_scores"].values() if value is not None]
                )
                for track in dwell["tracks"]
            ]
        )
        positions = np.arange(real.size)
        axis.scatter(positions, real, color="#2368a2", s=28, label="correct dwell UTC")
        axis.scatter(positions, null, color="#d1495b", marker="x", s=36, label="null median")
        axis.set_yscale("symlog", linthresh=1.0)
        axis.set_ylabel("shape score")
        axis.set_title(
            f"{dwell['session_id']} · {dwell['observed_track_count']} heard tracks · "
            f"{max(dwell['possible_prediction_counts'].values())} possible TLE tracks",
            loc="left",
        )
        axis.grid(alpha=0.18)
        axis.legend(loc="upper right", fontsize=8)
    axes[-1, 0].set_xlabel("sealed Standard trajectory index")
    figure.suptitle(
        "Retrospective TLE–Doppler shape alignment\n"
        "Lower is better · one CFO intercept removed · candidate-only evidence"
    )
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _markdown(document: dict[str, Any]) -> str:
    all_tracks = [track for dwell in document["dwells"] for track in dwell["tracks"]]
    best_scores = np.asarray(
        [track["rankings"][0]["nominal"]["comparison_score"] for track in all_tracks]
    )
    null_wins = np.asarray(
        [
            track["real_better_than_null_count"] == track["null_comparison_count"]
            for track in all_tracks
        ]
    )
    top_objects = Counter(track["rankings"][0]["prediction"]["object_name"] for track in all_tracks)
    narrow_margins = sum(
        track["top_two_score_margin"] <= 0.05 * track["rankings"][0]["nominal"]["comparison_score"]
        for track in all_tracks
    )
    lines = [
        f"# Preliminary TLE–Doppler alignment for {len(document['dwells'])} "
        "completed Standard dwells",
        "",
        "Status: candidate-only retrospective research evidence; no satellite identity is claimed.",
        "",
        "## Method",
        "",
        "The analysis validates each sealed `standard.glrt64-final-trajectory-table.v3` "
        "artifact, propagates the verified local Space-Track snapshot over the capture "
        "interval, retains a conservative horizon-visible candidate set, removes one "
        "constant CFO intercept, and ranks slope/acceleration/jerk agreement. "
        f"{len(document['null_shifts_s'])} shifted-time prediction sets "
        f"({', '.join(str(value) + ' s' for value in document['null_shifts_s'])}) provide "
        "a chance-alignment control.",
        "",
        "## Cohort summary",
        "",
        "| Session | Release | Heard tracks | Possible TLE tracks | "
        "Median best score | Better than every null |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for dwell in document["dwells"]:
        tracks = dwell["tracks"]
        scores = [item["rankings"][0]["nominal"]["comparison_score"] for item in tracks]
        decisive = sum(
            item["real_better_than_null_count"] == item["null_comparison_count"] for item in tracks
        )
        lines.append(
            f"| `{dwell['session_id']}` | `{dwell['pipeline_release_id'][:9]}` | "
            f"{len(tracks)} | {max(dwell['possible_prediction_counts'].values())} | "
            f"{np.median(scores):.2f} | {decisive}/{len(tracks)} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate observations",
            "",
            f"- {len(all_tracks)} replay-retained Standard trajectories were compared.",
            f"- The median nearest-candidate shape score is {np.median(best_scores):.2f}.",
            f"- {int(null_wins.sum())}/{len(all_tracks)} tracks beat all shifted-time "
            "null candidates.",
            f"- {narrow_margins}/{len(all_tracks)} tracks have a runner-up within 5% of "
            "the best score, so nearest-candidate specificity is often weak.",
            "- Most frequent nearest candidates: "
            + ", ".join(f"{name} ({count})" for name, count in top_objects.most_common(8))
            + ".",
            "",
            "## Interpretation limits",
            "",
            "The receiver products use `uncalibrated_prior`, so absolute CFO intercepts are "
            "excluded. The GPS position is an explicitly labelled input rather than capture-"
            "bound authority. A large visible-satellite inventory creates a substantial chance-"
            "match floor; the shifted-time controls and top-two margins must accompany every "
            "candidate. These results should guide the next calibration and beam-pointing step, "
            "not yet populate the production TLE-association field.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = _arguments()
    null_shifts = tuple(sorted(set(args.null_shifts_s or DEFAULT_NULL_SHIFTS_S)))
    if any(value == 0 for value in null_shifts):
        raise ValueError("zero is the primary prediction, not a null shift")
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)
    engine = create_catalog_engine(args.database_url)
    resolver = BulkUriResolver(
        args.bulk_root,
        allowed_namespaces=("analysis",),
        create=False,
    )
    archive = TleArchiveReader(args.tle_root)
    observer = ObserverSiteV1(
        latitude_deg=args.latitude_deg,
        longitude_deg=args.longitude_deg,
        altitude_m=args.altitude_m,
        label="preliminary-tle-doppler-observer",
    )
    with Session(engine) as database:
        cohort = _cohort(
            database,
            args.dwell_count,
            session_ids=tuple(args.session_ids or ()),
        )
        dwells = [
            _analyze_dwell(
                run,
                _path_evidence(database, resolver, run),
                archive,
                observer,
                provider=args.provider,
                horizon_mask_deg=args.horizon_mask_deg,
                rank_limit=args.rank_limit,
                null_shifts_s=null_shifts,
            )
            for run in cohort
        ]
    engine.dispose()
    document = {
        "schema_version": 1,
        "analysis_kind": "preliminary-tle-doppler-alignment",
        "generated_utc": datetime.now(UTC).isoformat(),
        "candidate_only": True,
        "specificity_claimed": False,
        "comparison_basis": "constant-intercept-removed slope-acceleration-jerk shape",
        "grid_spacing_s": GRID_SPACING_S,
        "horizon_candidate_margin_deg": MAX_ANGULAR_RATE_DEG_S * GRID_SPACING_S / 2.0,
        "observer": observer.model_dump(mode="json"),
        "gps_source": args.gps_source,
        "provider": args.provider,
        "null_shifts_s": list(null_shifts),
        "dwells": dwells,
    }
    rows = _flatten_rows(document)
    (output / "tle-doppler-alignment.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(output / "tle-doppler-candidates.csv", rows)
    _plot_overview(output / "tle-doppler-overview.png", document)
    (output / "README.md").write_text(_markdown(document), encoding="utf-8")


if __name__ == "__main__":
    main()
