#!/usr/bin/env python3
"""Rebuild a multi-dwell radio/TLE review with degree-1 radio models only.

This is a read-only retrospective tool.  It starts from the independently
scored candidates in each sealed ``standard.pilot-scan`` product, constructs a
fresh trajectory bank whose only permitted degree is one, and selects family
representatives from that bank.  It deliberately does not read membership from
the persisted raw, de-aliased, replay, or final trajectory products.

The selected tracks are not presented as Standard-pipeline final products:
replaying IQ and applying the published de-alias gates would create new
products outside this report-only rerun.  They are the strictly linear family
representatives used for the downstream scalar-rate/TLE comparison here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.acquisition.starlink_tuning import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_rf_center_frequency_hz,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankConfig,
    TrajectoryObservation,
    default_trajectory_bank_config,
    fit_trajectory_bank,
)
from leo.analysis.starlink.trajectory_feedback import (
    select_trajectory_representatives,
    trajectory_observations,
)
from leo.catalog.database import create_catalog_engine
from leo.catalog.models import AnalysisProduct, AnalysisScope, RunSubjectBinding
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.screening import observe_grid
from leo.storage import BulkUriResolver

try:
    from tools import report_five_dwell_tle_cone as base
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
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
DEFAULT_T1_SUMMARY = Path(
    "reports/figures/2026_08_21_t1_dense_degree1_only/t1-dense-degree1-summary.json"
)


@dataclass(frozen=True, slots=True)
class SelectedLinearTrack:
    label: str
    path: PathEvidence
    trajectory: PolynomialTrajectory
    observations: tuple[TrajectoryObservation, ...]
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def rate_hz_s(self) -> float:
        return float(self.trajectory.coefficients_hz[0])


@dataclass(frozen=True, slots=True)
class PathEvidence:
    """Only the current path evidence used by the strict-linear refit."""

    binding: StandardPathInputBindV3
    scope_digest: str
    pilot_scan: dict[str, Any]
    pilot_scan_product: AnalysisProduct
    rf_frequency_hz: int

    @property
    def label(self) -> str:
        return f"{self.binding.stream_id}/RX{self.binding.receiver_id}"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_DATABASE_URL", base.DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--bulk-root", type=Path, default=base.DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=base.DEFAULT_TLE_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--report-alias", type=Path, action="append", default=[])
    parser.add_argument("--t1-summary", type=Path, default=DEFAULT_T1_SUMMARY)
    parser.add_argument("--session-id", action="append", dest="session_ids", default=[])
    parser.add_argument("--provider", default="space-track")
    parser.add_argument("--horizon-deg", type=float, default=base.DEFAULT_HORIZON_DEG)
    parser.add_argument("--maximum-selected-per-path", type=int, default=16)
    return parser.parse_args()


def degree1_only_config() -> TrajectoryBankConfig:
    """Return the published trajectory settings with d2/d3 disabled."""

    return replace(default_trajectory_bank_config(), polynomial_degrees=(1,))


def _git_revision(ref: str = "main") -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd()}", "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _path_evidence(
    database: Session,
    resolver: BulkUriResolver,
    run: base.CohortRun,
) -> tuple[PathEvidence, ...]:
    """Load only the current V3 pilot scan and immutable path binding.

    The strict degree-1 report intentionally does not depend on the evolving
    de-aliased/final product schemas because their membership is excluded from
    the refit.
    """

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
            AnalysisProduct.kind == "standard.pilot-scan",
            AnalysisProduct.schema_version == 3,
            AnalysisProduct.available.is_(True),
        )
    ).all()
    by_scope: dict[int, AnalysisProduct] = {}
    for product, scope in products:
        if scope.id in by_scope:
            raise ValueError(f"duplicate pilot-scan product for scope {scope.id}")
        by_scope[scope.id] = product
    result = []
    for registration, scope in bindings:
        product = by_scope.get(scope.id)
        if product is None:
            raise ValueError(f"path lacks a current pilot-scan V3 product: {scope.id}")
        binding = StandardPathInputBindV3.model_validate(registration.document)
        pilot_scan = base._read_verified_json(resolver, product)
        if pilot_scan.get("schema_version") != 3:
            raise ValueError(f"path pilot scan has an unexpected schema: {scope.id}")
        result.append(
            PathEvidence(
                binding=binding,
                scope_digest=scope.canonical_digest,
                pilot_scan=pilot_scan,
                pilot_scan_product=product,
                rf_frequency_hz=binding.tuned_center_frequency_hz + STARLINK_LNB_LO_HZ,
            )
        )
    if len(result) != 4:
        raise ValueError(f"expected four receiver paths for {run.session_id}, found {len(result)}")
    return tuple(
        sorted(result, key=lambda item: (item.binding.stream_id, item.binding.receiver_id))
    )


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _score(value: dict[str, Any]) -> PilotMethodScore:
    return PilotMethodScore(
        PilotMethod(value["method"]),
        float(value["exact_score"]),
        None if value["control_score"] is None else float(value["control_score"]),
        float(value["margin"]),
        float(value["residual_cfo_hz"]),
        float(value["tracking_cfo_hz"]),
    )


def _candidate(value: dict[str, Any]) -> PilotMethodCandidate:
    return PilotMethodCandidate(
        int(value["rank"]),
        int(value["local_epoch_sample"]),
        float(value["acquired_cfo_hz"]),
        tuple(_score(item) for item in value["scores"]),
        value["qam_accuracy"],
        value["qam_evm"],
    )


def pilot_detections(document: dict[str, Any]) -> tuple[PilotProbeDetection, ...]:
    if document.get("schema_version") != 3:
        raise ValueError("linear-only rerun requires a Standard pilot-scan V3 product")
    return tuple(
        PilotProbeDetection(
            NumericalStatus(item["status"]),
            int(item["sample_start"]),
            float(item["time_s"]),
            item["local_epoch_sample"],
            item["acquired_cfo_hz"],
            tuple(_score(value) for value in item["scores"]),
            item["qam_accuracy"],
            item["qam_evm"],
            str(item["reason"]),
            int(item["source_candidate_count"]),
            int(item["truncated_candidate_count"]),
            tuple(_candidate(value) for value in item["candidates"]),
        )
        for item in document["detections"]
    )


def fit_path_degree1_only(
    path: PathEvidence,
    *,
    maximum_selected: int,
) -> tuple[
    tuple[TrajectoryObservation, ...],
    tuple[PolynomialTrajectory, ...],
    tuple[PolynomialTrajectory, ...],
    str,
]:
    """Fit and select tracks without consulting any persisted trajectory bank."""

    detections = pilot_detections(path.pilot_scan)
    observations = trajectory_observations(detections)
    config = degree1_only_config()
    bank = fit_trajectory_bank(observations, config)
    selected = tuple(
        trajectory for _, trajectory in select_trajectory_representatives(bank, maximum_selected)
    )
    assert_degree1_only(bank.trajectories, selected)
    return observations, bank.trajectories, selected, config.digest


def assert_degree1_only(*collections: tuple[PolynomialTrajectory, ...]) -> None:
    degrees = {item.polynomial_degree for values in collections for item in values}
    if degrees - {1}:
        raise AssertionError(f"nonlinear radio model escaped linear-only gate: {degrees}")


def _selected_tracks(
    paths: tuple[PathEvidence, ...],
    dwell_start_ns: int,
    *,
    maximum_selected: int,
) -> tuple[
    tuple[SelectedLinearTrack, ...],
    dict[str, tuple[PolynomialTrajectory, ...]],
    dict[str, tuple[TrajectoryObservation, ...]],
    str,
]:
    candidates: list[
        tuple[PathEvidence, PolynomialTrajectory, tuple[TrajectoryObservation, ...]]
    ] = []
    raw_by_path = {}
    observations_by_path = {}
    config_digest = None
    for path in paths:
        observations, raw, selected, digest = fit_path_degree1_only(
            path, maximum_selected=maximum_selected
        )
        config_digest = config_digest or digest
        if digest != config_digest:
            raise AssertionError("linear-only trajectory configuration changed between paths")
        raw_by_path[path.label] = raw
        observations_by_path[path.label] = observations
        by_id = {item.observation_id: item for item in observations}
        for trajectory in selected:
            candidates.append(
                (
                    path,
                    trajectory,
                    tuple(by_id[item] for item in trajectory.observation_ids),
                )
            )
    candidates.sort(
        key=lambda item: (
            -(item[1].end_s - item[1].start_s),
            -item[1].point_count,
            item[1].residual_rms_hz,
            item[0].label,
            item[1].trajectory_id,
        )
    )
    result = []
    for index, (path, trajectory, observations) in enumerate(candidates, start=1):
        offset = base._path_offset_s(path, dwell_start_ns)
        result.append(
            SelectedLinearTrack(
                f"T{index}",
                path,
                trajectory,
                observations,
                offset + trajectory.start_s,
                offset + trajectory.end_s,
            )
        )
    return tuple(result), raw_by_path, observations_by_path, str(config_digest)


def _match(
    track: SelectedLinearTrack,
    catalogue,
    observer: ObserverSiteV1,
    dwell_start_ns: int,
    horizon_deg: float,
) -> dict[str, Any]:
    midpoint_s = (track.start_s + track.end_s) / 2.0
    midpoint_ns = dwell_start_ns + round(midpoint_s * base._NS_PER_S)
    evaluations = base._sky_rate_evaluations(
        catalogue,
        observer,
        track_midpoint_utc_ns=midpoint_ns,
        rf_frequency_hz=track.path.rf_frequency_hz,
        horizon_deg=horizon_deg,
        shifts_s=base._null_shifts_s(),
    )
    controls = []
    true_ranked = None
    for evaluation in evaluations:
        ranked = sorted(
            (
                {
                    **satellite,
                    "signed_rate_error_hz_s": track.rate_hz_s - satellite["predicted_rate_hz_s"],
                    "absolute_rate_error_hz_s": abs(
                        track.rate_hz_s - satellite["predicted_rate_hz_s"]
                    ),
                }
                for satellite in evaluation["satellites"]
            ),
            key=lambda item: (item["absolute_rate_error_hz_s"], item["catalog_number"]),
        )
        if not ranked:
            raise ValueError("TLE screen returned no visible satellite")
        summary = {
            "time_shift_s": evaluation["time_shift_s"],
            "visible_satellite_count": len(ranked),
            "best_absolute_rate_error_hz_s": ranked[0]["absolute_rate_error_hz_s"],
            "within_500_hz_s": sum(item["absolute_rate_error_hz_s"] <= 500.0 for item in ranked),
            "within_1000_hz_s": sum(item["absolute_rate_error_hz_s"] <= 1_000.0 for item in ranked),
        }
        if evaluation["time_shift_s"] == 0.0:
            true_ranked = ranked
            true_summary = summary
        else:
            controls.append(summary)
    if true_ranked is None:
        raise AssertionError("true-time TLE evaluation is absent")
    null_errors = np.asarray(
        [item["best_absolute_rate_error_hz_s"] for item in controls], dtype=float
    )
    true_error = float(true_ranked[0]["absolute_rate_error_hz_s"])
    return {
        "method": "legacy_midpoint_two_second_secant",
        "track_midpoint_s": midpoint_s,
        "track_midpoint_utc_ns": midpoint_ns,
        "measured_rate_hz_s": track.rate_hz_s,
        "visible_satellite_count": true_summary["visible_satellite_count"],
        "matches_within_500_hz_s": true_summary["within_500_hz_s"],
        "matches_within_1000_hz_s": true_summary["within_1000_hz_s"],
        "best_absolute_rate_error_hz_s": true_error,
        "top_candidates": true_ranked[:5],
        "null_controls": controls,
        "null_control_count": len(controls),
        "true_time_rank_among_true_and_null": int(1 + np.count_nonzero(null_errors < true_error)),
        "true_time_empirical_p": float(
            (1 + np.count_nonzero(null_errors <= true_error)) / (1 + len(null_errors))
        ),
    }


def _plot_track_bank(
    destination: Path,
    run: base.CohortRun,
    paths: tuple[PathEvidence, ...],
    trajectories_by_path: dict[str, tuple[PolynomialTrajectory, ...]],
    observations_by_path: dict[str, tuple[TrajectoryObservation, ...]],
    duration_s: float,
    dwell_start_ns: int,
    *,
    title: str,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(17, 10), sharex=True, sharey=True)
    by_path = {item.label: item for item in paths}
    for axis, label in zip(axes.flat, sorted(by_path), strict=True):
        path = by_path[label]
        offset = base._path_offset_s(path, dwell_start_ns)
        observations = observations_by_path[label]
        axis.scatter(
            [item.time_s + offset for item in observations],
            [item.tracking_cfo_hz / 1_000.0 for item in observations],
            s=2.5,
            facecolors="none",
            edgecolors="#e17c05",
            linewidths=0.25,
            alpha=0.34,
            label=f"independent GLRT64 candidates ({len(observations)})",
        )
        for trajectory in trajectories_by_path[label]:
            times = np.linspace(trajectory.start_s, trajectory.end_s, 80)
            values = trajectory.frequency_hz(times)
            axis.plot(times + offset, values / 1_000.0, linewidth=0.75, alpha=0.55)
        axis.set_title(f"{label} · {len(trajectories_by_path[label])} tracks", loc="left")
        axis.grid(alpha=0.16)
        axis.set_xlim(0.0, duration_s)
        axis.legend(fontsize=7, loc="best")
    for axis in axes[:, 0]:
        axis.set_ylabel("CFO (kHz)")
    for axis in axes[-1, :]:
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        f"{title} · {run.session_id}\ndegree 1 is the only permitted radio model", fontweight="bold"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _plot_selected(
    destination: Path,
    run: base.CohortRun,
    paths: tuple[PathEvidence, ...],
    tracks: tuple[SelectedLinearTrack, ...],
    duration_s: float,
) -> None:
    by_path = {item.label: [] for item in paths}
    for track in tracks:
        by_path[track.path.label].append(track)
    top = {item.trajectory.trajectory_id: item.label for item in tracks[:3]}
    figure, axes = plt.subplots(2, 2, figsize=(17, 10), sharex=True, sharey=True)
    for axis, label in zip(axes.flat, sorted(by_path), strict=True):
        for track in by_path[label]:
            time = np.asarray([item.time_s for item in track.observations]) + (
                track.start_s - track.trajectory.start_s
            )
            cfo = np.asarray([item.tracking_cfo_hz for item in track.observations])
            name = top.get(track.trajectory.trajectory_id)
            axis.scatter(time, cfo / 1_000.0, s=4, alpha=0.18, color="#e17c05")
            times = np.linspace(track.start_s, track.end_s, 80)
            local = times - (track.start_s - track.trajectory.start_s)
            axis.plot(
                times,
                track.trajectory.frequency_hz(local) / 1_000.0,
                color="#111111",
                linewidth=1.3 if name else 0.8,
                alpha=0.95 if name else 0.55,
            )
            if name:
                axis.text(
                    times[len(times) // 2],
                    track.trajectory.frequency_hz(local)[len(times) // 2] / 1_000.0,
                    name,
                )
        axis.set_title(f"{label} · {len(by_path[label])} selected", loc="left")
        axis.grid(alpha=0.16)
        axis.set_xlim(0.0, duration_s)
    for axis in axes[:, 0]:
        axis.set_ylabel("CFO (kHz)")
    for axis in axes[-1, :]:
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        f"Strictly linear selected families · {run.session_id}\n"
        "points and membership come from independent pilot-scan candidates",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _plot_matches(
    destination: Path,
    run: base.CohortRun,
    tracks: tuple[SelectedLinearTrack, ...],
    matches: tuple[dict[str, Any], ...],
) -> None:
    if len(tracks) != len(matches):
        raise ValueError("track and match counts must agree")
    if not tracks:
        raise ValueError("at least one track is required for a match plot")
    figure, axes_grid = plt.subplots(
        len(tracks),
        1,
        figsize=(14, 4 * len(tracks)),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    axes = axes_grid[:, 0]
    for axis, track, match in zip(axes, tracks, matches, strict=True):
        candidates = match["top_candidates"]
        axis.scatter(
            [item["zenith_angle_deg"] for item in candidates],
            [item["predicted_rate_hz_s"] for item in candidates],
            color="#277da1",
            s=35,
        )
        axis.axhline(track.rate_hz_s, color="#111111", linewidth=1.2)
        for rank, item in enumerate(candidates, 1):
            axis.annotate(
                f"#{rank} {item['object_name']}",
                (item["zenith_angle_deg"], item["predicted_rate_hz_s"]),
                fontsize=8,
            )
        axis.set_title(
            f"{track.label} · {track.path.label} · radio {track.rate_hz_s:+.1f} Hz/s", loc="left"
        )
        axis.set_ylabel("rate (Hz/s)")
        axis.grid(alpha=0.16)
    axes[-1].set_xlabel("zenith angle (degrees)")
    figure.suptitle(f"Degree-1-only radio/TLE rate matches · {run.session_id}", fontweight="bold")
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _plot_nulls(
    destination: Path,
    run: base.CohortRun,
    tracks: tuple[SelectedLinearTrack, ...],
    matches: tuple[dict[str, Any], ...],
) -> None:
    if len(tracks) != len(matches):
        raise ValueError("track and match counts must agree")
    if not tracks:
        raise ValueError("at least one track is required for a null plot")
    figure, axes_grid = plt.subplots(
        len(tracks),
        1,
        figsize=(14, 3.7 * len(tracks)),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    axes = axes_grid[:, 0]
    for axis, track, match in zip(axes, tracks, matches, strict=True):
        controls = match["null_controls"]
        shifts = np.asarray([item["time_shift_s"] for item in controls])
        errors = np.asarray([item["best_absolute_rate_error_hz_s"] for item in controls])
        insertion = int(np.searchsorted(shifts, 0.0))
        axis.plot(
            np.insert(shifts, insertion, 0.0),
            np.insert(errors, insertion, match["best_absolute_rate_error_hz_s"]),
            color="#687381",
            marker="o",
            markersize=3,
            linewidth=0.8,
        )
        axis.scatter(
            [0.0], [match["best_absolute_rate_error_hz_s"]], color="#d1495b", s=50, zorder=5
        )
        axis.set_title(
            f"{track.label} · true-time rank "
            f"{match['true_time_rank_among_true_and_null']}/"
            f"{match['null_control_count'] + 1}",
            loc="left",
        )
        axis.set_ylabel("nearest error (Hz/s)")
        axis.grid(alpha=0.16)
    axes[-1].set_xlabel("deliberate TLE time shift (s)")
    figure.suptitle(
        f"Wrong-time nulls for degree-1-only tracks · {run.session_id}", fontweight="bold"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _plot_tle_overlay(
    destination: Path,
    run: base.CohortRun,
    tracks: tuple[SelectedLinearTrack, ...],
    matches: tuple[dict[str, Any], ...],
    catalogue,
    observer: ObserverSiteV1,
    cone_satellites: tuple[base.ConeSatellite, ...],
    dwell_start_ns: int,
    duration_s: float,
    horizon_deg: float,
) -> None:
    grid = base._grid(dwell_start_ns, duration_s)
    sample_times_s = np.asarray(grid.offsets_s(), dtype=float) + duration_s / 2.0
    observed = observe_grid(propagate_grid(catalogue, grid), observer, grid)
    by_number = {number: index for index, number in enumerate(catalogue.satellite_numbers)}
    colors = ("#d1495b", "#00798c", "#7a5195")
    if len(tracks) != len(matches):
        raise ValueError("track and match counts must agree")
    if not tracks:
        raise ValueError("at least one track is required for a TLE overlay")
    figure, axes_grid = plt.subplots(
        len(tracks),
        1,
        figsize=(14, 4 * len(tracks)),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    axes = axes_grid[:, 0]
    for axis, track, match in zip(axes, tracks, matches, strict=True):
        axis.plot(
            [track.start_s, track.end_s],
            [track.rate_hz_s, track.rate_hz_s],
            color="#111111",
            linewidth=1.3,
            label=f"pre-replay d1 radio {track.rate_hz_s:+.1f} Hz/s",
        )
        cone_numbers = {item.catalog_number for item in cone_satellites}
        for satellite in cone_satellites:
            index = by_number[satellite.catalog_number]
            doppler = doppler_shift_hz(track.path.rf_frequency_hz, observed.range_rate_km_s[index])
            rate = np.gradient(doppler, sample_times_s, edge_order=2)
            inside = observed.elevation_deg[index] >= 60.0
            axis.plot(
                sample_times_s,
                np.where(inside, rate, np.nan),
                color="#9aa4af",
                linewidth=0.7,
                alpha=0.55,
            )
        for color, candidate in zip(colors, match["top_candidates"][:3], strict=False):
            index = by_number[candidate["catalog_number"]]
            doppler = doppler_shift_hz(track.path.rf_frequency_hz, observed.range_rate_km_s[index])
            rate = np.gradient(doppler, sample_times_s, edge_order=2)
            visible = observed.elevation_deg[index] >= horizon_deg
            axis.plot(
                sample_times_s,
                np.where(visible, rate, np.nan),
                color=color,
                linewidth=1.2,
                label=(
                    candidate["object_name"]
                    + (" · enters 30° cone" if candidate["catalog_number"] in cone_numbers else "")
                ),
            )
        axis.set_xlim(0.0, duration_s)
        axis.set_ylabel("Doppler rate (Hz/s)")
        axis.set_title(f"{track.label} · {track.path.label}", loc="left")
        axis.grid(alpha=0.16)
        axis.legend(fontsize=8, loc="best")
    axes[-1].set_xlabel("capture time (s)")
    figure.suptitle(
        f"Strict d1 radio rates and TLE predictions · {run.session_id}\n"
        "gray: elevation ≥60° (30° zenith cone); colored: broad ≥10° match control",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _dwell(
    run: base.CohortRun,
    paths: tuple[PathEvidence, ...],
    archive: TleArchiveReader,
    observer: ObserverSiteV1,
    *,
    provider: str,
    horizon_deg: float,
    maximum_selected: int,
    output_root: Path,
) -> dict[str, Any]:
    start_ns, duration_s = base._nominal_capture(paths)
    tracks, raw_by_path, observations_by_path, config_digest = _selected_tracks(
        paths, start_ns, maximum_selected=maximum_selected
    )
    top = tracks[:3]
    snapshot = base._select_causal_space_track_snapshot(
        archive, anchor_utc_ns=start_ns, provider=provider
    )
    snapshot_selection = base._snapshot_selection_evidence(
        archive,
        snapshot,
        anchor_utc_ns=start_ns,
        provider=provider,
    )
    catalogue = parse_element_sets(archive.read(snapshot))
    capture_grid = base._grid(start_ns, duration_s)
    capture_times_s = np.asarray(capture_grid.offsets_s(), dtype=float) + duration_s / 2.0
    capture_observed = observe_grid(propagate_grid(catalogue, capture_grid), observer, capture_grid)
    cone_satellites = base._cone_satellites(
        catalogue,
        capture_observed,
        capture_times_s,
        elevation_threshold_deg=60.0,
        anchor_utc_ns=start_ns,
    )
    matches = tuple(_match(track, catalogue, observer, start_ns, horizon_deg) for track in top)
    stem = run.session_id.removeprefix("cap-")
    raw_name = f"{stem}-d1only-raw.png"
    selected_name = f"{stem}-d1only-selected.png"
    match_name = f"{stem}-d1only-tle-rate.png"
    overlay_name = f"{stem}-d1only-tle-overlay.png"
    null_name = f"{stem}-d1only-null.png"
    _plot_track_bank(
        output_root / raw_name,
        run,
        paths,
        raw_by_path,
        observations_by_path,
        duration_s,
        start_ns,
        title="Fresh raw trajectory bank",
    )
    selected_by_path = {
        path.label: tuple(track.trajectory for track in tracks if track.path.label == path.label)
        for path in paths
    }
    _plot_selected(output_root / selected_name, run, paths, tracks, duration_s)
    _plot_matches(output_root / match_name, run, top, matches)
    _plot_tle_overlay(
        output_root / overlay_name,
        run,
        top,
        matches,
        catalogue,
        observer,
        cone_satellites,
        start_ns,
        duration_s,
        horizon_deg,
    )
    _plot_nulls(output_root / null_name, run, top, matches)
    return {
        "session_id": run.session_id,
        "analysis_run_id": run.run_id,
        "capture_start_utc_ns": start_ns,
        "duration_s": duration_s,
        "linear_only_config_digest": config_digest,
        "pilot_scan_sources": [
            {
                "path": path.label,
                "uri": path.pilot_scan_product.logical_uri,
                "digest": path.pilot_scan_product.digest,
            }
            for path in paths
        ],
        "raw_track_count": sum(len(items) for items in raw_by_path.values()),
        "selected_track_count": len(tracks),
        "paths": [
            {
                "path": path.label,
                "raw_track_count": len(raw_by_path[path.label]),
                "selected_track_count": len(selected_by_path[path.label]),
            }
            for path in paths
        ],
        "top_tracks": [
            {
                "label": track.label,
                "path": track.path.label,
                "trajectory_id": track.trajectory.trajectory_id,
                "polynomial_degree": track.trajectory.polynomial_degree,
                "start_s": track.start_s,
                "end_s": track.end_s,
                "duration_s": track.duration_s,
                "observation_count": track.trajectory.point_count,
                "rate_hz_s": track.rate_hz_s,
                "reconstructed_rf_hz": track.path.rf_frequency_hz,
                "authoritative_tagged_rf_hz": starlink_edge_rf_center_frequency_hz(
                    track.path.binding.starlink_channel,
                    track.path.binding.starlink_edge,
                ),
                "rf_consistency_error_hz": track.path.rf_frequency_hz
                - starlink_edge_rf_center_frequency_hz(
                    track.path.binding.starlink_channel,
                    track.path.binding.starlink_edge,
                ),
                "residual_rms_hz": track.trajectory.residual_rms_hz,
                "match": match,
            }
            for track, match in zip(top, matches, strict=True)
        ],
        "all_selected_rates_hz_s": [track.rate_hz_s for track in tracks],
        "all_raw_rates_hz_s": [
            float(trajectory.coefficients_hz[0])
            for trajectories in raw_by_path.values()
            for trajectory in trajectories
        ],
        "snapshot": {
            "provider": snapshot.provider,
            "collected_utc_ns": snapshot.collected_utc_ns,
            "digest": snapshot.digest,
            "selection": snapshot_selection,
        },
        "zenith_cone": {
            "half_angle_deg": 30.0,
            "minimum_elevation_deg": 60.0,
            "satellites": [
                {
                    "object_name": item.object_name,
                    "catalog_number": item.catalog_number,
                    "peak_elevation_deg": item.peak_elevation_deg,
                    "element_epoch_utc_ns": item.element_epoch_utc_ns,
                    "element_age_s_at_capture_start": item.element_age_s,
                    "intervals": [asdict(interval) for interval in item.intervals],
                }
                for item in cone_satellites
            ],
        },
        "figures": {
            "raw": raw_name,
            "selected": selected_name,
            "tle_rate": match_name,
            "tle_overlay": overlay_name,
            "null": null_name,
        },
    }


def _plot_distribution(destination: Path, dwells: list[dict[str, Any]]) -> None:
    raw = np.asarray(
        [rate for dwell in dwells for rate in dwell["all_raw_rates_hz_s"]],
        dtype=float,
    )
    selected = np.asarray(
        [rate for dwell in dwells for rate in dwell["all_selected_rates_hz_s"]],
        dtype=float,
    )
    figure, axis = plt.subplots(figsize=(12, 6))
    bins = np.linspace(
        float(min(raw.min(), selected.min())),
        float(max(raw.max(), selected.max())),
        45,
    )
    axis.hist(
        raw,
        bins=bins,
        histtype="step",
        linewidth=1.4,
        color="#277da1",
        label=f"fresh raw d1 fits ({len(raw)})",
    )
    axis.hist(
        selected,
        bins=bins,
        color="#d1495b",
        alpha=0.55,
        label=f"selected pre-replay d1 families ({len(selected)})",
    )
    axis.axvline(
        float(np.median(selected)),
        color="#111111",
        linewidth=1.1,
        label=f"selected median {np.median(selected):+.1f} Hz/s",
    )
    axis.set_xlabel("constant degree-1 Doppler rate (Hz/s)")
    axis.set_ylabel("selected tracks")
    axis.set_title(f"{len(dwells)}-dwell degree-1-only selected-track rate distribution")
    axis.grid(alpha=0.14)
    axis.legend()
    figure.tight_layout()
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _strict_t1_lines(summary_path: Path) -> list[str]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (
        summary.get("schema") != "org.leo.research.t1-dense-degree1-only/v1"
        or summary.get("radio_model") != "intercept_plus_constant_slope_only"
        or summary.get("published_replay_membership_used") is not False
    ):
        raise ValueError("T1 summary is not strict degree-1 candidate evidence")
    dense = summary["dense"]
    lines = [
        "## Focused T1 strict-linear association and basin impact",
        "",
        "This focused audit starts from the 32 independently scored raw-IQ GLRT "
        "candidates at each probe. RANSAC associates at most one candidate per "
        "probe, and Huber refits only an intercept and one constant slope. Its "
        "breakpoints are selected within disclosed post-hoc windows; none comes "
        "from the superseded mixed-order replay membership.",
        "",
        "| Piece | Interval | Constant rate | Step entering | Support | Median |residual| |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for piece in dense["pieces"]:
        interval = piece["interval_s"]
        step = (
            "—"
            if piece["step_entering_hz"] is None
            else f"{piece['step_entering_hz'] / 1_000:+.2f} kHz"
        )
        lines.append(
            f"| {piece['piece']} | {interval[0]:.3f}–{interval[1]:.3f} s | "
            f"{piece['slope_hz_s']:+.1f} Hz/s | {step} | "
            f"{piece['support_count']}/{piece['available_probe_count']} | "
            f"{piece['median_absolute_residual_hz']:.1f} Hz |"
        )
    lines.extend(
        [
            "",
            "![Strict degree-1 T1 association]"
            "(figures/2026_08_21_t1_dense_degree1_only/"
            "t1-dense-degree1-only.png)",
            "",
            f"The first supported transition is **{dense['transitions_s'][0]:.3f} s**. "
            "The earlier ≈7.9 s marker was an equal-duration plotting boundary, not "
            "a fitted changepoint. The four straight rates are real candidate-level "
            "line coherence; they do not establish that all four epochs came from "
            "one spacecraft.",
            "",
            "### What better basin retention and CFO search change",
            "",
            "An acquisition basin is a distinct local timing/CFO maximum for one "
            "20 ms probe. Raising the retained count from 8 to 32 keeps more "
            "synchronization alternatives for later straight-line association; it "
            "does not add time samples or make adjacent probes dependent. A finer "
            "CFO/GLRT grid reduces quantization and refinement error after a useful "
            "basin survives.",
            "",
            "![Strict-linear basin and grid ablation]"
            "(figures/2026_08_21_t1_dense_degree1_only/"
            "t1-basin-impact-degree1-only.png)",
            "",
            "![Full dense independent GLRT interval]"
            "(figures/2026_08_21_dense_independent_glrt/"
            "dense-independent-glrt-full.png)",
            "",
            "![Dense independent GLRT P1-endpoint zoom]"
            "(figures/2026_08_21_dense_independent_glrt/"
            "dense-independent-glrt-p1-zoom.png)",
            "",
            "A later raw-IQ one-factor sweep resolves the mechanism more precisely. "
            "In 7.5–7.9 s, Standard recovers 13/16 probes from its complete inventory; "
            "32 basins with the original broad separation recovers 14/16; a 10 kHz "
            "coarse grid recovers 15/16; and changing only nonmaximum-suppression "
            "separation from 80 kHz/20 samples to 10 kHz/5 samples recovers 16/16. "
            "Thus candidate-retention geometry—especially separation policy—is the "
            "dominant local fix. Basin count alone helps but is not sufficient. See "
            "the [full parameter study]"
            "(2026_08_22_t1_glrt_search_parameter_study.md).",
            "",
            "This overturns one narrow interpretation: missing replay markers near "
            "the end of the old P1 panel are not evidence that the RF signal vanished "
            "or physically stepped there. The independently searched signal branch "
            "continues. The old candidate truncation and mixed-order family selection "
            "made its membership brittle.",
            "",
            "![Matched time-permutation control]"
            "(figures/2026_08_21_t1_dense_degree1_only/"
            "t1-degree1-time-permutation-null.png)",
            "",
            f"Recorded time order supports **{dense['total_support_count']}** probes; "
            f"the largest of {dense['null_repeat_count']} matched time-permutation "
            f"controls supports **{dense['null_max_support_count']}**. The plus-one "
            f"p-value is {dense['null_empirical_p']:.4f}. This tests temporal line "
            "coherence after searching 32 alternatives, not Starlink attribution; "
            "capture selection and breakpoint-window choice remain post hoc.",
            "",
            "The published replay is deliberately not compared here because its "
            "membership was seeded by a mixed-order family representative. A true "
            "after-replay distribution remains pending the separately versioned "
            "linear-only pipeline. See the [focused T1 report]"
            "(2026_08_21_t1_dense_degree1_only.md) for full method details.",
            "",
        ]
    )
    return lines


def _write_report(
    path: Path,
    evidence_name: str,
    distribution_name: str,
    dwells: list[dict[str, Any]],
    relative_root: str,
    t1_summary_path: Path,
) -> None:
    lines = [
        f"# {len(dwells)}-dwell strict degree-1-only rerun",
        "",
        "This report-only rerun starts from each sealed `standard.pilot-scan` V3 "
        "product. Every candidate was scored independently at its probe. A new "
        "trajectory bank was fitted with `polynomial_degrees=(1,)`. Persisted "
        "raw-family representatives, de-aliased membership, IQ-replay membership, "
        "and final tracks were not reused.",
        "",
        "**Selected** means a representative of a family built entirely from "
        "degree-1 tracks. It is not a newly sealed Standard final product. This "
        "bounded rerun does not replay IQ or claim the published de-alias/replay "
        "gates, so it never labels these results as after replay.",
        "",
        "| Contamination audit of superseded report sections | Count |",
        "|---|---:|",
        "| Former displayed top-three tracks from d3 membership | 15 / 15 |",
        "| Former post-replay tracks from d2 or d3 membership | 47 / 61 |",
        "",
        "Those old post-replay results are not inputs to this rerun.",
        "",
        "## Observation and RF provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Observer latitude | {base.DEFAULT_LATITUDE_DEG:.6f}° |",
        f"| Observer longitude | {base.DEFAULT_LONGITUDE_DEG:.6f}° |",
        f"| Observer altitude | {base.DEFAULT_ALTITUDE_M:.1f} m |",
        "| LNB model reported for 3 of 4 paths | GEOSATpro UL1PLL |",
        "| Configured acquisition LNB local oscillator | 9.75 GHz |",
        "| Per-path physical LNB mapping | Unknown |",
        "",
        "Reconstructed RF is tuned IF plus the configured 9.75 GHz LO. Each "
        "track used below was also checked against the authoritative channel/edge "
        "RF center; the machine-readable `rf_consistency_error_hz` records any "
        "difference. Physical LNB serial-to-path mapping remains unknown, but it "
        "does not change the requested RF encoded by the acquisition binding.",
        "",
        "## Cross-capture basin-retention control",
        "",
        "A separate capture, `cap-20260821T030352-0b45a2531e70`, tests search "
        "mechanics. It is outside this cohort and does not support satellite "
        "association. Fixed 8/16/32 is candidate-level and uses no trajectory "
        "prior. Alias-edge 6+2 also uses no fitted CFO trajectory.",
        "",
        "![Candidate-level fixed basin-count timeline]"
        "(figures/2026_08_21_0b45a2531e70_basin_recovery/"
        "basin-count-timeline.png)",
        "",
        "![Candidate-level fixed basin-count summary]"
        "(figures/2026_08_21_0b45a2531e70_basin_recovery/"
        "basin-count-summary.png)",
        "",
        "![Alias-edge 6+2 output timeline]"
        "(figures/2026_08_21_0b45a2531e70_basin_recovery/"
        "guided-eight-output-timeline.png)",
        "",
        "Basin-track-consistency and CFO-guided policy figures are deliberately "
        "omitted because those analyses used a quadratic trajectory.",
        "",
        f"Machine-readable evidence: [{evidence_name}]({relative_root}/{evidence_name})",
        "",
        f"![Degree-1-only rate distribution]({relative_root}/{distribution_name})",
        "",
        f"The raw-d1 set contains **{sum(item['raw_track_count'] for item in dwells)}** "
        "trajectories; the selected-pre-replay set contains "
        f"**{sum(item['selected_track_count'] for item in dwells)}** families. "
        "This is not an after-replay comparison.",
        "",
    ]
    lines.extend(_strict_t1_lines(t1_summary_path))
    for index, dwell in enumerate(dwells, 1):
        snapshot_ns = dwell["snapshot"]["collected_utc_ns"]
        capture_ns = dwell["capture_start_utc_ns"]
        snapshot_utc = datetime.fromtimestamp(snapshot_ns / 1e9, UTC).isoformat()
        capture_utc = datetime.fromtimestamp(capture_ns / 1e9, UTC).isoformat()
        snapshot_age_s = (capture_ns - snapshot_ns) / 1e9
        causal = not dwell["snapshot"]["selection"]["selected_after_capture"]
        lines.extend(
            [
                f"## Dwell {index}: `{dwell['session_id']}`",
                "",
                f"Fresh raw degree-1 tracks: **{dwell['raw_track_count']}**. "
                f"Selected pre-replay d1 families: **{dwell['selected_track_count']}**.",
                "",
                f"Capture start: **{capture_utc}**. Space-Track snapshot: "
                f"**{snapshot_utc}**, {snapshot_age_s / 60.0:.1f} minutes before "
                f"capture. Causal: **{'yes' if causal else 'NO'}**.",
                "",
                f"![Independent GLRT64 candidates and raw d1 fits]"
                f"({relative_root}/{dwell['figures']['raw']})",
                "",
                f"![Selected pre-replay d1 families]"
                f"({relative_root}/{dwell['figures']['selected']})",
                "",
                "### Up to three tracks and their top three broad-sky candidates",
                "",
                "The satellite candidates use a broader elevation ≥10° legacy "
                "scalar-rate screen as a secondary control.",
                "",
                "| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | "
                "Elev. | Predicted | Error | TLE age | True-time rank |",
                "|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|",
            ]
        )
        for track in dwell["top_tracks"]:
            for rank, candidate in enumerate(track["match"]["top_candidates"][:3], start=1):
                cells = (
                    f"**{track['label']}**",
                    str(rank),
                    f"`{track['path']}` / {track['reconstructed_rf_hz'] / 1e9:.7f} GHz",
                    f"{track['duration_s']:.2f} s",
                    str(track["observation_count"]),
                    f"{track['rate_hz_s']:+.1f}",
                    candidate["object_name"],
                    f"{candidate['elevation_deg']:.1f}°",
                    f"{candidate['predicted_rate_hz_s']:+.1f}",
                    f"{candidate['absolute_rate_error_hz_s']:.1f}",
                    f"{candidate['element_age_s'] / 3600.0:.2f} h",
                    f"{track['match']['true_time_rank_among_true_and_null']}/"
                    f"{track['match']['null_control_count'] + 1}",
                )
                lines.append("| " + " | ".join(cells) + " |")
        lines.extend(
            [
                "",
                "### 30° zenith cone during the full capture",
                "",
                "Half-angle 30° is equivalent to elevation ≥60°. Intervals are "
                "relative to capture start.",
                "",
                "| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |",
                "|---|---:|---:|---|---:|",
            ]
        )
        cone = dwell["zenith_cone"]["satellites"]
        if not cone:
            lines.append("| None | — | — | — | — |")
        for satellite in cone:
            intervals = ", ".join(
                f"{item['start_s']:.2f}–{item['end_s']:.2f} s" for item in satellite["intervals"]
            )
            lines.append(
                f"| {satellite['object_name']} | {satellite['catalog_number']} | "
                f"{satellite['peak_elevation_deg']:.1f}° | {intervals} | "
                f"{satellite['element_age_s_at_capture_start'] / 3600.0:.2f} h |"
            )
        lines.extend(
            [
                "",
                f"![TLE rate field]({relative_root}/{dwell['figures']['tle_rate']})",
                "",
                f"![Full-capture cone and broad-control overlay]"
                f"({relative_root}/{dwell['figures']['tle_overlay']})",
                "",
                f"![Wrong-time null controls]({relative_root}/{dwell['figures']['null']})",
                "",
            ]
        )
    lines.extend(
        [
            "## Scope and limitations",
            "",
            "No quadratic or cubic radio fit, family member, selector, observation "
            "membership, or curvature statistic is used. TLE curve curvature is "
            "orbital prediction, not a nonlinear radio estimate. Space-Track "
            "snapshots are the newest archived snapshot at or before each dwell. "
            "This is compatibility evidence, not satellite identification.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> None:
    args = _arguments()
    if args.maximum_selected_per_path < 1:
        raise ValueError("maximum-selected-per-path must be positive")
    session_ids = tuple(args.session_ids) or DEFAULT_SESSION_IDS
    args.output_root.mkdir(parents=True, exist_ok=True)
    engine = create_catalog_engine(args.database_url)
    resolver = BulkUriResolver(args.bulk_root, allowed_namespaces=("analysis",), create=False)
    archive = TleArchiveReader(args.tle_root)
    observer = ObserverSiteV1(
        latitude_deg=base.DEFAULT_LATITUDE_DEG,
        longitude_deg=base.DEFAULT_LONGITUDE_DEG,
        altitude_m=base.DEFAULT_ALTITUDE_M,
        label="preliminary-sausalito-degree1-only-review",
    )
    with Session(engine) as database:
        cohort = base._cohort(database, session_ids)
        dwells = [
            _dwell(
                run,
                _path_evidence(database, resolver, run),
                archive,
                observer,
                provider=args.provider,
                horizon_deg=args.horizon_deg,
                maximum_selected=args.maximum_selected_per_path,
                output_root=args.output_root,
            )
            for run in cohort
        ]
    distribution_name = "five-dwell-d1only-rate-distribution.png"
    _plot_distribution(args.output_root / distribution_name, dwells)
    evidence_name = "five-dwell-d1only-evidence.json"
    evidence = {
        "schema_version": 1,
        "analysis_kind": "multi_dwell_degree1_only_report_rerun",
        "analysis_main_commit": _git_revision(),
        "origin_main_commit": _git_revision("origin/main"),
        "analysis_tool_sha256": _sha256(Path(__file__)),
        "generated_utc": datetime.now(UTC).isoformat(),
        "radio_polynomial_degrees": [1],
        "source_membership": "independent_standard_pilot_scan_v3_candidates",
        "persisted_nonlinear_seeded_membership_reused": False,
        "iq_replay_performed": False,
        "superseded_report_contamination_audit": {
            "displayed_top_three_from_degree3_membership": {"count": 15, "total": 15},
            "post_replay_from_degree2_or_degree3_membership": {
                "count": 47,
                "total": 61,
            },
        },
        "observer": observer.model_dump(mode="json"),
        "hardware_provenance": {
            "reported_model_for_three_of_four_lnbs": "GEOSATpro UL1PLL",
            "configured_lo_frequency_hz": 9_750_000_000,
            "rf_input_hz": [10_700_000_000, 12_750_000_000],
            "per_path_physical_lnb_mapping_known": False,
            "rf_reconstruction": "tuned_center_frequency_hz + 9750000000",
            "rf_authority_check": "starlink_channel + starlink_edge",
        },
        "horizon_deg": args.horizon_deg,
        "zenith_cone_half_angle_deg": 30.0,
        "zenith_cone_minimum_elevation_deg": 60.0,
        "dwells": dwells,
        "distribution_figure": distribution_name,
    }
    (args.output_root / evidence_name).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    report_paths = [args.report_path, *args.report_alias]
    for report_path in report_paths:
        relative_root = os.path.relpath(args.output_root, report_path.parent)
        _write_report(
            report_path,
            evidence_name,
            distribution_name,
            dwells,
            relative_root,
            args.t1_summary,
        )


if __name__ == "__main__":
    main()
