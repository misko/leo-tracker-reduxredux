from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from leo.analysis.research.doppler_holdout_manifest import FrameMaskDispositionV1
from leo.analysis.research.doppler_holdout_pre_response import (
    DEFAULT_STRICT_PAST_CONFIGS,
    ODD_ATTACHMENT_SCHEMA,
    PREDICTION_LEDGER_SCHEMA,
    DopplerHoldoutPredictionLedgerV1,
    ForecastTargetKeyV1,
    OddQinAttachmentLedgerV1,
    OddQinResponseMeasurementV1,
    OddQinResponseRequestV1,
    OddQinTargetAuthorityV1,
    PredictionLedgerRowV1,
    StrictPastForecastConfigV1,
    attach_odd_qin_responses,
    strict_past_forecasts,
)
from leo.contracts.digests import canonical_digest

DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
SAMPLE_RATE_HZ = 1_000


def _target(reference_sample: int = 1_001) -> ForecastTargetKeyV1:
    return ForecastTargetKeyV1(
        session_id=f"cap-{reference_sample}",
        episode_id=DIGEST,
        target_mask_digest=OTHER_DIGEST,
        frame_start_sample=reference_sample,
        reference_sample=float(reference_sample),
        continuity_segment_id=4,
    )


def _cfo(reference_sample: float, target_sample: float) -> float:
    time_s = (reference_sample - target_sample) / SAMPLE_RATE_HZ
    return 125_000.0 - 3_250.0 * time_s + 0.5 * 2_400.0 * time_s**2


def _supported_row(reference_sample: int, *, target_sample: int = 1_001) -> FrameMaskDispositionV1:
    return FrameMaskDispositionV1(
        frame_start_sample=reference_sample,
        reference_sample=float(reference_sample),
        continuity_segment_id=4,
        status="supported",
        rejection_reasons=(),
        even_absolute_cfo_hz=_cfo(reference_sample, target_sample),
        even_frequency_uncertainty_hz=50.0,
        even_exact_coherence=0.2,
        even_control_coherence=0.02,
        even_coherence_margin=0.18,
        even_search_boundary=False,
    )


def _evidence(target_sample: int = 1_001) -> tuple[FrameMaskDispositionV1, ...]:
    return tuple(
        _supported_row(reference_sample, target_sample=target_sample)
        for reference_sample in range(target_sample - 500, target_sample + 2)
    )


def _prediction_ledger(
    target: ForecastTargetKeyV1,
    evidence: Sequence[FrameMaskDispositionV1],
) -> DopplerHoldoutPredictionLedgerV1:
    row = PredictionLedgerRowV1(
        target=target,
        forecasts=strict_past_forecasts(
            target,
            evidence,
            sample_rate_hz=SAMPLE_RATE_HZ,
        ),
    )
    document = {
        "schema": PREDICTION_LEDGER_SCHEMA,
        "phase": "pre_response_prediction_freeze",
        "source_v2_file_sha256": DIGEST,
        "source_v2_manifest_digest": OTHER_DIGEST,
        "forecast_implementation_sha256": DIGEST,
        "forecast_configuration_digest": canonical_digest(
            [item.model_dump(mode="json") for item in DEFAULT_STRICT_PAST_CONFIGS]
        ),
        "future_odd_qin_outcomes_opened": False,
        "target_even_numeric_cfo_consumed": False,
        "target_count": 1,
        "rows": [row.model_dump(mode="json")],
    }
    return DopplerHoldoutPredictionLedgerV1.model_validate(
        {**document, "ledger_digest": canonical_digest(document)}
    )


def _authority(target: ForecastTargetKeyV1) -> OddQinTargetAuthorityV1:
    return OddQinTargetAuthorityV1(
        target=target,
        scope_key=DIGEST,
        stream_id="stream-1",
        radio_id="radio-1",
        receiver_id=1,
        edge="upper",
        source_id=DIGEST,
        branch_id=OTHER_DIGEST,
        trajectory_id=DIGEST,
        acquisition_absolute_cfo_hz=-115_000.0,
    )


def _boundary_response(request: OddQinResponseRequestV1) -> OddQinResponseMeasurementV1:
    return OddQinResponseMeasurementV1(
        prediction_ledger_digest=request.prediction_ledger_digest,
        target=request.authority.target,
        status="boundary",
        accuracy_disposition="excluded_boundary",
        odd_absolute_cfo_hz=9.0e11,
        odd_frequency_uncertainty_hz=12.5,
        odd_exact_coherence=0.21,
        odd_rolled_control_coherence=0.07,
        odd_coherence_margin=0.14,
        odd_phase_residual_rms_rad=0.33,
        odd_search_boundary=True,
    )


def test_target_even_numeric_poison_cannot_change_any_forecast() -> None:
    target = _target()
    evidence = _evidence()
    target_index = next(
        index
        for index, row in enumerate(evidence)
        if row.reference_sample == target.reference_sample
    )
    poisoned = list(evidence)
    poisoned[target_index] = poisoned[target_index].model_copy(
        update={"even_absolute_cfo_hz": -9.9e99}
    )

    baseline = strict_past_forecasts(target, evidence, sample_rate_hz=SAMPLE_RATE_HZ)
    after_poison = strict_past_forecasts(target, poisoned, sample_rate_hz=SAMPLE_RATE_HZ)

    assert baseline == after_poison
    assert all(item.status == "complete" for item in baseline)
    assert all(item.latest_history_reference_sample < target.reference_sample for item in baseline)
    assert "even" not in " ".join(target.model_dump().keys())


def test_lean_quadratic_recovers_target_level_rate_and_acceleration() -> None:
    forecasts = strict_past_forecasts(
        _target(),
        _evidence(),
        sample_rate_hz=SAMPLE_RATE_HZ,
    )
    quadratic = forecasts[-1]

    assert quadratic.method == "lean_500ms_quadratic"
    assert quadratic.status == "complete"
    assert quadratic.converged is True
    assert quadratic.predicted_cfo_hz == pytest.approx(125_000.0, abs=1e-6)
    assert quadratic.rate_hz_s == pytest.approx(-3_250.0, abs=1e-6)
    assert quadratic.acceleration_hz_s2 == pytest.approx(2_400.0, abs=1e-5)


def test_nonconverged_irls_fails_closed_without_estimates() -> None:
    target = _target()
    evidence = list(_evidence())
    evidence[-100] = evidence[-100].model_copy(update={"even_absolute_cfo_hz": 10_000_000.0})
    configs = tuple(
        StrictPastForecastConfigV1.model_validate(
            {
                **config.model_dump(mode="python"),
                "maximum_iterations": 1,
                "prediction_convergence_hz": 1e-30,
            }
        )
        for config in DEFAULT_STRICT_PAST_CONFIGS
    )

    forecasts = strict_past_forecasts(
        target,
        evidence,
        sample_rate_hz=SAMPLE_RATE_HZ,
        configs=configs,
    )

    failed = tuple(item for item in forecasts if "fit_not_converged" in item.rejection_reasons)
    assert failed
    assert all(item.status == "no_result" for item in failed)
    assert all(item.predicted_cfo_hz is None and item.converged is None for item in failed)


def test_odd_port_sees_no_even_value_and_cannot_mutate_prediction_ledger() -> None:
    target = _target()
    ledger = _prediction_ledger(target, _evidence())
    ledger_before = ledger.model_dump(mode="json")

    class SpyPort:
        requests: list[OddQinResponseRequestV1]

        def __init__(self) -> None:
            self.requests = []

        def measure_odd_qin(self, request: OddQinResponseRequestV1) -> OddQinResponseMeasurementV1:
            self.requests.append(request)
            request_fields = repr(request.model_dump(mode="json")).lower()
            assert "even_absolute_cfo" not in request_fields
            assert request.authority.qin_symbol_indices == "zero-based-odd-1-through-299"
            return _boundary_response(request)

    port = SpyPort()
    attachment = attach_odd_qin_responses(ledger, (_authority(target),), port)

    assert len(port.requests) == 1
    assert ledger.model_dump(mode="json") == ledger_before
    assert attachment.schema == ODD_ATTACHMENT_SCHEMA
    assert attachment.prediction_ledger_digest == ledger.ledger_digest
    assert attachment.target_count == 1
    assert attachment.finite_response_count == 1
    assert attachment.accuracy_eligible_count == 0
    assert attachment.boundary_response_count == 1
    assert attachment.rows[0].response_denominator_member is True
    response = attachment.rows[0].response
    assert response.odd_exact_coherence == 0.21
    assert response.odd_rolled_control_coherence == 0.07
    assert response.odd_coherence_margin == 0.14
    assert response.odd_phase_residual_rms_rad == 0.33
    assert response.odd_absolute_cfo_hz == 9.0e11


def test_odd_response_contract_forbids_extra_target_even_evidence() -> None:
    target = _target()
    request = OddQinResponseRequestV1(
        prediction_ledger_digest=DIGEST,
        authority=_authority(target),
    )
    response = _boundary_response(request)

    with pytest.raises(ValidationError, match="target_even_absolute_cfo_hz"):
        OddQinResponseMeasurementV1.model_validate(
            {
                **response.model_dump(mode="python"),
                "target_even_absolute_cfo_hz": -123_456.0,
            }
        )


def test_no_support_and_missing_are_explicit_and_value_free() -> None:
    target = _target()
    no_support = OddQinResponseMeasurementV1(
        prediction_ledger_digest=DIGEST,
        target=target,
        status="no_support",
        support_reasons=("odd_fold_below_support",),
        accuracy_disposition="excluded_no_support",
    )
    missing = OddQinResponseMeasurementV1(
        prediction_ledger_digest=DIGEST,
        target=target,
        status="missing",
        missing_reason="odd_response_unavailable",
        accuracy_disposition="missing",
    )

    assert no_support.odd_exact_coherence is None
    assert missing.odd_absolute_cfo_hz is None
    with pytest.raises(ValidationError, match="no-support"):
        OddQinResponseMeasurementV1.model_validate(
            {
                **no_support.model_dump(mode="python"),
                "odd_exact_coherence": 0.2,
            }
        )


def test_prediction_and_attachment_models_are_frozen_and_digest_closed() -> None:
    target = _target()
    ledger = _prediction_ledger(target, _evidence())

    with pytest.raises(ValidationError, match="frozen"):
        ledger.target_count = 2
    with pytest.raises(ValidationError, match="digest"):
        DopplerHoldoutPredictionLedgerV1.model_validate(
            {
                **ledger.model_dump(mode="python"),
                "forecast_implementation_sha256": OTHER_DIGEST,
            }
        )

    class BoundaryPort:
        def measure_odd_qin(self, request: OddQinResponseRequestV1) -> OddQinResponseMeasurementV1:
            return _boundary_response(request)

    attachment = attach_odd_qin_responses(ledger, (_authority(target),), BoundaryPort())
    with pytest.raises(ValidationError, match="digest"):
        OddQinAttachmentLedgerV1.model_validate(
            {**attachment.model_dump(mode="python"), "attachment_digest": OTHER_DIGEST}
        )
