"""Pure product-only radio and paired-radio Standard reducers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import (
    AssociationStatus,
    FrequencyReference,
    PairedStandardReportV1,
    PairTimingEvidenceV1,
    PathStandardReportV1,
    RadioStandardReportV1,
    StandardScientificStatus,
    StandardTrajectoryV1,
    TrajectoryAssociationV1,
)

_BASE_ASSOCIATION_GATE_HZ = 2_500.0


def reduce_radio(
    paths: tuple[PathStandardReportV1, ...],
    *,
    declared_receiver_ids: tuple[int, ...],
) -> RadioStandardReportV1:
    """Reduce the exact declared receiver products for one radio.

    This API deliberately accepts only immutable path reports. It has no IQ,
    storage, catalog, or arbitrary product-discovery port.
    """

    ordered = tuple(sorted(paths, key=lambda item: item.receiver_id))
    if not ordered:
        raise ValueError("radio reduction requires at least one path report")
    declared = tuple(sorted(declared_receiver_ids))
    if (
        len(set(declared)) != len(declared)
        or tuple(item.receiver_id for item in ordered) != declared
    ):
        raise ValueError("radio reducer inputs must exactly match declared receivers")
    _require_equal(ordered, "session_id")
    _require_equal(ordered, "stream_id")
    _require_equal(ordered, "radio_id")
    _require_equal(ordered, "manifest_digest")
    _require_equal(ordered, "synchronization_inventory_digest")
    timing_documents = {item.timing.model_dump_json() for item in ordered}
    if len(timing_documents) != 1:
        raise ValueError("receiver paths for one radio must share exact stream timing")

    association_status, associations, unmatched = _associate_path_sets(
        (ordered[0],),
        ordered[1:],
    )
    if len(ordered) == 1:
        association_status = AssociationStatus.INSUFFICIENT_DATA
        associations = ()
        unmatched = _trajectory_keys(ordered)
    status = _aggregate_status(tuple(item.status for item in ordered))
    truncated_candidates = sum(item.truncated_candidate_count for item in ordered)
    truncated_trajectories = sum(item.truncated_trajectory_count for item in ordered)
    reason = _radio_reason(status, association_status, truncated_candidates, truncated_trajectories)
    first = ordered[0]
    values: dict[str, Any] = {
        "schema_version": 1,
        "session_id": first.session_id,
        "stream_id": first.stream_id,
        "radio_id": first.radio_id,
        "manifest_digest": first.manifest_digest,
        "synchronization_inventory_digest": first.synchronization_inventory_digest,
        "pipeline_family": "standard-glrt64-v2",
        "status": status,
        "reason": reason,
        "declared_receiver_ids": list(declared),
        "paths": [item.model_dump(mode="json") for item in ordered],
        "association_status": association_status,
        "associations": [item.model_dump(mode="json") for item in associations],
        "unmatched_trajectory_ids": list(unmatched),
        "child_truncated_candidate_count": truncated_candidates,
        "child_truncated_trajectory_count": truncated_trajectories,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return RadioStandardReportV1(**values, report_digest=canonical_digest(values))


def reduce_paired_radios(
    radios: tuple[RadioStandardReportV1, RadioStandardReportV1],
    *,
    timing: PairTimingEvidenceV1,
) -> PairedStandardReportV1:
    """Reduce exactly two same-manifest radio reports without rereading IQ."""

    ordered = tuple(sorted(radios, key=lambda item: (item.stream_id, item.radio_id)))
    ordered_pair = (ordered[0], ordered[1])
    if ordered[0].stream_id == ordered[1].stream_id:
        raise ValueError("paired reducer requires two distinct radio streams")
    _require_equal(ordered, "session_id")
    _require_equal(ordered, "manifest_digest")
    _require_equal(ordered, "synchronization_inventory_digest")
    if timing.synchronization_inventory_digest != ordered[0].synchronization_inventory_digest:
        raise ValueError("pair timing does not belong to these radio reports")
    _verify_pair_timing(ordered_pair, timing)

    left_paths = ordered[0].paths
    right_paths = ordered[1].paths
    association_status, associations, unmatched = _associate_path_sets(left_paths, right_paths)
    status = _aggregate_status(tuple(item.status for item in ordered))
    truncated_candidates = sum(item.child_truncated_candidate_count for item in ordered)
    truncated_trajectories = sum(item.child_truncated_trajectory_count for item in ordered)
    reason = _paired_reason(
        status, association_status, truncated_candidates, truncated_trajectories
    )
    first = ordered[0]
    values: dict[str, Any] = {
        "schema_version": 1,
        "session_id": first.session_id,
        "manifest_digest": first.manifest_digest,
        "synchronization_inventory_digest": first.synchronization_inventory_digest,
        "pipeline_family": "standard-glrt64-v2",
        "status": status,
        "reason": reason,
        "radios": [item.model_dump(mode="json") for item in ordered],
        "timing": timing.model_dump(mode="json"),
        "association_status": association_status,
        "associations": [item.model_dump(mode="json") for item in associations],
        "unmatched_trajectory_ids": list(unmatched),
        "child_truncated_candidate_count": truncated_candidates,
        "child_truncated_trajectory_count": truncated_trajectories,
        "phase_coherent": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PairedStandardReportV1(**values, report_digest=canonical_digest(values))


@dataclass(frozen=True, slots=True)
class _TrajectoryEntry:
    path: PathStandardReportV1
    trajectory: StandardTrajectoryV1

    @property
    def path_id(self) -> str:
        return _path_id(self.path)

    @property
    def key(self) -> str:
        return f"{self.path_id}#{self.trajectory.trajectory_id}"

    @property
    def start_utc_ns(self) -> int:
        return self.path.timing.first_estimate_utc_ns + round(self.trajectory.start_s * 1e9)

    @property
    def end_utc_ns(self) -> int:
        return self.path.timing.first_estimate_utc_ns + round(self.trajectory.end_s * 1e9)


def _associate_path_sets(
    left_paths: tuple[PathStandardReportV1, ...],
    right_paths: tuple[PathStandardReportV1, ...],
) -> tuple[AssociationStatus, tuple[TrajectoryAssociationV1, ...], tuple[str, ...]]:
    all_paths = left_paths + right_paths
    entries = _trajectory_entries(all_paths)
    if not entries:
        return AssociationStatus.INSUFFICIENT_DATA, (), ()
    if any(
        item.frequency_reference.reference is FrequencyReference.UNCALIBRATED_PRIOR
        for item in all_paths
    ):
        return (
            AssociationStatus.UNAVAILABLE_UNCALIBRATED_PRIOR,
            (),
            tuple(sorted(item.key for item in entries)),
        )
    left = _trajectory_entries(left_paths)
    right = _trajectory_entries(right_paths)
    if not left or not right:
        return AssociationStatus.INSUFFICIENT_DATA, (), tuple(sorted(item.key for item in entries))

    candidates: list[tuple[float, str, str, TrajectoryAssociationV1]] = []
    union_start_ns = min(item.path.timing.first_estimate_utc_ns for item in entries)
    for left_item in left:
        for right_item in right:
            overlap_start_ns = max(left_item.start_utc_ns, right_item.start_utc_ns)
            overlap_end_ns = min(left_item.end_utc_ns, right_item.end_utc_ns)
            if overlap_end_ns <= overlap_start_ns:
                continue
            midpoint_ns = (overlap_start_ns + overlap_end_ns) // 2
            left_frequency = _physical_frequency(left_item, midpoint_ns)
            right_frequency = _physical_frequency(right_item, midpoint_ns)
            difference = abs(left_frequency - right_frequency)
            left_uncertainty = left_item.path.frequency_reference.uncertainty_hz
            right_uncertainty = right_item.path.frequency_reference.uncertainty_hz
            assert left_uncertainty is not None and right_uncertainty is not None
            gate = _BASE_ASSOCIATION_GATE_HZ + left_uncertainty + right_uncertainty
            if difference > gate:
                continue
            document = {
                "left_path_id": left_item.path_id,
                "left_trajectory_id": left_item.trajectory.trajectory_id,
                "right_path_id": right_item.path_id,
                "right_trajectory_id": right_item.trajectory.trajectory_id,
                "overlap_start_utc_ns": overlap_start_ns,
                "overlap_end_utc_ns": overlap_end_ns,
                "midpoint_frequency_difference_hz": difference,
                "gate_hz": gate,
            }
            association = TrajectoryAssociationV1(
                association_id=canonical_digest(document),
                left_path_id=left_item.path_id,
                left_trajectory_id=left_item.trajectory.trajectory_id,
                right_path_id=right_item.path_id,
                right_trajectory_id=right_item.trajectory.trajectory_id,
                overlap_start_s=(overlap_start_ns - union_start_ns) / 1e9,
                overlap_end_s=(overlap_end_ns - union_start_ns) / 1e9,
                midpoint_frequency_difference_hz=difference,
                gate_hz=gate,
            )
            candidates.append((difference, left_item.key, right_item.key, association))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    used_left: set[str] = set()
    used_right: set[str] = set()
    selected = []
    for _, left_key, right_key, association in candidates:
        if left_key in used_left or right_key in used_right:
            continue
        used_left.add(left_key)
        used_right.add(right_key)
        selected.append(association)
    selected.sort(key=lambda item: (item.left_path_id, item.left_trajectory_id, item.right_path_id))
    matched = used_left | used_right
    unmatched = tuple(sorted(item.key for item in entries if item.key not in matched))
    return AssociationStatus.EVALUATED, tuple(selected), unmatched


def _trajectory_entries(
    paths: tuple[PathStandardReportV1, ...],
) -> tuple[_TrajectoryEntry, ...]:
    entries = [
        _TrajectoryEntry(path, trajectory)
        for path in paths
        for trajectory in path.trajectories
        if trajectory.fit_matches_well
    ]
    return tuple(sorted(entries, key=lambda item: item.key))


def _trajectory_keys(paths: tuple[PathStandardReportV1, ...]) -> tuple[str, ...]:
    return tuple(sorted(item.key for item in _trajectory_entries(paths)))


def _physical_frequency(entry: _TrajectoryEntry, utc_ns: int) -> float:
    reference = entry.path.frequency_reference
    if reference.reference is not FrequencyReference.CALIBRATED:
        raise ValueError("uncalibrated trajectory has no physical-frequency authority")
    assert reference.center_frequency_hz is not None
    local_time_s = (utc_ns - entry.path.timing.first_estimate_utc_ns) / 1e9
    relative = local_time_s - entry.trajectory.reference_time_s
    baseband = float(np.polyval(np.asarray(entry.trajectory.coefficients_hz), relative))
    return reference.center_frequency_hz + baseband


def _verify_pair_timing(
    radios: tuple[RadioStandardReportV1, RadioStandardReportV1],
    timing: PairTimingEvidenceV1,
) -> None:
    radio_timings = tuple(item.paths[0].timing for item in radios)
    union_start = min(item.first_estimate_utc_ns for item in radio_timings)
    union_end = max(item.last_estimate_utc_ns for item in radio_timings)
    overlap_start = max(item.first_estimate_utc_ns for item in radio_timings)
    overlap_end = min(item.last_estimate_utc_ns for item in radio_timings)
    skew = abs(radio_timings[0].first_estimate_utc_ns - radio_timings[1].first_estimate_utc_ns)
    observed = (
        timing.union_start_utc_ns,
        timing.union_end_utc_ns,
        timing.estimated_overlap_start_utc_ns,
        timing.estimated_overlap_end_utc_ns,
        timing.estimated_start_skew_ns,
    )
    expected = (union_start, union_end, overlap_start, overlap_end, skew)
    if observed != expected:
        raise ValueError("pair timing disagrees with exact child report timelines")


def _aggregate_status(statuses: tuple[StandardScientificStatus, ...]) -> StandardScientificStatus:
    if any(item is StandardScientificStatus.INSUFFICIENT_DATA for item in statuses):
        return StandardScientificStatus.INSUFFICIENT_DATA
    if any(item is StandardScientificStatus.PARTIAL for item in statuses):
        return StandardScientificStatus.PARTIAL
    if all(item is StandardScientificStatus.NO_RESULT for item in statuses):
        return StandardScientificStatus.NO_RESULT
    return StandardScientificStatus.COMPLETE


def _radio_reason(
    status: StandardScientificStatus,
    association_status: AssociationStatus,
    truncated_candidates: int,
    truncated_trajectories: int,
) -> str:
    return (
        f"{status.value} product-only radio reduction; association={association_status.value}; "
        f"child truncation candidates={truncated_candidates}, "
        f"trajectories={truncated_trajectories}; "
        "candidate consistency only"
    )


def _paired_reason(
    status: StandardScientificStatus,
    association_status: AssociationStatus,
    truncated_candidates: int,
    truncated_trajectories: int,
) -> str:
    return (
        f"{status.value} noncoherent two-radio reduction; association={association_status.value}; "
        f"child truncation candidates={truncated_candidates}, "
        f"trajectories={truncated_trajectories}; "
        "four paths are not independent trials"
    )


def _path_id(path: PathStandardReportV1) -> str:
    return f"{path.session_id}/{path.stream_id}/rx-{path.receiver_id}"


def _require_equal(items: tuple[Any, ...], field: str) -> None:
    if len({getattr(item, field) for item in items}) != 1:
        raise ValueError(f"aggregate inputs disagree on {field}")
