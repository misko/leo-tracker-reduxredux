from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.qualification.frequency_calibration import (
    FrequencyCalibrationDwellV1,
    FrequencyCalibrationEvidenceV1,
    FrequencyCalibrationPlanV1,
    generate_frequency_calibration,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _plan(**updates: object) -> FrequencyCalibrationPlanV1:
    values: dict[str, object] = {
        "plan_id": "cal-plan-radio-a-rx1",
        "declared_utc_ns": 100,
        "radio_id": "radio-a",
        "radio_serial": "serial-a",
        "physical_receiver_id": "rx_lnb_b",
        "hardware_epoch_id": "topology-epoch-a",
        "topology_evidence_digest": DIGEST_A,
        "profile_name": "starlink-ch4-lower-2p5m-60s-rx1",
        "profile_revision_digest": DIGEST_B,
        "candidate_extractor_digest": DIGEST_C,
        "center_frequency_hz": 1_709_687_500,
        "scheduled_session_ids": ("cal-a-1", "cal-a-2", "cal-a-3"),
        "minimum_usable_candidates": 9,
        "minimum_distinct_usable_sessions": 3,
    }
    values.update(updates)
    return FrequencyCalibrationPlanV1.create(**values)


def _dwell(
    index: int,
    offsets: tuple[float, ...],
    **updates: object,
) -> FrequencyCalibrationDwellV1:
    values: dict[str, object] = {
        "scheduled_index": index,
        "session_id": f"cal-a-{index + 1}",
        "stream_id": f"stream-{index + 1}",
        "radio_id": "radio-a",
        "radio_serial": "serial-a",
        "physical_receiver_id": "rx_lnb_b",
        "hardware_epoch_id": "topology-epoch-a",
        "topology_evidence_digest": DIGEST_A,
        "manifest_digest": "sha256:" + str(index + 1) * 64,
        "profile_revision_digest": DIGEST_B,
        "capture_start_utc_ns": 1_000_000_000_000 + index * 100_000_000_000,
        "capture_end_utc_ns": 1_060_000_000_000 + index * 100_000_000_000,
        "sample_rate_hz": 2_500_000,
        "sample_count": 150_000_000,
        "candidate_extractor_digest": DIGEST_C,
        "observation_digest": "sha256:" + str(index + 4) * 64,
        "status": "usable",
        "candidate_offsets_hz": offsets,
        "status_reason": "predeclared blind pilot search completed",
    }
    values.update(updates)
    return FrequencyCalibrationDwellV1(**values)


def _good_dwells() -> tuple[FrequencyCalibrationDwellV1, ...]:
    return (
        _dwell(0, (-1_000.0, 0.0, 1_000.0)),
        _dwell(1, (-500.0, 500.0, 1_500.0)),
        _dwell(2, (-200.0, 800.0, 1_800.0)),
    )


def test_generates_content_addressed_empirical_center_after_last_dwell() -> None:
    plan = _plan()
    generated = generate_frequency_calibration(
        plan=plan,
        dwells=_good_dwells(),
        calibration_id="cal-radio-a-rx1-epoch-a",
        calibration_set_id="cal-set-epoch-a",
        created_utc_ns=2_000_000_000_000,
    )
    assert generated.evidence.status == "sufficient"
    assert generated.evidence.usable_candidate_count == 9
    assert generated.evidence.usable_session_count == 3
    assert generated.evidence.empirical_center_hz == 500.0
    assert generated.evidence.sampled_band_margin_hz is not None
    assert generated.evidence.sampled_band_margin_hz > 0
    assert generated.evidence.residual_search_margin_hz is not None
    assert generated.evidence.residual_search_margin_hz > 0
    assert generated.calibration is not None
    assert generated.calibration.hardware_epoch_id == "topology-epoch-a"
    assert generated.calibration.receiver_id == 1
    assert generated.calibration.valid_from_utc_ns == max(
        dwell.capture_end_utc_ns for dwell in _good_dwells()
    ) + 1
    assert generated.calibration.method == "median_mad_empirical_pilot_acquisition_center_v1"
    assert generated.calibration.evidence[0].digest == generated.evidence.evidence_digest
    assert generated.calibration_set is not None
    assert generated.calibration_set.calibrations == (generated.calibration,)


def test_weak_campaign_is_insufficient_and_never_emits_zero_fallback() -> None:
    dwells = (
        _dwell(0, (-162_000.0,)),
        _dwell(
            1,
            (),
            status="unusable",
            status_reason="no candidate passed the frozen extractor",
        ),
        _dwell(2, (-161_000.0,)),
    )
    generated = generate_frequency_calibration(
        plan=_plan(),
        dwells=dwells,
        calibration_id="not-issued",
        calibration_set_id="not-issued",
        created_utc_ns=2_000_000_000_000,
    )

    assert generated.evidence.status == "insufficient"
    assert "minimum_usable_candidates_not_met" in generated.evidence.reasons
    assert "minimum_distinct_usable_sessions_not_met" in generated.evidence.reasons
    assert tuple(item.status for item in generated.evidence.dwells) == (
        "usable",
        "unusable",
        "usable",
    )
    assert generated.calibration is None
    assert generated.calibration_set is None


def test_multimodal_evidence_is_insufficient() -> None:
    dwells = (
        _dwell(0, (-202_000.0, -201_000.0, -200_000.0)),
        _dwell(1, (-102_000.0, -101_000.0, -100_000.0)),
        _dwell(2, (-201_500.0, -101_500.0, -100_500.0)),
    )
    generated = generate_frequency_calibration(
        plan=_plan(maximum_robust_sigma_hz=200_000.0),
        dwells=dwells,
        calibration_id="not-issued",
        calibration_set_id="not-issued",
        created_utc_ns=2_000_000_000_000,
    )

    assert generated.evidence.status == "insufficient"
    assert "multimodal_candidate_evidence" in generated.evidence.reasons
    assert generated.calibration is None


def test_residual_search_must_cover_uncertainty_plus_300khz_doppler_guard() -> None:
    generated = generate_frequency_calibration(
        plan=_plan(residual_search_half_width_hz=301_000.0),
        dwells=_good_dwells(),
        calibration_id="not-issued",
        calibration_set_id="not-issued",
        created_utc_ns=2_000_000_000_000,
    )
    assert generated.evidence.status == "insufficient"
    assert (
        "residual_search_does_not_cover_uncertainty_and_doppler_guard"
        in generated.evidence.reasons
    )


def test_sampled_band_rejects_historical_rx1_center_with_300khz_guard() -> None:
    dwells = (
        _dwell(0, (-163_000.0, -162_000.0, -161_000.0)),
        _dwell(1, (-162_500.0, -161_500.0, -160_500.0)),
        _dwell(2, (-162_200.0, -161_200.0, -160_200.0)),
    )
    generated = generate_frequency_calibration(
        plan=_plan(),
        dwells=dwells,
        calibration_id="not-issued",
        calibration_set_id="not-issued",
        created_utc_ns=2_000_000_000_000,
    )

    assert generated.evidence.status == "insufficient"
    assert (
        "sampled_band_does_not_cover_pilot_uncertainty_and_doppler_guard"
        in generated.evidence.reasons
    )
    assert generated.calibration is None


def test_campaign_rejects_identity_or_acceptance_geometry_reuse() -> None:
    with pytest.raises(ValueError, match="frozen plan"):
        generate_frequency_calibration(
            plan=_plan(),
            dwells=(_dwell(0, (-1.0,), hardware_epoch_id="other"), *_good_dwells()[1:]),
            calibration_id="not-issued",
            calibration_set_id="not-issued",
            created_utc_ns=2_000_000_000_000,
        )

    with pytest.raises(ValidationError, match="frequency_calibration_only"):
        _dwell(0, (-1.0,), capture_purpose="acceptance")
    with pytest.raises(ValidationError, match="exactly 60 seconds"):
        _dwell(0, (-1.0,), sample_count=149_999_999)


def test_evidence_and_plan_are_tamper_evident() -> None:
    plan = _plan()
    plan_document = plan.model_dump(mode="python")
    plan_document["center_frequency_hz"] = 1
    with pytest.raises(ValidationError, match="plan digest"):
        FrequencyCalibrationPlanV1(**plan_document)

    generated = generate_frequency_calibration(
        plan=plan,
        dwells=_good_dwells(),
        calibration_id="cal-a",
        calibration_set_id="set-a",
        created_utc_ns=2_000_000_000_000,
    )
    receipt_document = generated.evidence.model_dump(mode="python")
    receipt_document["usable_candidate_count"] = 999
    with pytest.raises(ValidationError, match="evidence digest"):
        FrequencyCalibrationEvidenceV1(**receipt_document)
