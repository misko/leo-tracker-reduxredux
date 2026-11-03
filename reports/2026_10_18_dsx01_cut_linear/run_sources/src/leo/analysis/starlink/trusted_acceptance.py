"""Pure evaluators for additive trusted matched-recovery V2 evidence."""

from __future__ import annotations

from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import (
    LegacyExecutionEnvelopeV1,
    MatchedPilotAcceptanceCampaignConfigV1,
    MatchedPilotAcceptanceConfigV1,
    NativeKnownPilotEvidenceProductV2,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    _recomputed_receipt_status,
    calibration_search_domain_covers,
)
from leo.contracts.trusted_scientific import (
    TrustedCampaignStreamV2,
    TrustedMatchedPilotWindowV2,
    TrustedMatchedRecoveryCampaignReceiptV2,
    TrustedMatchedRecoveryProductV2,
    TrustedMatchedRecoveryReceiptV2,
    _aggregate_stratum_v2,
    _campaign_status,
    _qam_positive,
    _recovery_summary,
)


def evaluate_trusted_matched_recovery_v2(
    *,
    analysis_run_id: str,
    config: MatchedPilotAcceptanceConfigV1,
    path_identity: ReceiverPathIdentityV1,
    calibration: ReceiverFrequencyCalibrationV1,
    legacy_execution: LegacyExecutionEnvelopeV1,
    native_evidence: NativeKnownPilotEvidenceProductV2,
) -> TrustedMatchedRecoveryProductV2:
    """Replay both sealed executions without rereading infrastructure state."""

    config = MatchedPilotAcceptanceConfigV1.model_validate(config.model_dump(mode="json"))
    path_identity = ReceiverPathIdentityV1.model_validate(path_identity.model_dump(mode="json"))
    calibration = ReceiverFrequencyCalibrationV1.model_validate(calibration.model_dump(mode="json"))
    legacy_execution = LegacyExecutionEnvelopeV1.model_validate(
        legacy_execution.model_dump(mode="json")
    )
    native_evidence = NativeKnownPilotEvidenceProductV2.model_validate(
        native_evidence.model_dump(mode="json")
    )
    windows = tuple(
        _matched_window_v2(reference, native)
        for reference, native in zip(
            legacy_execution.decisions,
            native_evidence.execution.decisions,
            strict=True,
        )
    )
    summary = _recovery_summary(windows, config)
    verified = summary.complete_raw_window_count == 600 and summary.evaluated_pair_count == 600
    eligible = verified and calibration_search_domain_covers(calibration, config)
    status, reason = _recomputed_receipt_status(
        preflight_failed=not eligible,
        complete_raw=summary.complete_raw_window_count,
        insufficient=summary.missing_or_insufficient_window_count,
        recovery=summary.recovery,
        reference_qam=summary.reference_qam_positive_count,
        qam_passed=summary.qam_noninferiority_passed,
        config=config,
    )
    receipt_values = {
        "schema_version": 2,
        "kind": "trusted-matched-pilot-recovery",
        "config": config.model_dump(mode="json"),
        "path_identity": path_identity.model_dump(mode="json"),
        "calibration": calibration.model_dump(mode="json"),
        "legacy_execution": legacy_execution.model_dump(mode="json"),
        "native_release": native_evidence.release.model_dump(mode="json"),
        "native_execution": native_evidence.execution.model_dump(mode="json"),
        "native_evidence_product_digest": native_evidence.product_digest,
        "content_complete": verified,
        "mathematical_eligible": eligible,
        "acceptance_eligible": False,
        "production_accepted": False,
        "status": status.value,
        "reason": reason,
        "scheduled_window_count": 600,
        **summary.model_dump(mode="json"),
        "qam_interval_method": config.qam_interval_method,
        "windows": tuple(item.model_dump(mode="json") for item in windows),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "attribution_claimed": False,
    }
    receipt = TrustedMatchedRecoveryReceiptV2.model_validate(
        {**receipt_values, "receipt_digest": canonical_digest(receipt_values)}
    )
    product_values = {
        "schema_version": 2,
        "kind": "trusted-matched-pilot-recovery-product",
        "analysis_run_id": analysis_run_id,
        "scope_key": path_identity.stream_id,
        "pipeline_release": config.detector_binding.pipeline_release,
        "receipt": receipt.model_dump(mode="json"),
        "sealed": True,
    }
    return TrustedMatchedRecoveryProductV2.model_validate(
        {**product_values, "product_digest": canonical_digest(product_values)}
    )


def evaluate_trusted_campaign_v2(
    *,
    config: MatchedPilotAcceptanceCampaignConfigV1,
    products: tuple[TrustedMatchedRecoveryProductV2, ...],
) -> TrustedMatchedRecoveryCampaignReceiptV2:
    """Replay the exact accepted capture inventory and its four frozen strata."""

    config = MatchedPilotAcceptanceCampaignConfigV1.model_validate(config.model_dump(mode="json"))
    products = tuple(
        TrustedMatchedRecoveryProductV2.model_validate(item.model_dump(mode="json"))
        for item in products
    )
    inventory = {(item.session_id, item.stream_id): item for item in config.capture_inventory}
    strata = {(item.radio_id, item.role): item.stratum_id for item in config.strata}
    streams: list[TrustedCampaignStreamV2] = []
    for product in products:
        identity = product.receipt.path_identity
        accepted = inventory.get((identity.session_id, identity.stream_id))
        if accepted is None:
            raise ValueError("trusted matched product is outside accepted capture inventory")
        streams.append(
            TrustedCampaignStreamV2(
                stratum_id=strata[(accepted.radio_id, accepted.role)],
                pairing_group_id=accepted.pairing_group_id,
                product=product,
            )
        )
    ordered = tuple(
        sorted(
            streams,
            key=lambda item: (
                item.stratum_id,
                item.product.receipt.path_identity.session_id,
                item.product.scope_key,
            ),
        )
    )
    complete = len(ordered) == 40 and all(item.product.receipt.content_complete for item in ordered)
    eligible = complete and all(item.product.receipt.mathematical_eligible for item in ordered)
    results = tuple(
        _aggregate_stratum_v2(
            declaration.stratum_id,
            tuple(item for item in ordered if item.stratum_id == declaration.stratum_id),
            declaration.required_session_count,
            declaration.minimum_reference_positive_count,
        )
        for declaration in config.strata
    )
    status, reason = _campaign_status(results, eligible)
    values = {
        "schema_version": 2,
        "kind": "trusted-matched-pilot-recovery-campaign",
        "config": config.model_dump(mode="json"),
        "content_complete": complete,
        "mathematical_eligible": eligible,
        "acceptance_eligible": False,
        "production_accepted": False,
        "status": status.value,
        "reason": reason,
        "expected_stream_count": 40,
        "observed_stream_count": 40,
        "expected_session_count": 30,
        "observed_session_count": 30,
        "streams": tuple(item.model_dump(mode="json") for item in ordered),
        "strata": tuple(item.model_dump(mode="json") for item in results),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "attribution_claimed": False,
    }
    return TrustedMatchedRecoveryCampaignReceiptV2.model_validate(
        {**values, "receipt_digest": canonical_digest(values)}
    )


def _matched_window_v2(
    reference: PilotWindowDecisionV1,
    native: PilotWindowDecisionV1,
) -> TrustedMatchedPilotWindowV2:
    epoch_error: int | None = None
    cfo_error: float | None = None
    associated = False
    if reference.candidate is True and native.candidate is True:
        assert reference.epoch_sample is not None and native.epoch_sample is not None
        assert reference.cfo_hz is not None and native.cfo_hz is not None
        period = round(2_500_000 / 750)
        raw_error = abs(reference.epoch_sample - native.epoch_sample) % period
        epoch_error = min(raw_error, period - raw_error)
        cfo_error = abs(reference.cfo_hz - native.cfo_hz)
        associated = epoch_error <= 8 and cfo_error <= 500.0
    complete = bool(
        reference.status is PilotDecisionStatus.EVALUATED
        and native.status is PilotDecisionStatus.EVALUATED
        and reference.window_iq_digest is not None
        and reference.window_iq_digest == native.window_iq_digest
    )
    difference = (
        native.qam_accuracy - reference.qam_accuracy
        if associated and reference.qam_accuracy is not None and native.qam_accuracy is not None
        else None
    )
    return TrustedMatchedPilotWindowV2(
        window_index=reference.window_index,
        sample_start=reference.sample_start,
        raw_window_complete=complete,
        reference=reference,
        native=native,
        candidate_associated=associated,
        circular_epoch_error_samples=epoch_error,
        absolute_cfo_error_hz=cfo_error,
        reference_qam_positive=_qam_positive(reference),
        native_qam_positive=_qam_positive(native),
        qam_accuracy_difference=difference,
    )
