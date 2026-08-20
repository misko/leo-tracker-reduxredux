from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo.analysis.standard.final_reports import reduce_radio_v2
from leo.contracts.cfo_dealias import FinalTrajectoryV1
from leo.contracts.digests import canonical_digest
from leo.contracts.final_trajectory_reports import PathStandardReportV2
from leo.contracts.standard_pipeline import PathStandardReportV1


def _raw_path(*, receiver_id: int) -> PathStandardReportV1:
    source = json.loads(
        Path("corpus/goldens/trial-132-standard-v2-one-second-frozen.json").read_bytes()
    )["products"]["report"]
    values = {**source, "receiver_id": receiver_id}
    values.pop("report_digest")
    return PathStandardReportV1(**values, report_digest=canonical_digest(values))


def _trajectory(
    name: str,
    *,
    intercept_hz: float,
    slope_hz_per_s: float = -2_000.0,
) -> FinalTrajectoryV1:
    observations = tuple(
        sorted(canonical_digest({"trajectory": name, "point": index}) for index in range(4))
    )
    return FinalTrajectoryV1(
        trajectory_id=canonical_digest({"final": name}),
        component_id=canonical_digest({"component": name}),
        branch_id=canonical_digest({"branch": name}),
        canonical_model_id=canonical_digest({"model": name}),
        alias_index=0,
        polynomial_degree=1,
        reference_time_s=0.0,
        canonical_coefficients_hz=(slope_hz_per_s, intercept_hz),
        absolute_coefficients_hz=(slope_hz_per_s, intercept_hz),
        start_s=0.0,
        end_s=1.0,
        observation_ids=observations,
        replayed_probe_count=4,
        median_margin_delta=0.2,
        median_control_separation=0.3,
    )


def _path(*, receiver_id: int, trajectory: FinalTrajectoryV1) -> PathStandardReportV2:
    raw = _raw_path(receiver_id=receiver_id)
    values = {
        "schema_version": 2,
        "algorithm_version": "standard-path-report-v2",
        "raw_report": raw.model_dump(mode="json"),
        "cfo_alias_map_digest": canonical_digest({"alias": receiver_id}),
        "dealiased_trajectory_bank_digest": canonical_digest({"canonical": receiver_id}),
        "cfo_lift_replay_digest": canonical_digest({"replay": receiver_id}),
        "final_trajectory_bank_digest": canonical_digest({"bank": receiver_id}),
        "final_trajectory_table_digest": canonical_digest({"table": receiver_id}),
        "source_trajectory_count": 1,
        "returned_trajectory_count": 1,
        "truncated_trajectory_count": 0,
        "final_trajectories": [trajectory.model_dump(mode="json")],
        "status": "complete",
        "reason": "complete final path fixture with replay-supported candidate evidence",
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PathStandardReportV2(**values, report_digest=canonical_digest(values))


def test_radio_v2_compares_derivatives_and_ignores_absolute_cfo_intercept() -> None:
    left = _path(receiver_id=0, trajectory=_trajectory("left", intercept_hz=-350_000.0))
    right = _path(receiver_id=1, trajectory=_trajectory("right", intercept_hz=350_000.0))

    report = reduce_radio_v2((right, left), declared_receiver_ids=(0, 1))

    assert report.status == "complete"
    assert len(report.derivative_associations) == 1
    association = report.derivative_associations[0]
    assert association.comparison_basis == "slope_acceleration_jerk_only"
    assert association.slope_rms_difference_hz_per_s == pytest.approx(0.0)
    assert association.acceleration_rms_difference_hz_per_s2 == pytest.approx(0.0)
    assert association.jerk_rms_difference_hz_per_s3 == pytest.approx(0.0)
    assert association.comparison_score == pytest.approx(0.0)


def test_radio_v2_exposes_derivative_disagreement_without_using_intercept() -> None:
    left = _path(receiver_id=0, trajectory=_trajectory("left-slope", intercept_hz=0.0))
    right = _path(
        receiver_id=1,
        trajectory=_trajectory("right-slope", intercept_hz=0.0, slope_hz_per_s=-5_000.0),
    )

    report = reduce_radio_v2((left, right), declared_receiver_ids=(0, 1))

    association = report.derivative_associations[0]
    assert association.slope_rms_difference_hz_per_s == pytest.approx(3_000.0)
    assert association.slope_max_difference_hz_per_s == pytest.approx(3_000.0)
    assert association.comparison_score == pytest.approx(3_000.0)
