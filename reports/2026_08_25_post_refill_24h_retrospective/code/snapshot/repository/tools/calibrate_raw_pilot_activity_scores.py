#!/usr/bin/env python3
"""Calibrate binary GLRT64-margin activity costs from frozen inventories.

Null inputs are complete ``standard.pilot-scan.v3.json`` products.  Positive
inputs are ``PATH COMPONENT_ID`` pairs naming one resolved alias component in
a full duration-constrained assignment input.  The output is a compact,
deterministic research artifact; it is not a detector qualification or a
spacecraft-identification result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.analysis.research.satellite_activity_scores import (  # type: ignore[import-untyped]
    ConservativeRankMarkCalibration,
    ConservativeRankMarkedPilotScoreCalibration,
    PilotScoreEvidence,
    PilotScoreGroup,
    group_pilot_score_evidence,
    poisson_count_upper_mean,
    wilson_probability_lower,
)

SCHEMA = "org.leo.research.raw-pilot-activity-score-calibration/v3"
DURATION_INPUT_SCHEMA = "org.leo.research.duration-constrained-satellite-assignment-input/v1"
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
QNAP_ROOT = Path("/mnt/qnap01")
RANK_BUCKET_SPECS: tuple[tuple[str, int, int | None], ...] = (
    ("rank0", 0, 0),
    ("rank1", 1, 1),
    ("rank2_4", 2, 4),
    ("rank5_plus", 5, None),
)


@dataclass(frozen=True, slots=True)
class SourceInventory:
    source: dict[str, Any]
    groups: tuple[PilotScoreGroup, ...]
    source_scan_digest: str
    raw_row_count: int
    deduplicated_row_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--null-scan",
        type=Path,
        action="append",
        required=True,
        help="complete standard.pilot-scan.v3.json null inventory; repeat as needed",
    )
    parser.add_argument(
        "--positive-component",
        nargs=2,
        action="append",
        required=True,
        metavar=("PATH", "COMPONENT_ID"),
        help="full duration-input JSON and resolved positive component ID; repeat as needed",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.1,
        help="positive threshold for GLRT64 exact-minus-control margin",
    )
    parser.add_argument("--detection-probability", type=float, default=0.75)
    parser.add_argument(
        "--familywise-alpha",
        type=float,
        default=0.05,
        help="simultaneous error budget for conservative null/signal feature bounds",
    )
    parser.add_argument("--resolution-epoch-tolerance-samples", type=int, default=1)
    parser.add_argument("--resolution-tracking-cfo-tolerance-hz", type=float, default=500.0)
    parser.add_argument("--duplicate-acquired-cfo-tolerance-hz", type=float, default=0.0)
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON here instead of stdout; paths below /mnt/qnap01 are refused",
    )
    return parser.parse_args()


def _read_object(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value, "sha256:" + hashlib.sha256(payload).hexdigest()


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _sha256_digest(value: object, label: str) -> str:
    result = _string(value, label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ValueError(f"{label} must be a lowercase sha256 digest")
    return result


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _glrt64_fields(candidate: dict[str, Any], label: str) -> tuple[float, float]:
    scores = _list(candidate.get("scores"), f"{label} scores")
    glrt64 = [
        _dict(score, f"{label} score")
        for score in scores
        if isinstance(score, dict) and score.get("method") == "glrt64"
    ]
    if len(glrt64) != 1:
        raise ValueError(f"{label} must contain exactly one GLRT64 score")
    exact = _finite_number(glrt64[0].get("exact_score"), f"{label} GLRT64 exact score")
    control = _finite_number(glrt64[0].get("control_score"), f"{label} GLRT64 control score")
    margin = _finite_number(glrt64[0].get("margin"), f"{label} GLRT64 margin")
    tracking_cfo_hz = _finite_number(
        glrt64[0].get("tracking_cfo_hz"),
        f"{label} GLRT64 tracking CFO",
    )
    if not math.isclose(margin, exact - control, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"{label} GLRT64 margin is inconsistent with exact minus control")
    return margin, tracking_cfo_hz


def _null_inventory(
    path: Path,
    threshold: float,
    *,
    epoch_tolerance_samples: int,
    tracking_cfo_tolerance_hz: float,
    acquired_cfo_tolerance_hz: float,
) -> SourceInventory:
    resolved = path.resolve(strict=True)
    document, file_digest = _read_object(resolved)
    if (
        document.get("schema_version") != 3
        or document.get("algorithm_version") != "standard-pilot-scan-v3"
    ):
        raise ValueError(f"expected a standard-pilot-scan-v3 schema V3 input: {resolved}")
    if document.get("frequency_coordinate") != "baseband_cfo_hz":
        raise ValueError(f"null scan is not in the baseband CFO coordinate: {resolved}")
    if document.get("frequency_reference") != "uncalibrated_prior":
        raise ValueError(
            f"null scan unexpectedly claims calibrated frequency authority: {resolved}"
        )
    if (
        document.get("candidate_only") is not True
        or document.get("specificity_claimed") is not False
        or document.get("payload_decoded") is not False
    ):
        raise ValueError(
            f"null scan does not carry the expected candidate-only caveats: {resolved}"
        )

    schedule_digest = _sha256_digest(
        document.get("probe_schedule_digest"), "null probe schedule digest"
    )
    maximum_candidates = _integer(
        document.get("maximum_scored_candidates_per_probe"),
        "maximum scored candidates per probe",
        minimum=1,
    )
    evidence: list[PilotScoreEvidence] = []
    row_identities: set[tuple[int, int]] = set()
    previous_sample_start = -1
    detections = _list(document.get("detections"), "null detections")
    for detection_index, raw_detection in enumerate(detections):
        label = f"null detection {detection_index}"
        detection = _dict(raw_detection, label)
        sample_start = _integer(detection.get("sample_start"), f"{label} sample start")
        if sample_start <= previous_sample_start:
            raise ValueError("null detections must be uniquely ordered by sample start")
        previous_sample_start = sample_start
        if (
            _integer(
                detection.get("truncated_candidate_count"), f"{label} truncated candidate count"
            )
            != 0
        ):
            raise ValueError("truncated null pilot-scan input is refused")
        candidates = _list(detection.get("candidates"), f"{label} candidates")
        source_count = _integer(
            detection.get("source_candidate_count"), f"{label} source candidate count"
        )
        if source_count != len(candidates):
            raise ValueError(f"{label} candidate count does not match its source count")
        expected_status = "complete" if candidates else "no_result"
        if detection.get("status") != expected_status:
            raise ValueError(f"{label} status is inconsistent with its candidate rows")
        for expected_rank, raw_candidate in enumerate(candidates):
            candidate_label = f"{label} candidate {expected_rank}"
            candidate = _dict(raw_candidate, candidate_label)
            rank = _integer(candidate.get("rank"), f"{candidate_label} rank")
            if rank != expected_rank:
                raise ValueError(f"{label} candidate ranks must be contiguous from zero")
            identity = (sample_start, rank)
            if identity in row_identities:
                raise ValueError("null GLRT64 row identity is not unique")
            row_identities.add(identity)
            local_epoch_sample = _integer(
                candidate.get("local_epoch_sample"),
                f"{candidate_label} local epoch sample",
            )
            margin, tracking_cfo_hz = _glrt64_fields(candidate, candidate_label)
            acquired_cfo_hz = _finite_number(
                candidate.get("acquired_cfo_hz"),
                f"{candidate_label} acquired CFO",
            )
            evidence.append(
                PilotScoreEvidence(
                    evidence_id=f"{sample_start}:{rank}",
                    probe_id=str(sample_start),
                    rank=rank,
                    local_epoch_sample=local_epoch_sample,
                    tracking_cfo_hz=tracking_cfo_hz,
                    score=margin,
                    acquired_cfo_hz=acquired_cfo_hz,
                )
            )

    if not evidence:
        raise ValueError(f"null scan contains no GLRT64 candidate rows: {resolved}")
    groups = group_pilot_score_evidence(
        tuple(evidence),
        epoch_tolerance_samples=epoch_tolerance_samples,
        tracking_cfo_tolerance_hz=tracking_cfo_tolerance_hz,
        acquired_cfo_tolerance_hz=acquired_cfo_tolerance_hz,
    )
    positive_count = sum(group.maximum_score >= threshold for group in groups)
    return SourceInventory(
        source={
            "path": str(resolved),
            "file_digest": file_digest,
            "probe_schedule_digest": schedule_digest,
            "maximum_scored_candidates_per_probe": maximum_candidates,
            "detection_count": len(detections),
            "raw_glrt64_row_count": len(evidence),
            "deduplicated_glrt64_row_count": len(evidence),
            "resolution_group_count": len(groups),
            "positive_count": positive_count,
        },
        groups=groups,
        source_scan_digest=file_digest,
        raw_row_count=len(evidence),
        deduplicated_row_count=len(evidence),
    )


def _validate_complete_duration_input(document: dict[str, Any], path: Path) -> dict[str, int]:
    if document.get("schema") != DURATION_INPUT_SCHEMA:
        raise ValueError(f"expected a duration-constrained assignment input: {path}")
    if document.get("per_probe_rows_omitted") is True:
        raise ValueError(f"summary-only duration input is refused: {path}")
    if (
        document.get("candidate_only") is not True
        or document.get("satellite_specificity_claimed") is not False
    ):
        raise ValueError(f"duration input does not carry candidate-only authority: {path}")

    capture = _dict(document.get("capture"), "duration-input capture")
    declared_count = _integer(capture.get("declared_sample_count"), "declared sample count")
    observed_count = _integer(capture.get("observed_sample_count"), "observed sample count")
    coverage = _finite_number(capture.get("coverage_fraction"), "capture coverage fraction")
    if observed_count != declared_count or coverage != 1.0:
        raise ValueError(f"truncated duration-input capture is refused: {path}")

    scheduled_probes = _list(document.get("scheduled_probes"), "scheduled probes")
    if not scheduled_probes:
        raise ValueError(f"duration input has no scheduled-probe rows: {path}")
    probe_sample_starts: dict[str, int] = {}
    for index, raw_probe in enumerate(scheduled_probes):
        probe = _dict(raw_probe, f"scheduled probe {index}")
        probe_id = _string(probe.get("probe_id"), f"scheduled probe {index} ID")
        if probe_id in probe_sample_starts:
            raise ValueError("duration-input scheduled probe IDs are not unique")
        probe_sample_starts[probe_id] = _integer(
            probe.get("probe_sample_start"), f"scheduled probe {index} sample start"
        )
        source_candidate_count = _integer(
            probe.get("source_candidate_count"),
            f"scheduled probe {index} source candidate count",
        )
        retained_candidate_count = _integer(
            probe.get("retained_candidate_count"),
            f"scheduled probe {index} retained candidate count",
        )
        truncated_candidate_count = _integer(
            probe.get("truncated_candidate_count"),
            f"scheduled probe {index} truncated candidate count",
        )
        if truncated_candidate_count != 0 or retained_candidate_count != source_candidate_count:
            raise ValueError(f"truncated duration-input candidate inventory is refused: {path}")

    frame_inventory = _dict(document.get("frame_evidence_inventory"), "frame inventory")
    if frame_inventory.get("evidence_complete") is not True:
        raise ValueError(f"incomplete duration-input frame inventory is refused: {path}")
    if (
        _integer(
            frame_inventory.get("alias_expanded_truncated_track_count"),
            "truncated frame-track count",
        )
        != 0
    ):
        raise ValueError(f"truncated duration-input frame inventory is refused: {path}")
    return probe_sample_starts


def _positive_inventory(
    path: Path,
    component_id: str,
    threshold: float,
    *,
    epoch_tolerance_samples: int,
    tracking_cfo_tolerance_hz: float,
    acquired_cfo_tolerance_hz: float,
) -> SourceInventory:
    resolved = path.resolve(strict=True)
    document, file_digest = _read_object(resolved)
    scheduled_probe_sample_starts = _validate_complete_duration_input(document, resolved)

    source_products = _dict(document.get("source_products"), "source products")
    scan_source = _dict(source_products.get("scan"), "source pilot scan")
    scan_digest = _sha256_digest(scan_source.get("file_digest"), "source pilot-scan digest")
    scan_path = _string(scan_source.get("path"), "source pilot-scan path")

    components = [
        _dict(value, "alias component")
        for value in _list(document.get("alias_components"), "alias components")
        if isinstance(value, dict) and value.get("component_id") == component_id
    ]
    if len(components) != 1:
        raise ValueError(f"expected exactly one alias component {component_id!r}: {resolved}")
    component = components[0]
    if component.get("status") != "resolved":
        raise ValueError(f"positive alias component is not resolved: {component_id}")
    declared_branch_ids = [
        _string(value, "component branch ID")
        for value in _list(component.get("branch_ids"), "component branch IDs")
    ]
    if not declared_branch_ids or len(set(declared_branch_ids)) != len(declared_branch_ids):
        raise ValueError(f"positive component branch IDs are empty or duplicated: {component_id}")

    matching_branches: dict[str, dict[str, Any]] = {}
    for index, raw_branch in enumerate(_list(document.get("branches"), "duration-input branches")):
        branch = _dict(raw_branch, f"duration-input branch {index}")
        if branch.get("component_id") != component_id:
            continue
        branch_id = _string(branch.get("branch_id"), f"duration-input branch {index} ID")
        if branch_id in matching_branches:
            raise ValueError(f"positive branch ID is duplicated: {branch_id}")
        matching_branches[branch_id] = branch
    if set(matching_branches) != set(declared_branch_ids):
        raise ValueError(
            f"positive component branch inventory does not match its declaration: {component_id}"
        )

    deduplicated: dict[tuple[int, int], tuple[object, ...]] = {}
    evidence_by_identity: dict[tuple[int, int], PilotScoreEvidence] = {}
    row_identity_by_source_id: dict[str, tuple[int, int]] = {}
    raw_count = 0
    for branch_id in sorted(matching_branches):
        observations = _list(
            matching_branches[branch_id].get("observations"),
            f"positive branch {branch_id} observations",
        )
        for index, raw_observation in enumerate(observations):
            label = f"positive branch {branch_id} observation {index}"
            observation = _dict(raw_observation, label)
            if observation.get("component_id") != component_id:
                raise ValueError(f"{label} has the wrong component ID")
            if observation.get("branch_id") != branch_id:
                raise ValueError(f"{label} has the wrong branch ID")
            source_id = _string(observation.get("source_observation_id"), f"{label} source ID")
            source_ids = [
                _string(value, f"{label} source observation ID")
                for value in _list(observation.get("source_observation_ids"), f"{label} source IDs")
            ]
            if source_id not in source_ids:
                raise ValueError(f"{label} source ID is absent from its source-ID inventory")
            probe_id = _string(observation.get("probe_id"), f"{label} probe ID")
            if probe_id not in scheduled_probe_sample_starts:
                raise ValueError(f"{label} probe ID is absent from the scheduled-probe inventory")
            candidate_rank = _integer(observation.get("candidate_rank"), f"{label} rank")
            probe_start = _integer(
                observation.get("probe_sample_start"), f"{label} probe sample start"
            )
            if scheduled_probe_sample_starts[probe_id] != probe_start:
                raise ValueError(f"{label} probe sample start disagrees with its schedule row")
            local_epoch = _integer(
                observation.get("local_epoch_sample"), f"{label} local epoch sample"
            )
            exact = _finite_number(
                observation.get("glrt64_exact_score"), f"{label} GLRT64 exact score"
            )
            control = _finite_number(
                observation.get("glrt64_control_score"), f"{label} GLRT64 control score"
            )
            margin = _finite_number(observation.get("glrt64_margin"), f"{label} GLRT64 margin")
            tracking_cfo_hz = _finite_number(
                observation.get("source_tracking_cfo_hz"),
                f"{label} source tracking CFO",
            )
            if not math.isclose(margin, exact - control, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"{label} GLRT64 margin is inconsistent with exact minus control")
            row_identity = (probe_start, candidate_rank)
            fingerprint = (
                source_id,
                probe_id,
                local_epoch,
                tracking_cfo_hz,
                exact,
                control,
                margin,
            )
            previous_identity = row_identity_by_source_id.get(source_id)
            if previous_identity is not None and previous_identity != row_identity:
                raise ValueError(f"positive source ID maps to conflicting GLRT64 rows: {source_id}")
            row_identity_by_source_id[source_id] = row_identity
            previous = deduplicated.get(row_identity)
            if previous is not None and previous != fingerprint:
                raise ValueError(
                    "conflicting duplicate positive GLRT64 row: "
                    f"sample_start={probe_start}, rank={candidate_rank}"
                )
            deduplicated[row_identity] = fingerprint
            evidence_by_identity[row_identity] = PilotScoreEvidence(
                evidence_id=source_id,
                probe_id=probe_id,
                rank=candidate_rank,
                local_epoch_sample=local_epoch,
                tracking_cfo_hz=tracking_cfo_hz,
                score=margin,
            )
            raw_count += 1

    declared_count = _integer(
        component.get("deduplicated_source_probe_count"),
        "component deduplicated source-probe count",
    )
    if len(deduplicated) != declared_count:
        raise ValueError(
            "positive GLRT64 row count does not match component "
            f"deduplicated_source_probe_count: {component_id}"
        )
    if not deduplicated:
        raise ValueError(f"positive component contains no GLRT64 rows: {component_id}")
    evidence = tuple(evidence_by_identity[identity] for identity in sorted(evidence_by_identity))
    groups = group_pilot_score_evidence(
        evidence,
        epoch_tolerance_samples=epoch_tolerance_samples,
        tracking_cfo_tolerance_hz=tracking_cfo_tolerance_hz,
        acquired_cfo_tolerance_hz=acquired_cfo_tolerance_hz,
    )
    unique_group_probe_count = len({group.probe_id for group in groups})
    if unique_group_probe_count != len(groups):
        raise ValueError(
            "positive signal calibration requires at most one resolution group per probe"
        )
    positive_count = sum(group.maximum_score >= threshold for group in groups)
    return SourceInventory(
        source={
            "path": str(resolved),
            "file_digest": file_digest,
            "component_id": component_id,
            "pilot_scan": {"path": scan_path, "file_digest": scan_digest},
            "branch_count": len(matching_branches),
            "raw_glrt64_row_count": raw_count,
            "deduplicated_glrt64_row_count": len(evidence),
            "duplicate_glrt64_row_count": raw_count - len(evidence),
            "resolution_group_count": len(groups),
            "unique_resolution_group_probe_count": unique_group_probe_count,
            "positive_count": positive_count,
        },
        groups=groups,
        source_scan_digest=scan_digest,
        raw_row_count=raw_count,
        deduplicated_row_count=len(evidence),
    )


def _refuse_overlapping_sources(
    null_inventories: Sequence[SourceInventory],
    signal_inventories: Sequence[SourceInventory],
) -> None:
    owners: dict[str, list[str]] = {}
    for label, inventories in (("null", null_inventories), ("signal", signal_inventories)):
        for inventory in inventories:
            owners.setdefault(inventory.source_scan_digest, []).append(
                f"{label}:{inventory.source['path']}"
            )
    overlaps = {digest: values for digest, values in owners.items() if len(values) > 1}
    if overlaps:
        detail = "; ".join(
            f"{digest} ({', '.join(values)})" for digest, values in sorted(overlaps.items())
        )
        raise ValueError(f"overlapping calibration source pilot-scan digests are refused: {detail}")


def build_calibration(
    *,
    null_scan_paths: Sequence[Path],
    positive_components: Sequence[tuple[Path, str]],
    score_threshold: float,
    detection_probability: float,
    familywise_alpha: float = 0.05,
    resolution_epoch_tolerance_samples: int = 1,
    resolution_tracking_cfo_tolerance_hz: float = 500.0,
    duplicate_acquired_cfo_tolerance_hz: float = 0.0,
) -> dict[str, Any]:
    """Build one deterministic calibration document from frozen input files."""

    threshold = _finite_number(score_threshold, "score threshold")
    alpha = _finite_number(familywise_alpha, "familywise alpha")
    if not 0.0 < alpha < 1.0:
        raise ValueError("familywise alpha must lie in (0, 1)")
    if not null_scan_paths:
        raise ValueError("at least one null pilot scan is required")
    if not positive_components:
        raise ValueError("at least one positive component is required")

    null_inventories = sorted(
        (
            _null_inventory(
                path,
                threshold,
                epoch_tolerance_samples=resolution_epoch_tolerance_samples,
                tracking_cfo_tolerance_hz=resolution_tracking_cfo_tolerance_hz,
                acquired_cfo_tolerance_hz=duplicate_acquired_cfo_tolerance_hz,
            )
            for path in null_scan_paths
        ),
        key=lambda item: (item.source_scan_digest, item.source["path"]),
    )
    signal_inventories = sorted(
        (
            _positive_inventory(
                path,
                component_id,
                threshold,
                epoch_tolerance_samples=resolution_epoch_tolerance_samples,
                tracking_cfo_tolerance_hz=resolution_tracking_cfo_tolerance_hz,
                acquired_cfo_tolerance_hz=duplicate_acquired_cfo_tolerance_hz,
            )
            for path, component_id in positive_components
        ),
        key=lambda item: (
            item.source_scan_digest,
            item.source["component_id"],
            item.source["path"],
        ),
    )
    _refuse_overlapping_sources(null_inventories, signal_inventories)

    null_groups = tuple(group for inventory in null_inventories for group in inventory.groups)
    signal_groups = tuple(group for inventory in signal_inventories for group in inventory.groups)
    bucket_count = len(RANK_BUCKET_SPECS)
    null_source_count = len(null_inventories)
    null_tail_probability = alpha / (2.0 * bucket_count * null_source_count)
    signal_tail_probability = alpha / (2.0 * bucket_count)

    def in_bucket(group: PilotScoreGroup, minimum: int, maximum: int | None) -> bool:
        return group.minimum_rank >= minimum and (maximum is None or group.minimum_rank <= maximum)

    rank_marks: list[ConservativeRankMarkCalibration] = []
    bucket_rows: list[dict[str, Any]] = []
    for label, minimum_rank, maximum_rank in RANK_BUCKET_SPECS:
        source_rows: list[dict[str, Any]] = []
        for inventory in null_inventories:
            groups = tuple(
                group for group in inventory.groups if in_bucket(group, minimum_rank, maximum_rank)
            )
            positive_count = sum(group.maximum_score >= threshold for group in groups)
            probe_count = int(inventory.source["detection_count"])
            upper_mean = poisson_count_upper_mean(
                positive_count,
                null_tail_probability,
            )
            upper_intensity = upper_mean / probe_count
            source_rows.append(
                {
                    "pilot_scan_digest": inventory.source_scan_digest,
                    "probe_count": probe_count,
                    "group_count": len(groups),
                    "positive_group_count": positive_count,
                    "poisson_count_upper_mean": upper_mean,
                    "positive_intensity_upper_per_probe": upper_intensity,
                }
            )
        worst_source = max(
            source_rows,
            key=lambda item: (
                _finite_number(
                    item["positive_intensity_upper_per_probe"],
                    "source positive intensity upper bound",
                ),
                str(item["pilot_scan_digest"]),
            ),
        )
        signal_positive_count = sum(
            group.maximum_score >= threshold
            for group in signal_groups
            if in_bucket(group, minimum_rank, maximum_rank)
        )
        signal_lower = wilson_probability_lower(
            signal_positive_count,
            len(signal_groups),
            signal_tail_probability,
        )
        mark = ConservativeRankMarkCalibration(
            label=label,
            minimum_rank=minimum_rank,
            maximum_rank=maximum_rank,
            null_positive_intensity_upper_per_probe=_finite_number(
                worst_source["positive_intensity_upper_per_probe"],
                "worst-source positive intensity upper bound",
            ),
            signal_positive_mark_probability_lower=signal_lower,
        )
        rank_marks.append(mark)
        bucket_rows.append(
            {
                "label": label,
                "minimum_rank": minimum_rank,
                "maximum_rank": maximum_rank,
                "null": {
                    "group_count": sum(
                        in_bucket(group, minimum_rank, maximum_rank) for group in null_groups
                    ),
                    "positive_group_count": sum(
                        group.maximum_score >= threshold
                        and in_bucket(group, minimum_rank, maximum_rank)
                        for group in null_groups
                    ),
                    "source_bounds": sorted(
                        source_rows,
                        key=lambda item: str(item["pilot_scan_digest"]),
                    ),
                    "worst_source_pilot_scan_digest": worst_source["pilot_scan_digest"],
                    "positive_intensity_upper_per_probe": worst_source[
                        "positive_intensity_upper_per_probe"
                    ],
                },
                "signal": {
                    "positive_group_count": signal_positive_count,
                    "total_group_count": len(signal_groups),
                    "positive_mark_probability_lower": signal_lower,
                },
            }
        )
    calibration = ConservativeRankMarkedPilotScoreCalibration(
        score_threshold=threshold,
        rank_marks=tuple(rank_marks),
        detection_probability=detection_probability,
    )
    positive_score = threshold
    negative_score = math.nextafter(threshold, -math.inf)

    def feature_costs(score: float, rank: int) -> dict[str, Any]:
        supported = calibration.match_supported(rank) or not calibration.is_positive(score)
        return {
            "clutter_cost": calibration.clutter_cost(score, rank),
            "match_supported": supported,
            "matched_base_cost": (
                calibration.matched_base_cost(score, rank) if supported else None
            ),
            "match_delta_before_residual": (
                calibration.match_delta_before_residual(score, rank) if supported else None
            ),
        }

    for row, mark in zip(bucket_rows, calibration.rank_marks, strict=True):
        row["costs"] = {
            "positive": feature_costs(positive_score, mark.minimum_rank),
            "negative": feature_costs(negative_score, mark.minimum_rank),
        }

    return {
        "schema": SCHEMA,
        "score_threshold": threshold,
        "detection_probability": calibration.detection_probability,
        "confidence": {
            "familywise_alpha": alpha,
            "rank_bucket_count": bucket_count,
            "null_source_count": null_source_count,
            "null_source_bucket_tail_probability": null_tail_probability,
            "signal_bucket_tail_probability": signal_tail_probability,
            "null_bound": "worst-source-exact-poisson-count-upper",
            "signal_bound": "simultaneous-wilson-mark-probability-lower",
        },
        "grouping": {
            "unit": "unresolved_probe_epoch_tracking_cfo_cell",
            "epoch_tolerance_samples": resolution_epoch_tolerance_samples,
            "tracking_cfo_tolerance_hz": resolution_tracking_cfo_tolerance_hz,
            "exact_duplicate_acquired_cfo_tolerance_hz": (duplicate_acquired_cfo_tolerance_hz),
            "physical_source_identity_claimed": False,
        },
        "null": {
            "positive_group_count": sum(group.maximum_score >= threshold for group in null_groups),
            "group_count": len(null_groups),
            "rank_buckets": bucket_rows,
        },
        "signal": {
            "positive_group_count": sum(
                group.maximum_score >= threshold for group in signal_groups
            ),
            "group_count": len(signal_groups),
        },
        "costs": {
            "missed_detection_cost": calibration.missed_detection_cost,
            "weak_match_is_dominated_by_miss": calibration.weak_match_is_dominated_by_miss(),
        },
        "sources": {
            "null": [inventory.source for inventory in null_inventories],
            "signal": [inventory.source for inventory in signal_inventories],
            "disjoint_pilot_scan_digests": True,
        },
        "accounting": {
            "null_input_file_count": len(null_inventories),
            "signal_component_spec_count": len(signal_inventories),
            "null_raw_glrt64_row_count": sum(
                inventory.raw_row_count for inventory in null_inventories
            ),
            "null_deduplicated_glrt64_row_count": sum(
                inventory.deduplicated_row_count for inventory in null_inventories
            ),
            "null_resolution_group_count": len(null_groups),
            "signal_raw_glrt64_row_count": sum(
                inventory.raw_row_count for inventory in signal_inventories
            ),
            "signal_deduplicated_glrt64_row_count": sum(
                inventory.deduplicated_row_count for inventory in signal_inventories
            ),
            "signal_resolution_group_count": len(signal_groups),
            "signal_unique_resolution_group_probe_count": len(
                {group.probe_id for group in signal_groups}
            ),
        },
        "caveats": [
            "Null inventories are empirical no-result dwells, not proof that no "
            "transmitter was present.",
            "Signal inventories are radio-selected resolved components, not "
            "payload-decoded spacecraft identities.",
            "The binary exact-minus-control margin threshold discards information "
            "in the full GLRT64 score pair.",
            "Zero declared truncation does not prove physical peak exhaustiveness; "
            "Standard acquisition retains a bounded candidate inventory.",
            "Positive clutter rates use the worst source-specific simultaneous upper "
            "intensity in each minimum-rank bucket.",
            "Detected-signal rank marks use simultaneous lower probability bounds.",
            "Each signal calibration group occupies a unique native probe; inputs with "
            "multiple selected signal groups per probe are refused.",
            "The detection probability remains an explicit modeling assumption.",
            "Derived costs are conservative research pseudo-costs, not posterior probabilities.",
            "Calibration sources must remain frozen and disjoint from evaluation dwells.",
        ],
    }


def _output_path(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    if resolved == QNAP_ROOT or QNAP_ROOT in resolved.parents:
        raise ValueError("refusing to write calibration output below /mnt/qnap01")
    return resolved


def main() -> int:
    args = _arguments()
    output = None if args.output is None else _output_path(args.output)
    positive_components = [
        (Path(path), component_id) for path, component_id in args.positive_component
    ]
    result = build_calibration(
        null_scan_paths=args.null_scan,
        positive_components=positive_components,
        score_threshold=args.score_threshold,
        detection_probability=args.detection_probability,
        familywise_alpha=args.familywise_alpha,
        resolution_epoch_tolerance_samples=args.resolution_epoch_tolerance_samples,
        resolution_tracking_cfo_tolerance_hz=(args.resolution_tracking_cfo_tolerance_hz),
        duplicate_acquired_cfo_tolerance_hz=(args.duplicate_acquired_cfo_tolerance_hz),
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
