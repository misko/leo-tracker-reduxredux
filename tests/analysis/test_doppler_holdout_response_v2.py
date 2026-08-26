from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.analysis.research.doppler_holdout_pre_response import ForecastTargetKeyV1
from leo.analysis.research.doppler_holdout_response_v2 import (
    ODD_ATTACHMENT_SCHEMA_V2,
    OddQinAttachmentLedgerV2,
    OddQinAttachmentRowV2,
    OddQinResponseMeasurementV2,
)
from leo.contracts.digests import canonical_digest

DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64


def _target(index: int) -> ForecastTargetKeyV1:
    return ForecastTargetKeyV1(
        session_id="capture-a",
        episode_id=DIGEST,
        target_mask_digest=OTHER_DIGEST,
        frame_start_sample=100 + index,
        reference_sample=101.0 + index,
        continuity_segment_id=0,
    )


def _response(index: int, status: str) -> OddQinResponseMeasurementV2:
    target = _target(index)
    if status == "missing":
        return OddQinResponseMeasurementV2(
            prediction_ledger_digest=DIGEST,
            target=target,
            status="missing",
            missing_reason="authorized_chunk_unavailable",
            accuracy_disposition="missing",
        )
    common = {
        "prediction_ledger_digest": DIGEST,
        "target": target,
        "odd_absolute_cfo_hz": 100_000.0 + index,
        "odd_frequency_uncertainty_hz": 20.0,
        "odd_exact_coherence": 0.2,
        "odd_rolled_control_coherence": 0.05,
        "odd_coherence_margin": 0.15,
        "odd_phase_residual_rms_rad": 0.3,
    }
    if status == "finite":
        return OddQinResponseMeasurementV2.model_validate(
            {
                **common,
                "status": "finite",
                "accuracy_disposition": "eligible",
                "odd_search_boundary": False,
            }
        )
    if status == "boundary":
        return OddQinResponseMeasurementV2.model_validate(
            {
                **common,
                "status": "boundary",
                "accuracy_disposition": "excluded_boundary",
                "odd_search_boundary": True,
            }
        )
    return OddQinResponseMeasurementV2.model_validate(
        {
            **common,
            "status": "no_support",
            "support_reasons": ("odd_exact_coherence_below_minimum",),
            "accuracy_disposition": "excluded_no_support",
            "odd_search_boundary": False,
        }
    )


def _attachment() -> OddQinAttachmentLedgerV2:
    responses = tuple(
        _response(index, status)
        for index, status in enumerate(("finite", "boundary", "no_support", "missing"))
    )
    rows = tuple(
        OddQinAttachmentRowV2(
            target=response.target,
            prediction_ledger_digest=DIGEST,
            response=response,
        )
        for response in responses
    )
    document = {
        "schema": ODD_ATTACHMENT_SCHEMA_V2,
        "prediction_ledger_digest": DIGEST,
        "prediction_membership_or_values_mutated": False,
        "target_count": 4,
        "finite_response_count": 3,
        "accuracy_eligible_count": 1,
        "boundary_response_count": 1,
        "no_support_response_count": 1,
        "missing_response_count": 1,
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    return OddQinAttachmentLedgerV2.model_validate(
        {**document, "attachment_digest": canonical_digest(document)}
    )


def test_v2_retains_all_response_states_and_no_support_specificity() -> None:
    attachment = _attachment()

    assert attachment.target_count == 4
    assert attachment.finite_response_count == 3
    assert attachment.accuracy_eligible_count == 1
    no_support = attachment.rows[2].response
    assert no_support.status == "no_support"
    assert no_support.odd_absolute_cfo_hz == 100_002.0
    assert no_support.odd_exact_coherence == 0.2


def test_v2_digest_counts_targets_and_extra_fields_fail_closed() -> None:
    attachment = _attachment()
    raw = attachment.model_dump(mode="python")

    with pytest.raises(ValidationError, match="status accounting"):
        OddQinAttachmentLedgerV2.model_validate({**raw, "missing_response_count": 0})
    with pytest.raises(ValidationError, match="digest"):
        OddQinAttachmentLedgerV2.model_validate({**raw, "attachment_digest": OTHER_DIGEST})
    with pytest.raises(ValidationError, match="target disagrees"):
        OddQinAttachmentRowV2(
            target=_target(9),
            prediction_ledger_digest=DIGEST,
            response=_response(0, "finite"),
        )
    with pytest.raises(ValidationError, match="target_even"):
        OddQinResponseMeasurementV2.model_validate(
            {
                **_response(0, "finite").model_dump(mode="python"),
                "target_even_absolute_cfo_hz": 1.0,
            }
        )
