#!/usr/bin/env python3
"""Render split-penalized residual-Hough research reports for persisted captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.cfo_lines import (
    HoughConfig,
    LineDetectionConfig,
    LineSegment,
    circular_residual_hz,
    weighted_hough_lines,
)
from leo.analysis.residual_hough import (
    ResidualHoughSelection,
    ResidualHoughSelectionConfig,
    detect_residual_hough_lines,
)
from leo.analysis.standard.alternate_tracks import (
    build_residual_hough_cfo_tracks,
    default_alternate_cfo_config,
    pilot_scan_points,
    render_alternate_cfo_tracks_png,
)
from leo.analysis.standard.analyzers import _pilot_detections
from leo.analysis.standard.reports import standard_v3_trajectory_documents
from leo.analysis.standard.runner import SingleReceiverIqReader
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_residual_hough_pilot_trajectories,
    replay_pilot_trajectories,
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
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.storage import BulkUriResolver, RecordingStore
from leo.storage.errors import BundleCorruptionError


@dataclass(frozen=True, slots=True)
class _PilotSource:
    document: dict[str, Any]
    binding: StandardPathInputBindV3
    bundle_uri: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", action="append", required=True)
    parser.add_argument("--path-label", default="stream-0/RX1")
    parser.add_argument("--minimum-split-gain", type=float, default=200.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-replay", action="store_true")
    return parser.parse_args()


def _initial_hough_config() -> HoughConfig:
    config = default_alternate_cfo_config().initial_hough
    return HoughConfig(
        common=LineDetectionConfig(
            alias_spacing_hz=config.alias_spacing_hz,
            minimum_slope_hz_per_s=config.minimum_slope_hz_per_s,
            maximum_slope_hz_per_s=config.maximum_slope_hz_per_s,
            residual_gate_hz=config.residual_gate_hz,
            maximum_gap_s=config.maximum_gap_s,
            minimum_span_s=config.minimum_span_s,
            minimum_support=config.minimum_support,
            minimum_point_weight=config.minimum_point_weight,
            maximum_tracks=config.maximum_detected_tracks,
        ),
        slope_bins=config.slope_bins,
        intercept_bins=config.intercept_bins,
        peak_candidates=config.peak_candidates,
    )


def _segment_rank(segment: LineSegment) -> tuple[float, float, int, float, str]:
    return (
        segment.weighted_support,
        segment.end_s - segment.start_s,
        segment.support,
        -segment.residual_rms_hz,
        segment.segment_id,
    )


def _read_verified_pilot_scan(
    resolver: BulkUriResolver, product: AnalysisProduct
) -> dict[str, Any]:
    payload = resolver.resolve(product.logical_uri).read_bytes()
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if digest != product.digest:
        raise ValueError(f"artifact digest mismatch: {product.logical_uri}")
    document = json.loads(payload)
    if not isinstance(document, dict) or document.get("schema_version") != 3:
        raise ValueError(f"pilot scan has an unexpected contract: {product.logical_uri}")
    return document


def _pilot_scans(
    database: Session,
    resolver: BulkUriResolver,
    session_ids: tuple[str, ...],
    path_label: str,
) -> dict[str, _PilotSource]:
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("exact session IDs must be unique")
    rows = database.execute(
        select(AnalysisRun, CaptureSession)
        .join(CurrentAnalysis, CurrentAnalysis.run_id == AnalysisRun.id)
        .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
        .where(
            AnalysisRun.state == "succeeded",
            AnalysisRun.pipeline_lane == "standard",
            CaptureSession.id.in_(session_ids),
            CaptureSession.source_type != "test",
        )
    ).all()
    runs = {capture.id: (run, capture) for run, capture in rows}
    missing = [session_id for session_id in session_ids if session_id not in runs]
    if missing:
        raise ValueError("sessions lack current succeeded Standard runs: " + ", ".join(missing))

    result: dict[str, _PilotSource] = {}
    for session_id in session_ids:
        run, capture = runs[session_id]
        if capture.bundle_uri is None:
            raise ValueError(f"{session_id} has no available recording bundle")
        bindings = database.execute(
            select(RunSubjectBinding, AnalysisScope)
            .join(AnalysisScope, AnalysisScope.id == RunSubjectBinding.scope_id)
            .where(
                RunSubjectBinding.run_id == run.id,
                AnalysisScope.kind == "receiver_path",
            )
        ).all()
        matching_scope_id = None
        matching_binding = None
        for registration, scope in bindings:
            binding = StandardPathInputBindV3.model_validate(registration.document)
            label = f"{binding.stream_id}/RX{binding.receiver_id}"
            if label == path_label:
                matching_scope_id = scope.id
                matching_binding = binding
                break
        if matching_scope_id is None:
            raise ValueError(f"{session_id} has no evidence path {path_label}")
        products = database.scalars(
            select(AnalysisProduct).where(
                AnalysisProduct.run_id == run.id,
                AnalysisProduct.scope_id == matching_scope_id,
                AnalysisProduct.kind == "standard.pilot-scan",
                AnalysisProduct.available.is_(True),
            )
        ).all()
        if len(products) != 1 or products[0].schema_version != 3:
            raise ValueError(f"{session_id} {path_label} lacks one Pilot Scan V3 product")
        if matching_binding is None:
            raise AssertionError("matched scope lacks its validated path binding")
        result[session_id] = _PilotSource(
            document=_read_verified_pilot_scan(resolver, products[0]),
            binding=matching_binding,
            bundle_uri=capture.bundle_uri,
        )
    return result


def _feedback_config() -> TrajectoryFeedbackConfig:
    return TrajectoryFeedbackConfig(
        maximum_workers=4,
        maximum_scored_candidates_per_probe=8,
        probe_offsets_ms=(0, 25),
        cfo_acquisition_mode="independent_wide_per_probe",
        cfo_search_min_hz=-400_000.0,
        cfo_search_max_hz=400_000.0,
    )


def _run_v3_replay(
    source: _PilotSource,
    *,
    segmentation_config,
    output: Path,
) -> dict[str, Any]:
    detections = _pilot_detections(source.document)
    feedback_config = _feedback_config()
    bank, representatives = fit_residual_hough_pilot_trajectories(
        detections,
        feedback_config,
        segmentation_config,
    )
    store = RecordingStore.open_read_only(Path(os.environ["LEO_BULK_ROOT"]))
    bundle = store.inspect_uri(source.bundle_uri)
    iq = SingleReceiverIqReader(
        store.reader(bundle, source.binding.stream_id, verify=True),
        source.binding.receiver_id,
    )
    replay = replay_pilot_trajectories(
        iq,
        detections,
        representatives,
        feedback_config,
        edge=source.binding.starlink_edge,
    )
    products = standard_v3_trajectory_documents(
        detections=detections,
        bank=bank,
        representatives=representatives,
        replay=replay,
        coarse_window_samples=int(source.document["coarse_window_samples"]),
        subwindow_samples=int(source.document["subwindow_samples"]),
        probe_samples=int(source.document["probe_samples"]),
        maximum_scored_candidates_per_probe=int(
            source.document["maximum_scored_candidates_per_probe"]
        ),
        probe_schedule_digest=str(source.document["probe_schedule_digest"]),
    )
    summary = {
        "trajectory_bank": products["standard.trajectory-bank"],
        "trajectory_feedback_content_digest": canonical_digest(
            products["standard.trajectory-feedback"]
        ),
        "trajectory_table": products["standard.glrt64-trajectory-table"],
        "representative_count": len(representatives),
        "replay_result_count": len(replay),
        "replay_preserved": True,
    }
    output.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _parent_arrays(points, parent: LineSegment, alias_spacing_hz: float):
    by_id = {point.point_id: point for point in points}
    selected = tuple(by_id[point_id] for point_id in parent.point_ids)
    times = np.asarray([point.time_s for point in selected], dtype=float)
    frequency = np.asarray([point.frequency_hz for point in selected], dtype=float)
    prediction = parent.slope_hz_per_s * times + parent.intercept_hz
    residual = circular_residual_hz(frequency, prediction, alias_spacing_hz)
    return selected, times, prediction + residual, residual


def _render(
    *,
    session_id: str,
    path_label: str,
    points,
    parent: LineSegment,
    selection: ResidualHoughSelection,
    alias_spacing_hz: float,
    output: Path,
) -> None:
    selected, times, unwrapped_frequency, residual = _parent_arrays(
        points, parent, alias_spacing_hz
    )
    residual_by_id = {
        point.point_id: float(point_residual)
        for point, point_residual in zip(selected, residual, strict=True)
    }
    time_by_id = {point.point_id: point.time_s for point in selected}
    order = np.argsort(times)
    figure, (frequency_axis, residual_axis) = plt.subplots(
        2,
        1,
        figsize=(14, 11),
        sharex=True,
        constrained_layout=True,
    )
    parent_time = np.asarray([parent.start_s, parent.end_s], dtype=float)
    parent_frequency = parent.slope_hz_per_s * parent_time + parent.intercept_hz
    frequency_axis.plot(
        parent_time,
        parent_frequency / 1_000.0,
        color="#D62728",
        linewidth=1.0,
        label="parent weighted-Hough line",
        zorder=2,
    )
    frequency_axis.scatter(
        times[order],
        unwrapped_frequency[order] / 1_000.0,
        color="#B8B8B8",
        s=12,
        alpha=0.62,
        linewidths=0,
        label=f"all parent support (n={parent.support})",
        zorder=3,
    )
    residual_axis.scatter(
        times[order],
        residual[order] / 1_000.0,
        color="#B8B8B8",
        s=12,
        alpha=0.62,
        linewidths=0,
        zorder=3,
    )
    residual_axis.axhline(0.0, color="#555555", linewidth=0.8, zorder=1)
    colours = plt.get_cmap("tab10")
    for line_index, line in enumerate(selection.lines):
        colour = colours(line_index % 10)
        line_time = np.asarray([line.start_s, line.end_s], dtype=float)
        residual_line = line.residual_slope_hz_per_s * line_time + line.residual_intercept_hz
        mapped_line = line.mapped_slope_hz_per_s * line_time + line.mapped_intercept_hz
        support_time = np.asarray([time_by_id[point_id] for point_id in line.point_ids])
        support_residual = np.asarray([residual_by_id[point_id] for point_id in line.point_ids])
        support_unwrapped = (
            parent.slope_hz_per_s * support_time + parent.intercept_hz + support_residual
        )
        sources = "+".join(f"R{number}" for number in line.source_proposal_numbers)
        residual_axis.scatter(
            support_time,
            support_residual / 1_000.0,
            color=colour,
            s=14,
            alpha=0.78,
            linewidths=0,
            zorder=4,
        )
        residual_axis.plot(
            line_time,
            residual_line / 1_000.0,
            color=colour,
            linewidth=1.8,
            label=(
                f"{sources}: {line.start_s:.2f}–{line.end_s:.2f} s, "
                f"n={line.support}, "
                f"Δslope {line.residual_slope_hz_per_s / 1_000.0:+.2f} kHz/s"
            ),
            zorder=5,
        )
        frequency_axis.scatter(
            support_time,
            support_unwrapped / 1_000.0,
            color=colour,
            s=14,
            alpha=0.78,
            linewidths=0,
            zorder=4,
        )
        frequency_axis.plot(
            line_time,
            mapped_line / 1_000.0,
            color=colour,
            linewidth=1.8,
            zorder=5,
        )
    frequency_axis.set_ylabel("Alias-unwrapped frequency (kHz)")
    frequency_axis.grid(True, color="#BBBBBB", alpha=0.28, linewidth=0.6)
    frequency_axis.legend(loc="upper right", frameon=False)
    residual_axis.set_xlabel("Elapsed time (s)")
    residual_axis.set_ylabel("Parent-line residual (kHz)")
    residual_axis.grid(True, color="#BBBBBB", alpha=0.28, linewidth=0.6)
    residual_axis.legend(loc="upper left", frameon=False, ncol=2, fontsize=8)
    frequency_axis.set_xlim(parent.start_s - 0.25, parent.end_s + 0.25)
    figure.suptitle(
        f"{session_id} · {path_label} · split-penalized residual Hough\n"
        f"minimum split gain {selection.minimum_split_gain:g} · "
        f"selected {selection.selected_line_count}/"
        f"{selection.considered_proposal_count} grouped lines · "
        f"assigned {selection.assigned_point_count}/{parent.support} points",
        fontsize=14,
        fontweight="bold",
    )
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _report_entry(
    *,
    session_id: str,
    path_label: str,
    points,
    parent: LineSegment,
    selection: ResidualHoughSelection,
    png: Path,
    pipeline_png: Path,
    pipeline_json: Path,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "path": path_label,
        "source_point_count": len(points),
        "parent": asdict(parent),
        "selection": asdict(selection),
        "png": str(png),
        "pipeline_png": str(pipeline_png),
        "pipeline_json": str(pipeline_json),
    }


def main() -> None:
    args = _parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    hough_config = _initial_hough_config()
    pipeline_config = default_alternate_cfo_config().model_copy(
        update={"minimum_split_gain": args.minimum_split_gain}
    )
    selection_config = ResidualHoughSelectionConfig(
        minimum_split_gain=args.minimum_split_gain,
        maximum_proposals=pipeline_config.maximum_proposals_per_parent,
        maximum_parent_support=pipeline_config.maximum_parent_support,
    )
    engine = create_catalog_engine(os.environ["LEO_DATABASE_URL"])
    try:
        with Session(engine) as database:
            pilot_scans = _pilot_scans(
                database,
                BulkUriResolver(
                    Path("/srv/bulk/leo"),
                    allowed_namespaces=("analysis",),
                    create=False,
                ),
                tuple(args.session_id),
                args.path_label,
            )
    finally:
        engine.dispose()

    entries: list[dict[str, Any]] = []
    for session_id in args.session_id:
        source = pilot_scans[session_id]
        points = pilot_scan_points(source.document)
        initial_segments = weighted_hough_lines(points, hough_config)
        if not initial_segments:
            raise ValueError(f"{session_id} {args.path_label} returned no Hough segments")
        parent = max(initial_segments, key=_segment_rank)
        selection = detect_residual_hough_lines(
            points=points,
            parent=parent,
            hough_config=hough_config,
            selection_config=selection_config,
        )
        stem = f"{session_id}-{args.path_label.replace('/', '-')}"
        png = output_dir / f"{stem}-residual-hough.png"
        metrics = output_dir / f"{stem}-residual-hough.json"
        pipeline_png = output_dir / f"{stem}-pipeline-segmentation.png"
        pipeline_json = output_dir / f"{stem}-pipeline-segmentation.json"
        _render(
            session_id=session_id,
            path_label=args.path_label,
            points=points,
            parent=parent,
            selection=selection,
            alias_spacing_hz=hough_config.common.alias_spacing_hz,
            output=png,
        )
        entry = _report_entry(
            session_id=session_id,
            path_label=args.path_label,
            points=points,
            parent=parent,
            selection=selection,
            png=png,
            pipeline_png=pipeline_png,
            pipeline_json=pipeline_json,
        )
        pipeline_bank = build_residual_hough_cfo_tracks(
            source.document,
            pilot_digest=canonical_digest(source.document),
            config=pipeline_config,
        )
        pipeline_json.write_text(json.dumps(pipeline_bank.model_dump(mode="json"), indent=2) + "\n")
        pipeline_png.write_bytes(render_alternate_cfo_tracks_png(source.document, pipeline_bank))
        if args.run_replay:
            replay_json = output_dir / f"{stem}-trajectory-replay-v3.json"
            expected_config_digest = canonical_digest(pipeline_config.model_dump(mode="json"))
            replay_summary = None
            if replay_json.exists():
                candidate = json.loads(replay_json.read_text())
                bank = candidate.get("trajectory_bank", {})
                if (
                    isinstance(bank, dict)
                    and bank.get("schema_version") == 3
                    and bank.get("config_digest") == expected_config_digest
                ):
                    replay_summary = candidate
            try:
                if replay_summary is None:
                    replay_summary = _run_v3_replay(
                        source,
                        segmentation_config=pipeline_config,
                        output=replay_json,
                    )
            except BundleCorruptionError as error:
                error_json = output_dir / f"{stem}-trajectory-replay-v3-error.json"
                failure = {
                    "status": "blocked_raw_integrity",
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "verification_bypassed": False,
                }
                error_json.write_text(json.dumps(failure, indent=2) + "\n")
                entry["trajectory_replay_v3_error_json"] = str(error_json)
                entry["trajectory_replay_v3"] = failure
            else:
                entry["trajectory_replay_v3_json"] = str(replay_json)
                entry["trajectory_replay_v3"] = {
                    "status": "complete",
                    "representative_count": replay_summary["representative_count"],
                    "replay_result_count": replay_summary["replay_result_count"],
                    "trajectory_feedback_content_digest": replay_summary[
                        "trajectory_feedback_content_digest"
                    ],
                }
        metrics.write_text(json.dumps(entry, indent=2) + "\n")
        entries.append(entry)

    manifest = {
        "algorithm": "split-penalized-residual-hough-research-v1",
        "configuration": {
            "hough": asdict(hough_config),
            "selection": asdict(selection_config),
            "residual_gate_rule": "alias_spacing_hz / (2 * intercept_bins)",
            "selection_criterion": ("theil_sen_l1_mdl + minimum_split_gain * selected_line_count"),
        },
        "reports": entries,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
