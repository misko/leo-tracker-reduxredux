"""Additive trusted matched-recovery and campaign scientific contracts.

These V2 contracts deliberately leave the persisted V1 contracts unchanged.  The
inner receipts contain scientific evidence and derived results only; artifact URIs,
catalog identifiers, and presentation projections belong to a later application seal.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.scientific import (
    AcceptanceCampaignStratumResultV1,
    AcceptanceStreamRole,
    BinomialLowerBoundsV1,
    LegacyExecutionEnvelopeV1,
    MatchedAcceptanceStatus,
    MatchedCandidateCountsV1,
    MatchedPilotAcceptanceCampaignConfigV1,
    MatchedPilotAcceptanceConfigV1,
    NativeExecutionReceiptV2,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    TrustedNativeReleaseEvidenceV2,
    _recomputed_receipt_status,
    calibration_search_domain_covers,
)


class TrustedMatchedPilotWindowV2(ContractModel):
    """One replayed legacy/native decision pair over the same normalized IQ."""

    schema_version: Literal[2] = 2
    window_index: Annotated[int, Field(ge=0, lt=600)]
    sample_start: Annotated[int, Field(ge=0)]
    raw_window_complete: bool
    reference: PilotWindowDecisionV1
    native: PilotWindowDecisionV1
    candidate_associated: bool
    circular_epoch_error_samples: Annotated[int | None, Field(ge=0)] = None
    absolute_cfo_error_hz: Annotated[float | None, Field(ge=0)] = None
    reference_qam_positive: bool
    native_qam_positive: bool
    qam_accuracy_difference: float | None = None

    @model_validator(mode="after")
    def _replay_decisions(self) -> Self:
        if self.sample_start != self.window_index * 250_000:
            raise ValueError("trusted window disagrees with the frozen 600-window schedule")
        if any(
            decision.window_index != self.window_index or decision.sample_start != self.sample_start
            for decision in (self.reference, self.native)
        ):
            raise ValueError("trusted window decision identity is retargeted")
        if self.reference.source != "legacy_reference" or self.native.source != "native":
            raise ValueError("trusted window detector roles are not frozen")
        reference_complete = (
            self.reference.status is PilotDecisionStatus.EVALUATED
            and self.reference.window_iq_digest is not None
        )
        native_complete = (
            self.native.status is PilotDecisionStatus.EVALUATED
            and self.native.window_iq_digest is not None
        )
        complete = bool(
            reference_complete
            and native_complete
            and self.reference.window_iq_digest == self.native.window_iq_digest
        )
        if (
            self.reference.window_iq_digest is not None
            and self.native.window_iq_digest is not None
            and self.reference.window_iq_digest != self.native.window_iq_digest
        ):
            raise ValueError("trusted decisions do not bind the same normalized IQ window")
        if self.raw_window_complete != complete:
            raise ValueError("trusted raw-window completeness was not replayed")
        epoch_error: int | None = None
        cfo_error: float | None = None
        associated = False
        if self.reference.candidate is True and self.native.candidate is True:
            assert self.reference.epoch_sample is not None
            assert self.native.epoch_sample is not None
            assert self.reference.cfo_hz is not None
            assert self.native.cfo_hz is not None
            period = round(2_500_000 / 750)
            raw_error = abs(self.reference.epoch_sample - self.native.epoch_sample) % period
            epoch_error = min(raw_error, period - raw_error)
            cfo_error = abs(self.reference.cfo_hz - self.native.cfo_hz)
            associated = epoch_error <= 8 and cfo_error <= 500.0
        reference_qam = _qam_positive(self.reference)
        native_qam = _qam_positive(self.native)
        difference = (
            self.native.qam_accuracy - self.reference.qam_accuracy
            if associated
            and self.reference.qam_accuracy is not None
            and self.native.qam_accuracy is not None
            else None
        )
        if (
            self.candidate_associated != associated
            or self.circular_epoch_error_samples != epoch_error
            or self.absolute_cfo_error_hz != cfo_error
            or self.reference_qam_positive != reference_qam
            or self.native_qam_positive != native_qam
            or self.qam_accuracy_difference != difference
        ):
            raise ValueError("trusted window association/QAM values were not replayed")
        return self


class TrustedMatchedRecoveryReceiptV2(ContractModel):
    """Inner scientific receipt built only from sealed same-scope executions."""

    schema_version: Literal[2] = 2
    kind: Literal["trusted-matched-pilot-recovery"] = "trusted-matched-pilot-recovery"
    config: MatchedPilotAcceptanceConfigV1
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1
    legacy_execution: LegacyExecutionEnvelopeV1
    native_release: TrustedNativeReleaseEvidenceV2
    native_execution: NativeExecutionReceiptV2
    native_evidence_product_digest: Sha256Digest
    content_complete: bool
    mathematical_eligible: bool
    acceptance_eligible: Literal[False] = False
    production_accepted: Literal[False] = False
    status: MatchedAcceptanceStatus
    reason: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    scheduled_window_count: Literal[600] = 600
    complete_raw_window_count: Annotated[int, Field(ge=0, le=600)]
    evaluated_pair_count: Annotated[int, Field(ge=0, le=600)]
    missing_or_insufficient_window_count: Annotated[int, Field(ge=0, le=600)]
    counts: MatchedCandidateCountsV1
    associated_reference_positive_count: Annotated[int, Field(ge=0, le=600)]
    recovery: BinomialLowerBoundsV1
    reference_qam_positive_count: Annotated[int, Field(ge=0, le=600)]
    native_qam_recovery_count: Annotated[int, Field(ge=0, le=600)]
    mean_qam_accuracy_difference: float | None
    qam_accuracy_difference_lower_bound: float | None
    qam_interval_method: Literal["paired-student-t-one-sided-95"]
    qam_noninferiority_passed: bool | None
    windows: tuple[TrustedMatchedPilotWindowV2, ...]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    attribution_claimed: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _replay_complete_evidence(self) -> Self:
        binding = self.config.detector_binding
        legacy = self.legacy_execution
        if not self.calibration.matches(self.path_identity):
            raise ValueError("trusted calibration does not cover the exact receiver dwell")
        if (
            self.native_execution.input_manifest_digest != self.path_identity.manifest_digest
            or self.native_execution.session_id != self.path_identity.session_id
            or self.native_execution.stream_id != self.path_identity.stream_id
            or self.native_execution.calibration_digest != self.calibration.calibration_digest
            or legacy.input_manifest_digest != self.path_identity.manifest_digest
            or legacy.session_id != self.path_identity.session_id
            or legacy.stream_id != self.path_identity.stream_id
            or legacy.calibration_digest != self.calibration.calibration_digest
            or legacy.receiver_center_hz != self.calibration.center_hz
        ):
            raise ValueError("trusted legacy/native evidence is not exact same-IQ scope")
        release = self.native_release
        execution = self.native_execution
        if (
            release.pipeline_release != binding.pipeline_release
            or release.source_revision != binding.native_source_revision
            or release.source_tree_digest != binding.native_source_tree_digest
            or release.release_metadata_digest != binding.native_release_manifest_digest
            or execution.pipeline_release != release.pipeline_release
            or execution.source_revision != release.source_revision
            or execution.source_tree_digest != release.source_tree_digest
            or execution.release_manifest_digest != release.release_metadata_digest
            or execution.worker_digest != release.worker_digest
            or execution.interpreter_digest != release.interpreter_digest
            or execution.runtime_package_tree_digest != release.runtime_package_tree_digest
            or execution.template_digest != binding.native_template_digest
            or execution.acquisition_configuration_digest
            != binding.native_acquisition_configuration_digest
            or execution.qam_configuration_digest != binding.native_qam_configuration_digest
            or legacy.oracle_environment_digest != binding.legacy_environment_digest
        ):
            raise ValueError("trusted execution lineage differs from the pinned release")
        if len(self.windows) != 600 or tuple(item.window_index for item in self.windows) != tuple(
            range(600)
        ):
            raise ValueError("trusted receipt requires all 600 canonically ordered windows")
        if legacy.decisions != tuple(item.reference for item in self.windows):
            raise ValueError("trusted legacy decisions differ from replayed windows")
        if execution.decisions != tuple(item.native for item in self.windows):
            raise ValueError("trusted native decisions differ from replayed windows")
        expected = _recovery_summary(self.windows, self.config)
        verified = (
            expected.complete_raw_window_count == 600 and expected.evaluated_pair_count == 600
        )
        eligible = verified and calibration_search_domain_covers(self.calibration, self.config)
        if self.content_complete != verified or self.mathematical_eligible != eligible:
            raise ValueError("content completeness/mathematical eligibility was not replayed")
        if (
            self.complete_raw_window_count != expected.complete_raw_window_count
            or self.evaluated_pair_count != expected.evaluated_pair_count
            or self.missing_or_insufficient_window_count
            != expected.missing_or_insufficient_window_count
            or self.counts != expected.counts
            or self.associated_reference_positive_count
            != expected.associated_reference_positive_count
            or self.recovery != expected.recovery
            or self.reference_qam_positive_count != expected.reference_qam_positive_count
            or self.native_qam_recovery_count != expected.native_qam_recovery_count
            or self.mean_qam_accuracy_difference != expected.mean_qam_accuracy_difference
            or self.qam_accuracy_difference_lower_bound
            != expected.qam_accuracy_difference_lower_bound
            or self.qam_noninferiority_passed != expected.qam_noninferiority_passed
        ):
            raise ValueError("trusted recovery statistics were not independently replayed")
        status, reason = _recomputed_receipt_status(
            preflight_failed=not eligible,
            complete_raw=expected.complete_raw_window_count,
            insufficient=expected.missing_or_insufficient_window_count,
            recovery=expected.recovery,
            reference_qam=expected.reference_qam_positive_count,
            qam_passed=expected.qam_noninferiority_passed,
            config=self.config,
        )
        if self.status is not status or self.reason != reason:
            raise ValueError("trusted recovery status was not independently replayed")
        expected_digest = canonical_digest(self.model_dump(mode="json", exclude={"receipt_digest"}))
        if self.receipt_digest != expected_digest:
            raise ValueError(f"trusted recovery receipt digest does not match: {expected_digest}")
        return self


class TrustedMatchedRecoveryProductV2(ContractModel):
    """Run/scope seal around an inner trusted scientific receipt; no storage fields."""

    schema_version: Literal[2] = 2
    kind: Literal["trusted-matched-pilot-recovery-product"] = (
        "trusted-matched-pilot-recovery-product"
    )
    analysis_run_id: Identifier
    scope_key: Identifier
    pipeline_release: Identifier
    receipt: TrustedMatchedRecoveryReceiptV2
    sealed: Literal[True] = True
    product_digest: Sha256Digest

    @model_validator(mode="after")
    def _seal_is_exact(self) -> Self:
        if (
            self.scope_key != self.receipt.path_identity.stream_id
            or self.pipeline_release != self.receipt.config.detector_binding.pipeline_release
        ):
            raise ValueError("trusted matched product is retargeted across run/scope/release")
        native_values = {
            "schema_version": 2,
            "kind": "native-known-pilot-evidence",
            "analysis_run_id": self.analysis_run_id,
            "scope_key": self.scope_key,
            "release": self.receipt.native_release.model_dump(mode="json"),
            "path_identity": self.receipt.path_identity.model_dump(mode="json"),
            "calibration": self.receipt.calibration.model_dump(mode="json"),
            "execution": self.receipt.native_execution.model_dump(mode="json"),
            "acceptance_eligible": False,
        }
        if canonical_digest(native_values) != self.receipt.native_evidence_product_digest:
            raise ValueError("trusted matched product does not seal the consumed native product")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"product_digest"}))
        if self.product_digest != expected:
            raise ValueError(f"trusted matched product digest does not match: {expected}")
        return self


class TrustedCampaignStreamV2(ContractModel):
    schema_version: Literal[2] = 2
    stratum_id: Identifier
    pairing_group_id: Identifier | None = None
    product: TrustedMatchedRecoveryProductV2


class TrustedMatchedRecoveryCampaignReceiptV2(ContractModel):
    """Exact four-stratum replay over the accepted 30-session/40-stream inventory."""

    schema_version: Literal[2] = 2
    kind: Literal["trusted-matched-pilot-recovery-campaign"] = (
        "trusted-matched-pilot-recovery-campaign"
    )
    config: MatchedPilotAcceptanceCampaignConfigV1
    content_complete: bool
    mathematical_eligible: bool
    acceptance_eligible: Literal[False] = False
    production_accepted: Literal[False] = False
    status: MatchedAcceptanceStatus
    reason: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    expected_stream_count: Literal[40] = 40
    observed_stream_count: Literal[40] = 40
    expected_session_count: Literal[30] = 30
    observed_session_count: Literal[30] = 30
    streams: tuple[TrustedCampaignStreamV2, ...]
    strata: tuple[AcceptanceCampaignStratumResultV1, ...]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    attribution_claimed: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _replay_campaign(self) -> Self:
        ordered = tuple(
            sorted(
                self.streams,
                key=lambda item: (
                    item.stratum_id,
                    item.product.receipt.path_identity.session_id,
                    item.product.scope_key,
                ),
            )
        )
        if self.streams != ordered or len(self.streams) != 40:
            raise ValueError("trusted campaign requires 40 canonically ordered products")
        identities = tuple(
            (
                item.product.receipt.path_identity.session_id,
                item.product.receipt.path_identity.stream_id,
            )
            for item in self.streams
        )
        if (
            len(set(identities)) != 40
            or len({item.product.product_digest for item in self.streams}) != 40
        ):
            raise ValueError("trusted campaign products must be unique")
        if len({item.product.receipt.config.config_digest for item in self.streams}) != 1:
            raise ValueError(
                "trusted campaign contains heterogeneous or mixed-release recovery configurations"
            )
        inventory = {
            (item.session_id, item.stream_id): item for item in self.config.capture_inventory
        }
        if set(identities) != set(inventory):
            raise ValueError("trusted campaign products do not equal accepted capture inventory")
        strata = {item.stratum_id: item for item in self.config.strata}
        pairing: dict[str, list[TrustedCampaignStreamV2]] = {}
        for stream in self.streams:
            receipt = stream.product.receipt
            identity = receipt.path_identity
            accepted = inventory[(identity.session_id, identity.stream_id)]
            declaration = strata.get(stream.stratum_id)
            if declaration is None:
                raise ValueError("trusted campaign stream references an unknown stratum")
            if (
                identity.radio_id != accepted.radio_id
                or identity.radio_serial != accepted.radio_serial
                or identity.receiver_id != accepted.receiver_id
                or identity.physical_receiver_id != accepted.physical_receiver_id
                or identity.hardware_epoch_id != accepted.hardware_epoch_id
                or identity.manifest_digest != accepted.manifest_digest
                or identity.profile_revision_digest != accepted.profile_revision_digest
                or identity.capture_utc_ns != accepted.dwell_start_utc_ns
                or identity.capture_end_utc_ns != accepted.dwell_end_utc_ns
                or stream.pairing_group_id != accepted.pairing_group_id
                or declaration.radio_id != accepted.radio_id
                or declaration.radio_serial != accepted.radio_serial
                or declaration.receiver_id != accepted.receiver_id
                or declaration.physical_receiver_id != accepted.physical_receiver_id
                or declaration.role is not accepted.role
                or receipt.config.detector_binding != self.config.detector_binding
                or stream.product.pipeline_release != self.config.detector_binding.pipeline_release
            ):
                raise ValueError("trusted campaign stream is retargeted or mixed-release")
            if stream.pairing_group_id is not None:
                pairing.setdefault(stream.pairing_group_id, []).append(stream)
        paired_strata = {
            item.stratum_id
            for item in self.config.strata
            if item.role is AcceptanceStreamRole.PAIRED
        }
        if len(pairing) != 10 or any(
            len(group) != 2
            or len({item.product.receipt.path_identity.session_id for item in group}) != 1
            or {item.stratum_id for item in group} != paired_strata
            for group in pairing.values()
        ):
            raise ValueError("trusted campaign pairing is not the accepted 10-session inventory")
        if len({session_id for session_id, _stream_id in identities}) != 30:
            raise ValueError("trusted campaign must contain the accepted 30 sessions")
        complete = all(item.product.receipt.content_complete for item in self.streams)
        eligible = complete and all(
            item.product.receipt.mathematical_eligible for item in self.streams
        )
        if self.content_complete != complete or self.mathematical_eligible != eligible:
            raise ValueError("trusted campaign content/mathematical eligibility was not replayed")
        expected_strata = tuple(
            _aggregate_stratum_v2(
                declaration.stratum_id,
                tuple(item for item in self.streams if item.stratum_id == declaration.stratum_id),
                declaration.required_session_count,
                declaration.minimum_reference_positive_count,
            )
            for declaration in self.config.strata
        )
        if self.strata != expected_strata:
            raise ValueError("trusted campaign strata were not independently replayed")
        status, reason = _campaign_status(expected_strata, eligible)
        if self.status is not status or self.reason != reason:
            raise ValueError("trusted campaign status was not independently replayed")
        expected_digest = canonical_digest(self.model_dump(mode="json", exclude={"receipt_digest"}))
        if self.receipt_digest != expected_digest:
            raise ValueError(f"trusted campaign receipt digest does not match: {expected_digest}")
        return self


class _RecoverySummary(ContractModel):
    complete_raw_window_count: int
    evaluated_pair_count: int
    missing_or_insufficient_window_count: int
    counts: MatchedCandidateCountsV1
    associated_reference_positive_count: int
    recovery: BinomialLowerBoundsV1
    reference_qam_positive_count: int
    native_qam_recovery_count: int
    mean_qam_accuracy_difference: float | None
    qam_accuracy_difference_lower_bound: float | None
    qam_noninferiority_passed: bool | None


def _recovery_summary(
    windows: tuple[TrustedMatchedPilotWindowV2, ...],
    config: MatchedPilotAcceptanceConfigV1,
) -> _RecoverySummary:
    from leo.analysis.starlink.acceptance import (  # noqa: PLC0415
        binomial_lower_bounds,
        paired_student_t_lower_bound,
    )

    evaluated = tuple(
        item
        for item in windows
        if item.reference.status is PilotDecisionStatus.EVALUATED
        and item.native.status is PilotDecisionStatus.EVALUATED
        and item.raw_window_complete
    )
    counts = MatchedCandidateCountsV1(
        n11=sum(
            item.reference.candidate is True and item.native.candidate is True for item in evaluated
        ),
        n10=sum(
            item.reference.candidate is True and item.native.candidate is False
            for item in evaluated
        ),
        n01=sum(
            item.reference.candidate is False and item.native.candidate is True
            for item in evaluated
        ),
        n00=sum(
            item.reference.candidate is False and item.native.candidate is False
            for item in evaluated
        ),
    )
    associated = sum(
        item.reference.candidate is True and item.candidate_associated for item in evaluated
    )
    recovery = binomial_lower_bounds(
        associated, counts.n11 + counts.n10, alpha=config.confidence_alpha
    )
    reference_qam = sum(item.reference_qam_positive for item in evaluated)
    native_qam = sum(
        item.reference_qam_positive
        and item.candidate_associated
        and item.native_qam_positive
        and item.qam_accuracy_difference is not None
        and item.qam_accuracy_difference >= -config.qam_accuracy_noninferiority_margin
        for item in evaluated
    )
    differences = tuple(
        item.qam_accuracy_difference
        for item in evaluated
        if item.reference_qam_positive
        and item.candidate_associated
        and item.native_qam_positive
        and item.qam_accuracy_difference is not None
    )
    mean = sum(differences) / len(differences) if differences else None
    lower = paired_student_t_lower_bound(differences, alpha=config.qam_confidence_alpha)
    qam_passed = (
        None
        if reference_qam < 2 or lower is None
        else native_qam == reference_qam and lower >= -config.qam_accuracy_noninferiority_margin
    )
    return _RecoverySummary(
        complete_raw_window_count=sum(item.raw_window_complete for item in windows),
        evaluated_pair_count=len(evaluated),
        missing_or_insufficient_window_count=600 - len(evaluated),
        counts=counts,
        associated_reference_positive_count=associated,
        recovery=recovery,
        reference_qam_positive_count=reference_qam,
        native_qam_recovery_count=native_qam,
        mean_qam_accuracy_difference=mean,
        qam_accuracy_difference_lower_bound=lower,
        qam_noninferiority_passed=qam_passed,
    )


def _aggregate_stratum_v2(
    stratum_id: str,
    streams: tuple[TrustedCampaignStreamV2, ...],
    required_sessions: int,
    minimum_positives: int,
) -> AcceptanceCampaignStratumResultV1:
    from leo.analysis.starlink.acceptance import (  # noqa: PLC0415
        binomial_lower_bounds,
        paired_student_t_lower_bound,
    )

    receipts = tuple(item.product.receipt for item in streams)
    reference_positive = sum(item.recovery.trials for item in receipts)
    associated = sum(item.associated_reference_positive_count for item in receipts)
    recovery = binomial_lower_bounds(associated, reference_positive, alpha=0.05)
    qam_windows = tuple(
        window
        for receipt in receipts
        for window in receipt.windows
        if window.reference_qam_positive
    )
    differences = tuple(
        item.qam_accuracy_difference
        for item in qam_windows
        if item.qam_accuracy_difference is not None
    )
    mean = sum(differences) / len(differences) if differences else None
    lower = paired_student_t_lower_bound(differences, alpha=0.05)
    incomplete = any(not item.mathematical_eligible for item in receipts)
    if len(streams) != required_sessions or reference_positive < minimum_positives or incomplete:
        status = MatchedAcceptanceStatus.INCONCLUSIVE
        reason = "stratum requires 10 complete trusted sessions and at least 30 reference positives"
        qam_passed = None
    elif len(differences) < 2:
        status = MatchedAcceptanceStatus.INCONCLUSIVE
        reason = "stratum requires at least two trusted paired QAM-positive differences"
        qam_passed = None
    else:
        config = receipts[0].config
        native_qam = sum(item.native_qam_recovery_count for item in receipts)
        reference_qam = len(qam_windows)
        qam_passed = bool(
            reference_qam >= config.minimum_reference_qam_positive_count
            and native_qam == reference_qam
            and lower is not None
            and lower >= -config.qam_accuracy_noninferiority_margin
        )
        recovery_passed = bool(
            recovery.point_estimate is not None
            and recovery.point_estimate >= config.minimum_recovery_fraction
            and recovery.wilson_one_sided_lower is not None
            and recovery.wilson_one_sided_lower >= config.minimum_wilson_lower_bound
            and recovery.clopper_pearson_one_sided_lower is not None
            and recovery.clopper_pearson_one_sided_lower >= config.minimum_exact_lower_bound
        )
        status = (
            MatchedAcceptanceStatus.PASS
            if recovery_passed and qam_passed
            else MatchedAcceptanceStatus.FAIL
        )
        reason = "aggregate trusted candidate-recovery and paired-QAM gates evaluated"
    return AcceptanceCampaignStratumResultV1(
        stratum_id=stratum_id,
        observed_session_count=len(streams),
        reference_positive_count=reference_positive,
        associated_reference_positive_count=associated,
        recovery=recovery,
        reference_qam_positive_count=len(qam_windows),
        mean_qam_accuracy_difference=mean,
        qam_accuracy_difference_lower_bound=lower,
        qam_interval_method="paired-student-t-one-sided-95",
        qam_noninferiority_passed=qam_passed,
        status=status,
        reason=reason,
    )


def _campaign_status(
    strata: tuple[AcceptanceCampaignStratumResultV1, ...], eligible: bool
) -> tuple[MatchedAcceptanceStatus, str]:
    if not eligible or any(item.status is MatchedAcceptanceStatus.INCONCLUSIVE for item in strata):
        return (
            MatchedAcceptanceStatus.INCONCLUSIVE,
            "campaign lacks complete trusted evidence or a predeclared stratum gate denominator",
        )
    if any(item.status is MatchedAcceptanceStatus.FAIL for item in strata):
        return (
            MatchedAcceptanceStatus.FAIL,
            "one or more predeclared trusted campaign strata failed a frozen gate",
        )
    return (
        MatchedAcceptanceStatus.PASS,
        "all predeclared trusted campaign strata passed the frozen aggregate gates",
    )


def _qam_positive(decision: PilotWindowDecisionV1) -> bool:
    return bool(
        decision.candidate is True
        and decision.qam_accuracy is not None
        and decision.qam_evm is not None
        and decision.qam_accuracy >= 0.60
        and decision.qam_evm <= 1.25
    )
