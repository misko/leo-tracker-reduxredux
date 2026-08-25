#!/usr/bin/env python3
"""Memory-bounded long-locklet probe for one persisted Aug-25 branch.

IQ is read and digest-verified in bounded chunks into a temporary complex128
memmap.  The research recovery core then sees one contiguous array and keeps
one uninterrupted causal filter state.  Calling the core independently per
read chunk would reset the Kalman state and is intentionally not done.

This is an exploratory, candidate-only analysis.  Odd Qin is held out from
the frame update, but GLRT64 acquisition and persisted trajectory selection
used all Qin symbols; odd errors are therefore conditional fold-heldout
metrics, not end-to-end untouched validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

REPOSITORY_ROOT = Path(os.environ.get("LEO_REPOSITORY_ROOT", Path.cwd())).resolve()
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from leo.analysis.research.continuous_frame_recovery import (  # noqa: E402
    FrameOpportunityOutcome,
    FrameRecoveryAnchor,
    FrameRecoveryConfig,
    anchors_compatible,
    recover_contiguous_frames,
)
from leo.analysis.starlink.templates import StarlinkEdge  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402
from tools.prototype_continuous_frame_recovery import (  # noqa: E402
    GlrtAnchorCandidate,
    OwnedAnchor,
    _frame_document,
    add_trailing_line_predictions,
)

SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
RUN_ID = "capture-a5d45dd7752c4fc7833cd017a289f8d7"
SCOPE = "sha256:7f564aad7246e3f24930ae2851c7ddfd58cf0879a052cb5fc304b897e063c74f"
STREAM_ID = "stream-1"
RECEIVER_ID = 1
EDGE = StarlinkEdge.UPPER
SAMPLE_RATE_HZ = 2_500_000
PROBE_SAMPLES = round(0.020 * SAMPLE_RATE_HZ)
FRAME_PERIOD = SAMPLE_RATE_HZ / 750.0
FRAME_CONTENT_SAMPLES = round(302 * SAMPLE_RATE_HZ * 4.4e-6)
MAXIMUM_INTERVAL_S = 15.0

RECORDING_ROOT = Path("/srv/bulk/leo/recordings/2026/08/25") / SESSION_ID
RECORDING_MANIFEST = RECORDING_ROOT / "manifest.json"
ANALYSIS_ROOT = Path("/srv/bulk/leo/analysis") / SESSION_ID / RUN_ID
ANALYSIS_MANIFEST = ANALYSIS_ROOT / "manifest.json"
PATH_ROOT = ANALYSIS_ROOT / "scientific/path-standard" / SCOPE
PILOT_SCAN = PATH_ROOT / "standard.pilot-scan.v3.json"
TRAJECTORY_BANK = PATH_ROOT / "standard.final-trajectory-bank.v3.json"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-s", type=float, default=47.8)
    parser.add_argument("--stop-s", type=float, default=48.3)
    parser.add_argument("--read-chunk-s", type=float, default=0.25)
    parser.add_argument("--anchor-refresh-s", type=float, default=0.5)
    parser.add_argument("--anchor-epoch-tolerance-samples", type=int, default=4)
    parser.add_argument("--summary-block-s", type=float, default=1.0)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/tmp/cap-20260825T150802-long-continuity-probe"),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one object: {path}")
    return value


def maximum_rss_mib() -> float:
    # Linux ru_maxrss is KiB.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = [score for score in candidate["scores"] if score["method"] == "glrt64"]
    if len(scores) != 1:
        raise ValueError("candidate does not have exactly one GLRT64 score")
    return scores[0]


def trajectory_cfo(trajectory: dict[str, Any], time_s: float) -> float:
    coefficients = tuple(float(value) for value in trajectory["absolute_coefficients_hz"])
    if len(coefficients) != 2 or int(trajectory["polynomial_degree"]) != 1:
        raise ValueError("long-locklet runner requires a persisted degree-one trajectory")
    slope, at_reference = coefficients
    return at_reference + slope * (time_s - float(trajectory["reference_time_s"]))


def select_trajectory(
    bank: dict[str, Any], *, interval_start_s: float, interval_stop_s: float
) -> dict[str, Any]:
    eligible = [
        value
        for value in bank["trajectories"]
        if float(value["start_s"]) <= interval_start_s
        and float(value["end_s"]) >= interval_stop_s
        and bool(value["automatic_correction_eligible"])
        and bool(value["geometry_display_eligible"])
        and float(value["median_block_corrected_margin"]) >= 0.1
        and int(value["polynomial_degree"]) == 1
    ]
    if not eligible:
        raise ValueError("no independently persisted strong degree-one trajectory covers interval")
    return max(
        eligible,
        key=lambda value: (
            float(value["end_s"]) - float(value["start_s"]),
            float(value["median_block_corrected_margin"]),
            str(value["trajectory_id"]),
        ),
    )


Match = tuple[dict[str, Any], dict[str, Any], dict[str, Any]]


def matching_candidates(
    scan: dict[str, Any],
    trajectory: dict[str, Any],
    *,
    interval_start: int,
    interval_stop: int,
) -> list[Match]:
    output: list[Match] = []
    for detection in scan["detections"]:
        if detection["status"] != "complete":
            continue
        start = int(detection["sample_start"])
        if start < interval_start or start + PROBE_SAMPLES > interval_stop:
            continue
        target = trajectory_cfo(trajectory, float(detection["time_s"]))
        for candidate in detection["candidates"]:
            score = glrt_score(candidate)
            if (
                int(candidate["rank"]) <= 2
                and 0 <= int(candidate["local_epoch_sample"]) < math.ceil(FRAME_PERIOD)
                and float(score["margin"]) >= 0.05
                and float(score["exact_score"]) >= 0.02
                and abs(float(score["tracking_cfo_hz"]) - target) <= 2_000.0
            ):
                output.append((detection, candidate, score))
    if not output:
        raise ValueError("no trajectory-consistent GLRT candidate in requested interval")
    return output


def match_key(value: Match) -> tuple[float, float, int, int, int]:
    detection, candidate, score = value
    return (
        float(score["margin"]),
        float(score["exact_score"]),
        -int(candidate["rank"]),
        -int(detection["sample_start"]),
        -int(candidate["local_epoch_sample"]),
    )


def match_candidate(value: Match) -> GlrtAnchorCandidate:
    detection, candidate, score = value
    return GlrtAnchorCandidate(
        detection_sample_start=int(detection["sample_start"]),
        candidate_rank=int(candidate["rank"]),
        local_epoch_sample=int(candidate["local_epoch_sample"]),
        tracking_cfo_hz=float(score["tracking_cfo_hz"]),
        exact_score=float(score["exact_score"]),
        control_score=float(score["control_score"]),
        margin=float(score["margin"]),
    )


def select_refresh_matches(
    matches: list[Match],
    *,
    interval_start: int,
    interval_stop: int,
    refresh_samples: int,
) -> list[tuple[Match, int, int, str]]:
    """Select acquisition evidence before each causal refresh deadline."""

    selection_window = min(refresh_samples, round(0.100 * SAMPLE_RATE_HZ))

    def select(start: int, stop: int) -> Match | None:
        eligible = [
            value
            for value in matches
            if int(value[0]["sample_start"]) >= start
            and int(value[0]["sample_start"]) + PROBE_SAMPLES <= stop
        ]
        return max(eligible, key=match_key) if eligible else None

    first_stop = min(interval_stop, interval_start + selection_window)
    first = select(interval_start, first_stop)
    if first is None:
        raise ValueError("no trajectory-consistent anchor completes in first selection window")
    selected = [(first, interval_start, first_stop, "initial")]
    deadline = interval_start + refresh_samples
    while deadline < interval_stop:
        window_start = max(interval_start, deadline - selection_window)
        value = select(window_start, deadline)
        if value is not None:
            selected.append((value, window_start, deadline, "refresh"))
        deadline += refresh_samples

    # Acquisition completion is the earliest moment a refresh may own frames.
    selected.sort(key=lambda value: int(value[0][0]["sample_start"]) + PROBE_SAMPLES)
    deduplicated: list[tuple[Match, int, int, str]] = []
    seen: set[tuple[int, int]] = set()
    for value in selected:
        identity = (int(value[0][0]["sample_start"]), int(value[0][1]["rank"]))
        if identity not in seen:
            seen.add(identity)
            deduplicated.append(value)
    return deduplicated


def build_owned_anchors(
    selected: list[tuple[Match, int, int, str]],
    trajectory: dict[str, Any],
    *,
    interval_start: int,
    interval_stop: int,
) -> tuple[tuple[OwnedAnchor, ...], list[dict[str, Any]]]:
    candidates = [match_candidate(value[0]) for value in selected]
    ownership_starts = [interval_start]
    ownership_starts.extend(
        value.detection_sample_start + PROBE_SAMPLES for value in candidates[1:]
    )
    if ownership_starts != sorted(ownership_starts) or len(set(ownership_starts)) != len(
        ownership_starts
    ):
        raise ValueError("anchor acquisition completions are not strictly ordered")
    ownership_stops = ownership_starts[1:] + [interval_stop]
    owned: list[OwnedAnchor] = []
    documents: list[dict[str, Any]] = []
    trajectory_id = str(trajectory["trajectory_id"])
    for index, (candidate, selection, start, stop) in enumerate(
        zip(candidates, selected, ownership_starts, ownership_stops, strict=True)
    ):
        if start >= stop:
            raise ValueError("anchor ownership interval is empty")
        anchor = FrameRecoveryAnchor(
            anchor_id=f"persisted-branch-anchor-{index:03d}",
            sample_source_id=f"{SESSION_ID}:{STREAM_ID}:receiver-{RECEIVER_ID}",
            canonical_observation_id=trajectory_id,
            source_observation_id=(
                f"sample-{candidate.detection_sample_start}:"
                f"rank-{candidate.candidate_rank}:glrt64"
            ),
            continuity_source_id=trajectory_id,
            edge=EDGE,
            cfo_alias_index=int(trajectory["alias_index"]),
            epoch_sample=(
                candidate.detection_sample_start + candidate.local_epoch_sample
            ),
            acquisition_absolute_cfo_hz=candidate.tracking_cfo_hz,
            ownership_start_sample=start,
            ownership_stop_sample=stop,
        )
        owned.append(
            OwnedAnchor(
                anchor=anchor,
                segment_start_sample=start,
                segment_stop_sample=stop,
                acquisition_start_sample=candidate.detection_sample_start,
                acquisition_stop_sample=candidate.detection_sample_start + PROBE_SAMPLES,
                candidate=candidate,
            )
        )
        documents.append(
            {
                "anchor_id": anchor.anchor_id,
                "role": selection[3],
                "selection_window_start_sample": selection[1],
                "selection_window_stop_sample": selection[2],
                "ownership_start_sample": start,
                "ownership_stop_sample": stop,
                "acquisition_start_sample": candidate.detection_sample_start,
                "acquisition_stop_sample": candidate.detection_sample_start + PROBE_SAMPLES,
                "candidate_rank": candidate.candidate_rank,
                "local_epoch_sample": candidate.local_epoch_sample,
                "absolute_epoch_sample": anchor.epoch_sample,
                "tracking_cfo_hz": candidate.tracking_cfo_hz,
                "exact_score": candidate.exact_score,
                "control_score": candidate.control_score,
                "margin": candidate.margin,
            }
        )
    return tuple(owned), documents


def complex_receiver_into(destination: np.ndarray, values: np.ndarray) -> None:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("unexpected one-receiver CI16 shape")
    if destination.shape != (values.shape[0],):
        raise ValueError("destination and CI16 sample counts disagree")
    destination.real = values[:, 0, 0]
    destination.imag = values[:, 0, 1]
    destination /= 2**15


def rms(values: list[float]) -> float | None:
    return None if not values else float(np.sqrt(np.mean(np.square(values))))


def error_summary(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    data = np.asarray(values, dtype=float)
    return {
        "count": len(values),
        "mean_hz": float(np.mean(data)),
        "rms_hz": float(np.sqrt(np.mean(np.square(data)))),
        "median_absolute_hz": float(np.median(np.abs(data))),
        "p95_absolute_hz": float(np.percentile(np.abs(data), 95)),
        "maximum_absolute_hz": float(np.max(np.abs(data))),
    }


def mark_all_acquisition_overlaps(
    rows: list[dict[str, Any]], owned: tuple[OwnedAnchor, ...]
) -> None:
    spans = tuple(
        (value.acquisition_start_sample, value.acquisition_stop_sample) for value in owned
    )
    for row in rows:
        start = int(row["frame_start_sample"])
        stop = start + FRAME_CONTENT_SAMPLES
        overlap = any(start < right and stop > left for left, right in spans)
        row["any_selected_acquisition_overlap"] = overlap
        if overlap:
            row["odd_scored"] = False


def block_metrics(
    rows: list[dict[str, Any]], *, interval_start_s: float, block_s: float
) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["odd_scored"] and row["trailing_20ms_scored"]:
            index = max(
                0,
                math.floor((float(row["reference_time_s"]) - interval_start_s) / block_s),
            )
            grouped[index].append(row)
    output = []
    for index, values in sorted(grouped.items()):
        filter_errors = [float(value["odd_prediction_error_hz"]) for value in values]
        line_errors = [float(value["trailing_20ms_odd_error_hz"]) for value in values]
        filter_rms = rms(filter_errors)
        line_rms = rms(line_errors)
        output.append(
            {
                "block_index": index,
                "time_start_s": interval_start_s + index * block_s,
                "time_stop_s": interval_start_s + (index + 1) * block_s,
                "common_frame_count": len(values),
                "filter_rms_hz": filter_rms,
                "trailing_line_rms_hz": line_rms,
                "filter_to_line_ratio": (
                    None
                    if filter_rms is None or line_rms is None or line_rms == 0.0
                    else filter_rms / line_rms
                ),
            }
        )
    return output


def summarize(
    rows: list[dict[str, Any]],
    *,
    result: Any,
    refill_boundaries: tuple[int, ...],
    interval_start_s: float,
    summary_block_s: float,
) -> dict[str, Any]:
    outcomes = Counter(str(row["outcome"]) for row in rows)
    modes = Counter(str(row["mode"]) for row in rows)
    odd_rows = [row for row in rows if row["odd_scored"]]
    common = [row for row in odd_rows if row["trailing_20ms_scored"]]
    filter_errors = [float(row["odd_prediction_error_hz"]) for row in common]
    baseline_errors = [float(row["trailing_20ms_odd_error_hz"]) for row in common]
    filter_rms = rms(filter_errors)
    baseline_rms = rms(baseline_errors)
    blocks = block_metrics(
        rows, interval_start_s=interval_start_s, block_s=summary_block_s
    )
    ratios = [
        float(value["filter_to_line_ratio"])
        for value in blocks
        if value["filter_to_line_ratio"] is not None
    ]
    return {
        "opportunity_count": len(rows),
        "outcome_counts": dict(sorted(outcomes.items())),
        "mode_counts": dict(sorted(modes.items())),
        "supported_frame_count": outcomes[FrameOpportunityOutcome.SUPPORTED.value],
        "filter_accepted_count": sum(bool(row["filter_accepted"]) for row in rows),
        "predicted_only_coast_count": sum(bool(row["predicted_only"]) for row in rows),
        "primary_diagnostic_supported_count": sum(
            row["primary_supported"] is True for row in rows
        ),
        "primary_diagnostic_evaluated_count": sum(
            row["primary_supported"] is not None for row in rows
        ),
        "locklet_count": len(result.locklets),
        "locklet_end_reason_counts": dict(
            sorted(Counter(value.ended_by.value for value in result.locklets).items())
        ),
        "hard_split_row_reason_counts": dict(
            sorted(
                Counter(
                    str(row["split_reason"])
                    for row in rows
                    if row["hard_split_before"] and row["split_reason"] is not None
                ).items()
            )
        ),
        "refill_audit_marker_count": len(refill_boundaries),
        "selected_acquisition_overlap_frame_count": sum(
            bool(row["any_selected_acquisition_overlap"]) for row in rows
        ),
        "pre_initial_acquisition_backprojected_frame_count": sum(
            bool(row["pre_acquisition_backprojection"]) for row in rows
        ),
        "conditional_odd_fold_error": error_summary(
            [float(row["odd_prediction_error_hz"]) for row in odd_rows]
        ),
        "common_mask_trailing_20ms": {
            "frame_count": len(common),
            "filter_error": error_summary(filter_errors),
            "causal_trailing_line_error": error_summary(baseline_errors),
            "filter_to_line_rms_ratio": (
                None
                if filter_rms is None or baseline_rms is None or baseline_rms == 0.0
                else filter_rms / baseline_rms
            ),
            "summary_block_s": summary_block_s,
            "block_count": len(blocks),
            "median_block_filter_to_line_ratio": (
                None if not ratios else float(np.median(ratios))
            ),
            "filter_win_block_count": sum(value < 1.0 for value in ratios),
            "blocks": blocks,
        },
        "conditional_scope": (
            "odd Qin is excluded from each frame update and scored pre-update, but all-Qin "
            "GLRT64 and the persisted trajectory selected the anchor sequence; this is "
            "conditional fold-heldout evidence, not end-to-end untouched validation"
        ),
        "occupancy_status": (
            "unknown; estimator no-result/rejection is not an independent absence decision"
        ),
    }


def lattice_evidence(matches: list[Match], *, reference_epoch: int) -> dict[str, Any]:
    by_detection: dict[int, Match] = {}
    for value in matches:
        start = int(value[0]["sample_start"])
        current = by_detection.get(start)
        if current is None or match_key(value) > match_key(current):
            by_detection[start] = value
    residuals = []
    for detection, candidate, _score in by_detection.values():
        epoch = int(detection["sample_start"]) + int(candidate["local_epoch_sample"])
        lattice_index = round((epoch - reference_epoch) / FRAME_PERIOD)
        residuals.append(epoch - (reference_epoch + lattice_index * FRAME_PERIOD))
    absolute = np.abs(np.asarray(residuals, dtype=float))
    return {
        "detection_count": len(residuals),
        "median_absolute_lattice_residual_samples": float(np.median(absolute)),
        "p95_absolute_lattice_residual_samples": float(np.percentile(absolute, 95)),
        "maximum_absolute_lattice_residual_samples": float(np.max(absolute)),
    }


def nearest_lattice_sample(epoch_sample: int, sample: int) -> int:
    approximate = round((sample - epoch_sample) * 750 / SAMPLE_RATE_HZ)
    candidates = tuple(
        epoch_sample + round((approximate + offset) * SAMPLE_RATE_HZ / 750)
        for offset in (-1, 0, 1)
    )
    return min(candidates, key=lambda value: (abs(value - sample), value))


def adjacent_anchor_epoch_evidence(owned: tuple[OwnedAnchor, ...]) -> dict[str, Any]:
    rows = []
    for left, right in zip(owned, owned[1:], strict=False):
        boundary = right.anchor.ownership_start_sample
        left_lattice = nearest_lattice_sample(left.anchor.epoch_sample, boundary)
        right_lattice = nearest_lattice_sample(right.anchor.epoch_sample, boundary)
        rows.append(
            {
                "left_anchor_id": left.anchor.anchor_id,
                "right_anchor_id": right.anchor.anchor_id,
                "boundary_sample": boundary,
                "left_nearest_lattice_sample": left_lattice,
                "right_nearest_lattice_sample": right_lattice,
                "signed_epoch_adjustment_samples": right_lattice - left_lattice,
            }
        )
    absolute = np.abs(
        np.asarray([value["signed_epoch_adjustment_samples"] for value in rows], dtype=float)
    )
    return {
        "pair_count": len(rows),
        "maximum_absolute_adjustment_samples": (
            None if not len(absolute) else float(np.max(absolute))
        ),
        "p95_absolute_adjustment_samples": (
            None if not len(absolute) else float(np.percentile(absolute, 95))
        ),
        "rows": rows,
    }


def boundary_cfo_evidence(
    rows: list[dict[str, Any]], refill_boundaries: tuple[int, ...]
) -> dict[str, Any]:
    supported = sorted(
        (
            row
            for row in rows
            if row["outcome"] == FrameOpportunityOutcome.SUPPORTED.value
            and row["even_absolute_cfo_hz"] is not None
        ),
        key=lambda row: float(row["reference_sample"]),
    )
    deltas = np.asarray(
        [
            float(right["even_absolute_cfo_hz"] - left["even_absolute_cfo_hz"])
            for left, right in zip(supported, supported[1:], strict=False)
        ],
        dtype=float,
    )
    crossings = []
    cursor = 0
    for boundary in refill_boundaries:
        while (
            cursor + 1 < len(supported)
            and float(supported[cursor + 1]["reference_sample"]) < boundary
        ):
            cursor += 1
        if cursor + 1 >= len(supported):
            break
        left, right = supported[cursor], supported[cursor + 1]
        if float(left["reference_sample"]) < boundary <= float(right["reference_sample"]):
            crossings.append(
                {
                    "boundary_sample": boundary,
                    "boundary_time_s": boundary / SAMPLE_RATE_HZ,
                    "left_reference_sample": left["reference_sample"],
                    "right_reference_sample": right["reference_sample"],
                    "reference_gap_s": (
                        float(right["reference_sample"])
                        - float(left["reference_sample"])
                    )
                    / SAMPLE_RATE_HZ,
                    "even_cfo_delta_hz": float(
                        right["even_absolute_cfo_hz"]
                        - left["even_absolute_cfo_hz"]
                    ),
                }
            )
    boundary_deltas = np.asarray(
        [value["even_cfo_delta_hz"] for value in crossings], dtype=float
    )
    return {
        "refill_marker_count": len(refill_boundaries),
        "scored_crossing_count": len(crossings),
        "median_boundary_delta_hz": (
            None if not len(boundary_deltas) else float(np.median(boundary_deltas))
        ),
        "p95_absolute_boundary_delta_hz": (
            None
            if not len(boundary_deltas)
            else float(np.percentile(np.abs(boundary_deltas), 95))
        ),
        "maximum_absolute_boundary_delta_hz": (
            None if not len(boundary_deltas) else float(np.max(np.abs(boundary_deltas)))
        ),
        "all_adjacent_delta_median_hz": (
            None if not len(deltas) else float(np.median(deltas))
        ),
        "all_adjacent_delta_p95_absolute_hz": (
            None if not len(deltas) else float(np.percentile(np.abs(deltas), 95))
        ),
        "crossings": crossings,
    }


def validate_arguments(args: argparse.Namespace) -> tuple[int, int, int, int]:
    values = (args.start_s, args.stop_s, args.read_chunk_s, args.anchor_refresh_s)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("time arguments must be finite")
    if args.start_s < 0 or args.stop_s <= args.start_s:
        raise ValueError("interval must be positive and ordered")
    if args.stop_s - args.start_s > MAXIMUM_INTERVAL_S:
        raise ValueError(f"interval exceeds frozen {MAXIMUM_INTERVAL_S:g} s safety bound")
    if args.read_chunk_s <= 0 or args.read_chunk_s > 1.0:
        raise ValueError("read chunks must lie in (0, 1] seconds")
    if args.anchor_refresh_s < 0.1 or args.anchor_refresh_s > 2.0:
        raise ValueError("anchor refresh must lie in [0.1, 2] seconds")
    if not math.isfinite(args.summary_block_s) or args.summary_block_s <= 0:
        raise ValueError("summary block duration must be positive")
    if not 0 <= args.anchor_epoch_tolerance_samples <= 50:
        raise ValueError("anchor epoch tolerance must lie in 0..50 samples")
    start = round(args.start_s * SAMPLE_RATE_HZ)
    stop = round(args.stop_s * SAMPLE_RATE_HZ)
    read_chunk = round(args.read_chunk_s * SAMPLE_RATE_HZ)
    refresh = round(args.anchor_refresh_s * SAMPLE_RATE_HZ)
    if start >= stop or read_chunk <= 0 or refresh <= PROBE_SAMPLES:
        raise ValueError("time arguments do not map to valid sample geometry")
    return start, stop, read_chunk, refresh


def main() -> None:
    args = arguments()
    interval_start, interval_stop, read_chunk_samples, refresh_samples = validate_arguments(
        args
    )
    interval_samples = interval_stop - interval_start
    interval_start_s = interval_start / SAMPLE_RATE_HZ
    interval_stop_s = interval_stop / SAMPLE_RATE_HZ
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"output root is nonempty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    recording_manifest = load(RECORDING_MANIFEST)
    analysis_manifest = load(ANALYSIS_MANIFEST)
    scan = load(PILOT_SCAN)
    bank = load(TRAJECTORY_BANK)
    stream = next(
        value for value in recording_manifest["streams"] if value["stream_id"] == STREAM_ID
    )
    continuity = stream["continuity"]
    if not (
        recording_manifest["schema_version"] == 2
        and continuity["schema_version"] == 2
        and continuity["sample_loss_observable"]
        and continuity["gap_count"] == 0
        and continuity["missing_sample_count"] == 0
        and continuity["overflow_count"] == 0
        and continuity["device_span_sample_count"] == continuity["observed_sample_count"]
        and continuity["observed_sample_count"] == 150_000_000
    ):
        raise ValueError("requested recording lacks counter-authoritative continuity")
    products = [
        value
        for value in analysis_manifest["products"]
        if value["kind"] == "standard.pilot-scan"
        and value["scope_key"] == SCOPE
        and value["status"] == "complete"
    ]
    if len(products) != 1 or products[0]["digest"] != f"sha256:{sha256(PILOT_SCAN)}":
        raise ValueError("pilot scan is not bound to requested analysis scope")

    trajectory = select_trajectory(
        bank, interval_start_s=interval_start_s, interval_stop_s=interval_stop_s
    )
    matches = matching_candidates(
        scan,
        trajectory,
        interval_start=interval_start,
        interval_stop=interval_stop,
    )
    selected = select_refresh_matches(
        matches,
        interval_start=interval_start,
        interval_stop=interval_stop,
        refresh_samples=refresh_samples,
    )
    owned, anchor_documents = build_owned_anchors(
        selected,
        trajectory,
        interval_start=interval_start,
        interval_stop=interval_stop,
    )
    recovery_config = FrameRecoveryConfig(
        maximum_anchor_epoch_error_samples=args.anchor_epoch_tolerance_samples
    )
    compatibility = [
        anchors_compatible(
            left.anchor,
            right.anchor,
            sample_rate_hz=SAMPLE_RATE_HZ,
            config=recovery_config,
        )
        for left, right in zip(owned, owned[1:], strict=False)
    ]

    memmap_bytes = interval_samples * np.dtype(np.complex128).itemsize
    free_bytes = shutil.disk_usage("/tmp").free
    if free_bytes < memmap_bytes + 512 * 1024**2:
        raise ValueError("insufficient /tmp space for bounded IQ memmap and safety reserve")

    read_chunks = []
    runtime_start = time.perf_counter()
    rss_before_mib = maximum_rss_mib()
    store: RecordingStore | None = None
    result: Any
    with tempfile.TemporaryDirectory(prefix="leo-long-recovery-", dir="/tmp") as temporary:
        memmap_path = Path(temporary) / "iq.complex128"
        iq = np.memmap(
            memmap_path,
            dtype=np.complex128,
            mode="w+",
            shape=(interval_samples,),
        )
        try:
            store = RecordingStore.open_pinned(PinnedLocalRoot(Path("/srv/bulk/leo")))
            bundle = store.inspect(SESSION_ID)
            reader = store.reader(bundle, STREAM_ID, verify=True)
            if reader.sample_rate_hz != SAMPLE_RATE_HZ or RECEIVER_ID not in reader.receiver_ids:
                raise ValueError("recording geometry disagrees with frozen runner")
            if reader.gap_map().boundaries:
                raise ValueError("counter-authoritative recording unexpectedly has gap boundaries")
            timeline = tuple(reader.iter_timeline_metadata())
            refill_boundaries = tuple(
                value.session_sample_start
                for value in timeline[1:]
                if interval_start < value.session_sample_start < interval_stop
            )
            overlapping = tuple(
                value
                for value in timeline
                if value.session_sample_start < interval_stop
                and value.session_sample_start + value.sample_count > interval_start
            )
            if not all(
                value.continuity.value == "contiguous"
                and value.missing_samples_before == 0
                and not value.overflow_observed
                for value in overlapping
            ):
                raise ValueError("interval contains a non-contiguous counter record")
            cursor = interval_start
            chunk_index = 0
            while cursor < interval_stop:
                count = min(read_chunk_samples, interval_stop - cursor)
                started = time.perf_counter()
                raw = reader.read(cursor, count, receiver_ids=(RECEIVER_ID,))
                complex_receiver_into(
                    iq[cursor - interval_start : cursor - interval_start + count], raw
                )
                elapsed = time.perf_counter() - started
                read_chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "sample_start": cursor,
                        "sample_count": count,
                        "read_and_convert_runtime_s": elapsed,
                    }
                )
                cursor += count
                chunk_index += 1
                if chunk_index == 1 or chunk_index % 10 == 0 or cursor == interval_stop:
                    print(
                        f"read {cursor - interval_start:,}/{interval_samples:,} samples "
                        f"in {chunk_index} verified chunks",
                        flush=True,
                    )
        finally:
            if store is not None:
                store.close()
        iq.flush()
        rss_after_read_mib = maximum_rss_mib()
        compute_started = time.perf_counter()
        # No refill reset: these V2 counter-authoritative records are retained as
        # diagnostic markers and evaluated below for boundary-local CFO jumps.
        result = recover_contiguous_frames(
            iq,
            sample_start=interval_start,
            sample_rate_hz=SAMPLE_RATE_HZ,
            anchors=tuple(value.anchor for value in owned),
            refill_boundaries=(),
            config=recovery_config,
        )
        compute_runtime_s = time.perf_counter() - compute_started
        rss_after_recovery_mib = maximum_rss_mib()
        del iq

    by_anchor = {value.anchor.anchor_id: value for value in owned}
    rows = [
        _frame_document(
            "N1",
            frame,
            by_anchor[frame.anchor_id],
            sample_rate_hz=SAMPLE_RATE_HZ,
        )
        for frame in result.frames
    ]
    mark_all_acquisition_overlaps(rows, owned)
    add_trailing_line_predictions(rows)
    summary = summarize(
        rows,
        result=result,
        refill_boundaries=refill_boundaries,
        interval_start_s=interval_start_s,
        summary_block_s=args.summary_block_s,
    )

    rows_path = output_root / "frame-rows.jsonl"
    with rows_path.open("w", encoding="utf-8") as destination:
        for row in rows:
            destination.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    total_runtime_s = time.perf_counter() - runtime_start
    evidence = {
        "schema": "org.leo.research.chunked-long-continuity-probe/v1",
        "candidate_only": True,
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "scope_sha256": SCOPE,
        "stream_id": STREAM_ID,
        "receiver_id": RECEIVER_ID,
        "edge": EDGE.value,
        "interval": {
            "sample_start": interval_start,
            "sample_stop": interval_stop,
            "sample_count": interval_samples,
            "time_start_s": interval_start_s,
            "time_stop_s": interval_stop_s,
            "duration_s": (interval_stop - interval_start) / SAMPLE_RATE_HZ,
        },
        "trajectory": {
            key: trajectory[key]
            for key in (
                "trajectory_id",
                "branch_id",
                "alias_index",
                "reference_time_s",
                "absolute_coefficients_hz",
                "polynomial_degree",
                "start_s",
                "end_s",
                "median_block_corrected_margin",
                "block_coverage_ratio",
                "harmful_block_count",
            )
        },
        "selection_rule": (
            "within the persisted strong degree-one final trajectory, choose the maximum-"
            "margin rank<=2 GLRT64 candidate (margin>=0.05, exact>=0.02, within 2 kHz "
            "of the trajectory) that completes in the first 100 ms and before each "
            "periodic refresh deadline; refreshed anchors own frames only after their "
            "20 ms all-Qin acquisition probe completes"
        ),
        "anchor_refresh_s": args.anchor_refresh_s,
        "anchor_epoch_tolerance_samples": args.anchor_epoch_tolerance_samples,
        "anchor_epoch_tolerance_s": (
            args.anchor_epoch_tolerance_samples / SAMPLE_RATE_HZ
        ),
        "anchors": anchor_documents,
        "adjacent_anchor_pair_count": len(compatibility),
        "compatible_adjacent_anchor_pair_count": sum(compatibility),
        "incompatible_adjacent_anchor_pair_count": sum(not value for value in compatibility),
        "matching_candidate_count": len(matches),
        "lattice_evidence": lattice_evidence(
            matches, reference_epoch=owned[0].anchor.epoch_sample
        ),
        "adjacent_anchor_epoch_evidence": adjacent_anchor_epoch_evidence(owned),
        "counter_continuity": continuity,
        "timeline_record_count": len(overlapping),
        "refill_audit_boundary_samples": list(refill_boundaries),
        "boundary_cfo_evidence": boundary_cfo_evidence(rows, refill_boundaries),
        "result": summary,
        "memory_bounding": {
            "maximum_interval_s": MAXIMUM_INTERVAL_S,
            "read_chunk_s": args.read_chunk_s,
            "read_chunk_samples": read_chunk_samples,
            "read_chunk_count": len(read_chunks),
            "memmap_bytes": memmap_bytes,
            "temporary_memmap_deleted": True,
            "rss_before_mib": rss_before_mib,
            "rss_after_read_mib": rss_after_read_mib,
            "rss_after_recovery_mib": rss_after_recovery_mib,
            "note": (
                "IQ heap use is bounded by one verified CI16 read chunk; the core's frame "
                "result ledger remains O(frame count) within the frozen 15 s interval cap"
            ),
        },
        "runtime": {
            "verified_read_and_convert_s": sum(
                value["read_and_convert_runtime_s"] for value in read_chunks
            ),
            "continuous_recovery_compute_s": compute_runtime_s,
            "total_s": total_runtime_s,
        },
        "artifacts": {
            "frame_rows_path": str(rows_path),
            "frame_rows_sha256": sha256(rows_path),
            "frame_rows_bytes": rows_path.stat().st_size,
        },
        "input_sha256": {
            "recording_manifest": sha256(RECORDING_MANIFEST),
            "analysis_manifest": sha256(ANALYSIS_MANIFEST),
            "pilot_scan": sha256(PILOT_SCAN),
            "final_trajectory_bank": sha256(TRAJECTORY_BANK),
        },
        "interpretation_limits": [
            (
                "exploratory interval chosen inside an existing strong persisted "
                "trajectory, not an untouched promotion holdout"
            ),
            (
                "odd-Qin errors are pre-update fold-heldout conditional on all-Qin "
                "GLRT64 acquisition and persisted trajectory/anchor selection"
            ),
            (
                "the trajectory is candidate-only and is not a confirmed physical "
                "transmitter identity"
            ),
            (
                "the 4-sample anchor-epoch tolerance is an exploratory setting chosen "
                "after observing this branch's 0-to-4-sample adjacent refresh drift; "
                "it is not a frozen promotion parameter"
            ),
            "frame support is not an independent signal-occupancy measurement",
            (
                "counter-authoritative application refill records are audit markers, "
                "not filter resets in this run"
            ),
            "phase is neither estimated nor fed back",
            (
                "the core has no external continuation-state API; the memmap permits "
                "one exact uninterrupted call without holding all IQ on heap"
            ),
        ],
    }
    evidence_path = output_root / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "evidence.json": {
            "sha256": sha256(evidence_path),
            "bytes": evidence_path.stat().st_size,
        },
        "frame-rows.jsonl": {
            "sha256": sha256(rows_path),
            "bytes": rows_path.stat().st_size,
        },
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output_root": str(output_root), **summary}, indent=2))


if __name__ == "__main__":
    main()
