"""Pure terminal reducers over replay-selected Standard trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from leo.contracts.cfo_dealias import (
    CfoAliasMapV1,
    CfoLiftReplayV1,
    DealiasedTrajectoryBankV1,
    FinalTrajectoryBankV1,
    FinalTrajectoryV1,
    Glrt64FinalTrajectoryTableV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.final_trajectory_reports import (
    DerivativeTrajectoryAssociationV2,
    PairedStandardReportV2,
    PathStandardReportV2,
    RadioStandardReportV2,
)
from leo.contracts.standard_pipeline import (
    AssociationStatus,
    PathStandardReportV1,
    StandardPairInputBindV2,
    StandardScientificStatus,
)


def build_path_standard_report_v2(
    raw_report: PathStandardReportV1,
    *,
    alias_map: CfoAliasMapV1,
    dealiased_bank: DealiasedTrajectoryBankV1,
    lift_replay: CfoLiftReplayV1,
    final_bank: FinalTrajectoryBankV1,
    final_table: Glrt64FinalTrajectoryTableV1,
) -> PathStandardReportV2:
    """Bind the legacy raw summary to the exact final trajectory closure."""

    if (
        dealiased_bank.alias_map_digest != alias_map.content_digest
        or lift_replay.dealiased_bank_digest != dealiased_bank.content_digest
        or final_bank.dealiased_bank_digest != dealiased_bank.content_digest
        or final_bank.lift_replay_digest != lift_replay.content_digest
        or final_table.final_trajectory_bank_digest != final_bank.content_digest
        or final_table.trajectories != final_bank.trajectories
    ):
        raise ValueError("final path report predecessor closure is inconsistent")
    status = _path_status(raw_report.status, final_bank.status)
    reason = (
        f"{status.value} final path reduction from replay-selected absolute CFO trajectories; "
        f"raw={raw_report.status.value}; final={final_bank.status.value}; candidate-only"
    )
    values: dict[str, Any] = {
        "schema_version": 2,
        "algorithm_version": "standard-path-report-v2",
        "raw_report": raw_report.model_dump(mode="json"),
        "cfo_alias_map_digest": alias_map.content_digest,
        "dealiased_trajectory_bank_digest": dealiased_bank.content_digest,
        "cfo_lift_replay_digest": lift_replay.content_digest,
        "final_trajectory_bank_digest": final_bank.content_digest,
        "final_trajectory_table_digest": final_table.content_digest,
        "source_trajectory_count": final_bank.source_trajectory_count,
        "returned_trajectory_count": final_bank.returned_trajectory_count,
        "truncated_trajectory_count": final_bank.truncated_trajectory_count,
        "final_trajectories": [item.model_dump(mode="json") for item in final_bank.trajectories],
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PathStandardReportV2(**values, report_digest=canonical_digest(values))


def reduce_radio_v2(
    paths: tuple[PathStandardReportV2, ...],
    *,
    declared_receiver_ids: tuple[int, ...],
) -> RadioStandardReportV2:
    ordered = tuple(sorted(paths, key=lambda item: item.raw_report.receiver_id))
    if not ordered:
        raise ValueError("final radio reduction requires at least one path")
    declared = tuple(sorted(declared_receiver_ids))
    if declared != tuple(item.raw_report.receiver_id for item in ordered) or len(
        set(declared)
    ) != len(declared):
        raise ValueError("final radio inputs do not match declared receivers")
    _require_equal_raw(ordered, "session_id")
    _require_equal_raw(ordered, "stream_id")
    _require_equal_raw(ordered, "radio_id")
    _require_equal_raw(ordered, "manifest_digest")
    _require_equal_raw(ordered, "synchronization_inventory_digest")
    if len({item.raw_report.timing.model_dump_json() for item in ordered}) != 1:
        raise ValueError("final radio paths disagree on stream timing")
    associations, unmatched, association_status = _associate((ordered[0],), ordered[1:])
    if len(ordered) == 1:
        association_status = AssociationStatus.INSUFFICIENT_DATA
    status = _aggregate_status(tuple(item.status for item in ordered))
    candidate_truncation = sum(item.raw_report.truncated_candidate_count for item in ordered)
    trajectory_truncation = sum(item.truncated_trajectory_count for item in ordered)
    first = ordered[0].raw_report
    values: dict[str, Any] = {
        "schema_version": 2,
        "algorithm_version": "standard-radio-report-v2",
        "session_id": first.session_id,
        "stream_id": first.stream_id,
        "radio_id": first.radio_id,
        "manifest_digest": first.manifest_digest,
        "synchronization_inventory_digest": first.synchronization_inventory_digest,
        "status": status,
        "reason": _reason(
            "radio", status, association_status, candidate_truncation, trajectory_truncation
        ),
        "declared_receiver_ids": list(declared),
        "paths": [item.model_dump(mode="json") for item in ordered],
        "association_status": association_status,
        "derivative_associations": [item.model_dump(mode="json") for item in associations],
        "unmatched_trajectory_ids": list(unmatched),
        "child_truncated_candidate_count": candidate_truncation,
        "child_truncated_trajectory_count": trajectory_truncation,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return RadioStandardReportV2(**values, report_digest=canonical_digest(values))


def reduce_paired_radios_v2(
    radios: tuple[RadioStandardReportV2, RadioStandardReportV2],
    *,
    binding: StandardPairInputBindV2,
) -> PairedStandardReportV2:
    ordered_values = tuple(sorted(radios, key=lambda item: (item.stream_id, item.radio_id)))
    ordered = (ordered_values[0], ordered_values[1])
    if ordered[0].stream_id == ordered[1].stream_id:
        raise ValueError("final paired reduction requires distinct radio streams")
    for field in ("session_id", "manifest_digest", "synchronization_inventory_digest"):
        if getattr(ordered[0], field) != getattr(ordered[1], field):
            raise ValueError(f"final paired radio inputs disagree on {field}")
    if (
        binding.session_id != ordered[0].session_id
        or binding.manifest_digest != ordered[0].manifest_digest
        or binding.synchronization_inventory_digest != ordered[0].synchronization_inventory_digest
    ):
        raise ValueError("final pair binding disagrees with radio reports")
    associations, unmatched, association_status = _associate(ordered[0].paths, ordered[1].paths)
    status = _aggregate_status(tuple(item.status for item in ordered))
    candidate_truncation = sum(item.child_truncated_candidate_count for item in ordered)
    trajectory_truncation = sum(item.child_truncated_trajectory_count for item in ordered)
    values: dict[str, Any] = {
        "schema_version": 2,
        "algorithm_version": "standard-paired-report-v2",
        "session_id": ordered[0].session_id,
        "manifest_digest": ordered[0].manifest_digest,
        "synchronization_inventory_digest": ordered[0].synchronization_inventory_digest,
        "status": status,
        "reason": _reason(
            "noncoherent paired",
            status,
            association_status,
            candidate_truncation,
            trajectory_truncation,
        ),
        "radios": [item.model_dump(mode="json") for item in ordered],
        "timing": binding.timing.model_dump(mode="json"),
        "association_status": association_status,
        "derivative_associations": [item.model_dump(mode="json") for item in associations],
        "unmatched_trajectory_ids": list(unmatched),
        "child_truncated_candidate_count": candidate_truncation,
        "child_truncated_trajectory_count": trajectory_truncation,
        "phase_coherent": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PairedStandardReportV2(**values, report_digest=canonical_digest(values))


@dataclass(frozen=True, slots=True)
class _Entry:
    path: PathStandardReportV2
    trajectory: FinalTrajectoryV1

    @property
    def path_id(self) -> str:
        raw = self.path.raw_report
        return f"{raw.session_id}/{raw.stream_id}/rx-{raw.receiver_id}"

    @property
    def key(self) -> str:
        return f"{self.path_id}#{self.trajectory.trajectory_id}"

    @property
    def start_utc_ns(self) -> int:
        return self.path.raw_report.timing.first_estimate_utc_ns + round(
            self.trajectory.start_s * 1e9
        )

    @property
    def end_utc_ns(self) -> int:
        return self.path.raw_report.timing.first_estimate_utc_ns + round(
            self.trajectory.end_s * 1e9
        )


def _associate(
    left_paths: tuple[PathStandardReportV2, ...],
    right_paths: tuple[PathStandardReportV2, ...],
) -> tuple[
    tuple[DerivativeTrajectoryAssociationV2, ...],
    tuple[str, ...],
    AssociationStatus,
]:
    left = _entries(left_paths)
    right = _entries(right_paths)
    all_entries = left + right
    if not left or not right:
        return (
            (),
            tuple(sorted(item.key for item in all_entries)),
            AssociationStatus.INSUFFICIENT_DATA,
        )
    candidates = []
    for left_item in left:
        for right_item in right:
            overlap_start = max(left_item.start_utc_ns, right_item.start_utc_ns)
            overlap_end = min(left_item.end_utc_ns, right_item.end_utc_ns)
            if overlap_end <= overlap_start:
                continue
            association = _derivative_association(left_item, right_item, overlap_start, overlap_end)
            candidates.append(
                (association.comparison_score, left_item.key, right_item.key, association)
            )
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
    selected.sort(key=lambda item: item.association_id)
    matched = used_left | used_right
    unmatched = tuple(sorted(item.key for item in all_entries if item.key not in matched))
    return tuple(selected), unmatched, AssociationStatus.EVALUATED


def _derivative_association(
    left: _Entry,
    right: _Entry,
    overlap_start_ns: int,
    overlap_end_ns: int,
) -> DerivativeTrajectoryAssociationV2:
    utc = np.linspace(overlap_start_ns, overlap_end_ns, 128)
    left_values = _derivatives(left, utc)
    right_values = _derivatives(right, utc)
    differences = tuple(
        left_value - right_value
        for left_value, right_value in zip(left_values, right_values, strict=True)
    )
    rms = tuple(float(np.sqrt(np.mean(value**2))) for value in differences)
    maximum = tuple(float(np.max(np.abs(value))) for value in differences)
    duration_s = (overlap_end_ns - overlap_start_ns) / 1e9
    score = rms[0] + rms[1] * duration_s + rms[2] * duration_s * duration_s
    identity = {
        "left_path_id": left.path_id,
        "left_trajectory_id": left.trajectory.trajectory_id,
        "right_path_id": right.path_id,
        "right_trajectory_id": right.trajectory.trajectory_id,
        "overlap_start_utc_ns": overlap_start_ns,
        "overlap_end_utc_ns": overlap_end_ns,
        "comparison_basis": "slope_acceleration_jerk_only",
    }
    return DerivativeTrajectoryAssociationV2(
        association_id=canonical_digest(identity),
        left_path_id=left.path_id,
        left_trajectory_id=left.trajectory.trajectory_id,
        right_path_id=right.path_id,
        right_trajectory_id=right.trajectory.trajectory_id,
        overlap_start_utc_ns=overlap_start_ns,
        overlap_end_utc_ns=overlap_end_ns,
        slope_rms_difference_hz_per_s=rms[0],
        slope_max_difference_hz_per_s=maximum[0],
        acceleration_rms_difference_hz_per_s2=rms[1],
        acceleration_max_difference_hz_per_s2=maximum[1],
        jerk_rms_difference_hz_per_s3=rms[2],
        jerk_max_difference_hz_per_s3=maximum[2],
        comparison_score=score,
    )


def _derivatives(entry: _Entry, utc_ns: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = entry.path.raw_report
    local_s = (utc_ns - raw.timing.first_estimate_utc_ns) / 1e9
    relative_s = local_s - entry.trajectory.reference_time_s
    coefficients = np.asarray(entry.trajectory.absolute_coefficients_hz, dtype=np.float64)
    values = []
    for order in (1, 2, 3):
        derivative = np.polyder(coefficients, order)
        values.append(
            np.zeros_like(relative_s)
            if derivative.size == 0
            else np.polyval(derivative, relative_s)
        )
    return values[0], values[1], values[2]


def _entries(paths: tuple[PathStandardReportV2, ...]) -> tuple[_Entry, ...]:
    return tuple(
        sorted(
            (_Entry(path, trajectory) for path in paths for trajectory in path.final_trajectories),
            key=lambda item: item.key,
        )
    )


def _path_status(
    raw: StandardScientificStatus, final: StandardScientificStatus
) -> StandardScientificStatus:
    if raw is StandardScientificStatus.PARTIAL or final is StandardScientificStatus.PARTIAL:
        return StandardScientificStatus.PARTIAL
    if (
        raw is StandardScientificStatus.INSUFFICIENT_DATA
        or final is StandardScientificStatus.INSUFFICIENT_DATA
    ):
        return StandardScientificStatus.INSUFFICIENT_DATA
    if raw is StandardScientificStatus.NO_RESULT:
        return StandardScientificStatus.NO_RESULT
    return final


def _aggregate_status(statuses: tuple[StandardScientificStatus, ...]) -> StandardScientificStatus:
    if any(item is StandardScientificStatus.INSUFFICIENT_DATA for item in statuses):
        return StandardScientificStatus.INSUFFICIENT_DATA
    if any(item is StandardScientificStatus.PARTIAL for item in statuses):
        return StandardScientificStatus.PARTIAL
    if all(item is StandardScientificStatus.NO_RESULT for item in statuses):
        return StandardScientificStatus.NO_RESULT
    return StandardScientificStatus.COMPLETE


def _require_equal_raw(paths: tuple[PathStandardReportV2, ...], field: str) -> None:
    if len({getattr(item.raw_report, field) for item in paths}) != 1:
        raise ValueError(f"final path inputs disagree on {field}")


def _reason(
    label: str,
    status: StandardScientificStatus,
    association: AssociationStatus,
    candidate_truncation: int,
    trajectory_truncation: int,
) -> str:
    return (
        f"{status.value} {label} final-trajectory reduction; "
        f"derivative-association={association.value}; intercept excluded; "
        f"child truncation candidates={candidate_truncation}, "
        f"trajectories={trajectory_truncation}; candidate consistency only"
    )
