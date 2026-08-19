from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from leo.analysis.presentation import whole_dwell_timeline_documents
from leo.analysis.starlink import NumericalStatus
from leo.presentation.models import (
    AnalysisStageTimelineV1,
    CarrierTimingTimelineV1,
    CurrentRunStageMatrixV1,
    QamTimelineV1,
)


def _bundle(*, candidate_count: int = 1, with_qam: bool = True) -> SimpleNamespace:
    candidates = tuple(
        SimpleNamespace(
            candidate_id=f"candidate-{index}",
            observation=SimpleNamespace(
                receiver_id=0,
                absolute_epoch_sample=3_783_709 + 2_500_000 * index,
                absolute_cfo_hz=100_000.0 + index * 25.0,
                verify_minus_control_margin=0.02,
            ),
        )
        for index in range(candidate_count)
    )
    metrics = SimpleNamespace(hard_symbol_accuracy=0.91, rms_evm=0.42, frame_count=12)
    qam_result = SimpleNamespace(metrics=metrics if with_qam else None)
    return SimpleNamespace(
        waterfall=SimpleNamespace(sample_rate_hz=2_500_000.0),
        cloud=SimpleNamespace(candidates=candidates),
        tracks=SimpleNamespace(
            tracks=(
                SimpleNamespace(
                    track_id="track-1",
                    candidate_ids=tuple(item.candidate_id for item in candidates),
                ),
            )
        ),
        doppler=SimpleNamespace(
            status=NumericalStatus.COMPLETE,
            reference_time_s=3_783_709 / 2_500_000,
            frequency_at_reference_hz=100_000.0,
            slope_hz_s=25.0,
            acceleration_hz_s2=0.0,
            source_candidate_ids=tuple(item.candidate_id for item in candidates),
        ),
        qam=SimpleNamespace(
            receiver_ids=(0,),
            receiver_epoch_samples=(3_783_709,),
            receiver_results=(qam_result,),
        ),
    )


def test_timeline_documents_are_bounded_and_validate_as_typed_contracts() -> None:
    documents = whole_dwell_timeline_documents("run-1", _bundle(candidate_count=300))

    carrier = CarrierTimingTimelineV1.model_validate(documents["carrier-timing.presentation"])
    qam = QamTimelineV1.model_validate(documents["qam-timeline.presentation"])
    stages = AnalysisStageTimelineV1.model_validate(
        documents["analysis-stage-timeline.presentation"]
    )

    assert carrier.source_point_count == 300
    assert carrier.returned_point_count == 256
    assert carrier.truncated is True
    assert carrier.points[0].time_s == pytest.approx(1.5134836)
    assert carrier.points[0].fitted_baseband_cfo_hz == 100_000.0
    assert carrier.points[0].used_by_doppler_fit is True
    assert qam.state == "partial"
    assert qam.continuous_time_series_available is False
    assert qam.temporal_resolution == "aggregate_candidate_window"
    assert qam.points[0].time_s == pytest.approx(1.5134836)
    assert stages.state == "unavailable"
    assert stages.stages == ()


def test_missing_qam_is_explicitly_unavailable_not_a_synthetic_curve() -> None:
    document = whole_dwell_timeline_documents("run-1", _bundle(with_qam=False))[
        "qam-timeline.presentation"
    ]

    qam = QamTimelineV1.model_validate(document)

    assert qam.state == "unavailable"
    assert qam.points == ()
    assert "no candidate-window QAM" in qam.reason


def test_timeline_contract_rejects_false_counts() -> None:
    document = whole_dwell_timeline_documents("run-1", _bundle())["carrier-timing.presentation"]
    document["returned_point_count"] = 0

    with pytest.raises(ValidationError, match="returned carrier point count"):
        CarrierTimingTimelineV1.model_validate(document)


def test_current_run_stage_matrix_is_bounded_and_rejects_duplicate_scopes() -> None:
    stages = [
        {
            "job_id": 1,
            "stage_key": "qam",
            "scope_key": "stream-0",
            "state": "succeeded",
            "outcome": "complete",
        }
    ]
    matrix = CurrentRunStageMatrixV1.model_validate(
        {
            "analysis_run_id": "run-1",
            "source_stage_count": 1,
            "returned_stage_count": 1,
            "truncated": False,
            "stages": stages,
        }
    )
    assert matrix.stages[0].outcome == "complete"

    with pytest.raises(ValidationError, match="unique stage and scope"):
        CurrentRunStageMatrixV1.model_validate(
            {
                "analysis_run_id": "run-1",
                "source_stage_count": 2,
                "returned_stage_count": 2,
                "truncated": False,
                "stages": [*stages, {**stages[0], "job_id": 2}],
            }
        )
