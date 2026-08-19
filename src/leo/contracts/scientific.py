"""Versioned scientific qualification artifacts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.calibration import ReceiverPathIdentityV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier


class PilotDecisionStatus(StrEnum):
    EVALUATED = "evaluated"
    INSUFFICIENT = "insufficient"


class MatchedAcceptanceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    INSUFFICIENT = "insufficient"


class AcceptanceStreamRole(StrEnum):
    INDEPENDENT = "independent"
    PAIRED = "paired"


class MatchedPilotAcceptanceConfigV1(ContractModel):
    """Frozen geometry and candidate-recovery gates for one 60-second stream."""

    schema_version: Literal[1] = 1
    config_digest: Sha256Digest
    sample_rate_hz: Literal[2_500_000] = 2_500_000
    dwell_sample_count: Literal[150_000_000] = 150_000_000
    window_sample_count: Literal[25_000] = 25_000
    interval_sample_count: Literal[250_000] = 250_000
    scheduled_window_count: Literal[600] = 600
    block_sample_count: Annotated[int, Field(ge=25_000, le=1_048_576)] = 262_144
    epoch_tolerance_samples: Literal[8] = 8
    cfo_tolerance_hz: float = 500.0
    minimum_reference_positive_count: Literal[30] = 30
    minimum_recovery_fraction: float = 0.90
    minimum_wilson_lower_bound: float = 0.80
    minimum_exact_lower_bound: float = 0.80
    confidence_alpha: float = 0.05
    minimum_qam_accuracy: float = 0.60
    maximum_qam_evm: float = 1.25
    qam_accuracy_noninferiority_margin: float = 0.05
    minimum_reference_qam_positive_count: Literal[1] = 1
    minimum_native_candidate_margin: float = 0.05
    qam_interval_method: Literal["paired-student-t-one-sided-95"] = "paired-student-t-one-sided-95"
    qam_confidence_alpha: float = 0.05

    @field_validator(
        "cfo_tolerance_hz",
        "minimum_recovery_fraction",
        "minimum_wilson_lower_bound",
        "minimum_exact_lower_bound",
        "confidence_alpha",
        "minimum_qam_accuracy",
        "maximum_qam_evm",
        "qam_accuracy_noninferiority_margin",
        "minimum_native_candidate_margin",
        "qam_confidence_alpha",
    )
    @classmethod
    def _floats_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("acceptance thresholds must be finite")
        return value

    @model_validator(mode="after")
    def _geometry_and_digest_are_exact(self) -> Self:
        frozen = (
            self.cfo_tolerance_hz,
            self.minimum_recovery_fraction,
            self.minimum_wilson_lower_bound,
            self.minimum_exact_lower_bound,
            self.confidence_alpha,
            self.minimum_qam_accuracy,
            self.maximum_qam_evm,
            self.qam_accuracy_noninferiority_margin,
            self.minimum_native_candidate_margin,
            self.qam_confidence_alpha,
        )
        if frozen != (500.0, 0.90, 0.80, 0.80, 0.05, 0.60, 1.25, 0.05, 0.05, 0.05):
            raise ValueError("published v1 acceptance thresholds are immutable")
        expected_windows = (
            self.dwell_sample_count - self.window_sample_count
        ) // self.interval_sample_count + 1
        if expected_windows != self.scheduled_window_count:
            raise ValueError("acceptance schedule does not produce exactly 600 windows")
        expected = matched_pilot_acceptance_config_digest(self)
        if self.config_digest != expected:
            raise ValueError(f"acceptance config digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        block_sample_count: int = 262_144,
    ) -> MatchedPilotAcceptanceConfigV1:
        values: dict[str, object] = {
            "schema_version": 1,
            "sample_rate_hz": 2_500_000,
            "dwell_sample_count": 150_000_000,
            "window_sample_count": 25_000,
            "interval_sample_count": 250_000,
            "scheduled_window_count": 600,
            "block_sample_count": block_sample_count,
            "epoch_tolerance_samples": 8,
            "cfo_tolerance_hz": 500.0,
            "minimum_reference_positive_count": 30,
            "minimum_recovery_fraction": 0.90,
            "minimum_wilson_lower_bound": 0.80,
            "minimum_exact_lower_bound": 0.80,
            "confidence_alpha": 0.05,
            "minimum_qam_accuracy": 0.60,
            "maximum_qam_evm": 1.25,
            "qam_accuracy_noninferiority_margin": 0.05,
            "minimum_reference_qam_positive_count": 1,
            "minimum_native_candidate_margin": 0.05,
            "qam_interval_method": "paired-student-t-one-sided-95",
            "qam_confidence_alpha": 0.05,
        }
        return cls(
            config_digest=canonical_digest(values),
            block_sample_count=block_sample_count,
        )


class PilotWindowDecisionV1(ContractModel):
    schema_version: Literal[1] = 1
    source: Literal["legacy_reference", "native"]
    algorithm_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    algorithm_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    evidence_digest: Sha256Digest
    window_iq_digest: Sha256Digest | None
    window_index: Annotated[int, Field(ge=0, lt=600)]
    sample_start: Annotated[int, Field(ge=0)]
    status: PilotDecisionStatus
    candidate: bool | None
    epoch_sample: Annotated[int | None, Field(ge=0, lt=25_000)] = None
    cfo_hz: float | None = None
    qam_accuracy: Annotated[float | None, Field(ge=0, le=1)] = None
    qam_evm: Annotated[float | None, Field(gt=0)] = None
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @field_validator("cfo_hz", "qam_accuracy", "qam_evm")
    @classmethod
    def _optional_floats_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("decision metrics must be finite")
        return value

    @model_validator(mode="after")
    def _decision_fields_are_consistent(self) -> Self:
        if self.sample_start != self.window_index * 250_000:
            raise ValueError("decision sample_start disagrees with fixed v1 schedule")
        expected = pilot_window_decision_digest(self)
        if self.evidence_digest != expected:
            raise ValueError(f"decision evidence digest does not match content: {expected}")
        if self.status is PilotDecisionStatus.INSUFFICIENT:
            if (
                self.window_iq_digest is not None
                or self.candidate is not None
                or any(
                    value is not None
                    for value in (self.epoch_sample, self.cfo_hz, self.qam_accuracy, self.qam_evm)
                )
            ):
                raise ValueError("insufficient decision cannot contain a candidate or metrics")
            return self
        if self.candidate is None:
            raise ValueError("evaluated decision requires a candidate boolean")
        if self.window_iq_digest is None:
            raise ValueError("evaluated decision requires its normalized IQ digest")
        if self.candidate and (self.epoch_sample is None or self.cfo_hz is None):
            raise ValueError("candidate decision requires epoch and CFO")
        if not self.candidate and any(
            value is not None
            for value in (self.epoch_sample, self.cfo_hz, self.qam_accuracy, self.qam_evm)
        ):
            raise ValueError("negative decision cannot contain candidate metrics")
        if (self.qam_accuracy is None) != (self.qam_evm is None):
            raise ValueError("QAM accuracy and EVM must appear together")
        return self

    @classmethod
    def create(
        cls,
        *,
        source: Literal["legacy_reference", "native"],
        algorithm_id: str,
        algorithm_version: str,
        window_iq_digest: str | None,
        window_index: int,
        sample_start: int,
        status: PilotDecisionStatus,
        candidate: bool | None,
        reason: str,
        epoch_sample: int | None = None,
        cfo_hz: float | None = None,
        qam_accuracy: float | None = None,
        qam_evm: float | None = None,
    ) -> PilotWindowDecisionV1:
        values = {
            "schema_version": 1,
            "source": source,
            "algorithm_id": algorithm_id,
            "algorithm_version": algorithm_version,
            "window_iq_digest": window_iq_digest,
            "window_index": window_index,
            "sample_start": sample_start,
            "status": status.value,
            "candidate": candidate,
            "epoch_sample": epoch_sample,
            "cfo_hz": cfo_hz,
            "qam_accuracy": qam_accuracy,
            "qam_evm": qam_evm,
            "reason": reason,
            "candidate_only": True,
            "specificity_claimed": False,
            "payload_decoded": False,
        }
        return cls(
            source=source,
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            evidence_digest=canonical_digest(values),
            window_iq_digest=window_iq_digest,
            window_index=window_index,
            sample_start=sample_start,
            status=status,
            candidate=candidate,
            epoch_sample=epoch_sample,
            cfo_hz=cfo_hz,
            qam_accuracy=qam_accuracy,
            qam_evm=qam_evm,
            reason=reason,
        )


class MatchedPilotWindowV1(ContractModel):
    schema_version: Literal[1] = 1
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
    def _window_identity_is_consistent(self) -> Self:
        if self.sample_start != self.window_index * 250_000:
            raise ValueError("matched window sample_start disagrees with fixed v1 schedule")
        for decision in (self.reference, self.native):
            if (
                decision.window_index != self.window_index
                or decision.sample_start != self.sample_start
            ):
                raise ValueError("decision identity disagrees with matched window")
        if (
            self.reference.window_iq_digest is not None
            and self.reference.window_iq_digest != self.native.window_iq_digest
        ):
            raise ValueError("matched decisions must bind to the same normalized IQ window")
        if self.candidate_associated and (
            self.circular_epoch_error_samples is None or self.absolute_cfo_error_hz is None
        ):
            raise ValueError("associated candidate requires epoch and CFO errors")
        if self.qam_accuracy_difference is not None and not math.isfinite(
            self.qam_accuracy_difference
        ):
            raise ValueError("QAM accuracy difference must be finite")
        return self


class MatchedCandidateCountsV1(ContractModel):
    schema_version: Literal[1] = 1
    n11: Annotated[int, Field(ge=0)]
    n10: Annotated[int, Field(ge=0)]
    n01: Annotated[int, Field(ge=0)]
    n00: Annotated[int, Field(ge=0)]

    @property
    def total(self) -> int:
        return self.n11 + self.n10 + self.n01 + self.n00


class BinomialLowerBoundsV1(ContractModel):
    schema_version: Literal[1] = 1
    successes: Annotated[int, Field(ge=0)]
    trials: Annotated[int, Field(ge=0)]
    point_estimate: Annotated[float | None, Field(ge=0, le=1)]
    confidence_level: Annotated[float, Field(gt=0.5, lt=1)]
    wilson_one_sided_lower: Annotated[float | None, Field(ge=0, le=1)]
    clopper_pearson_one_sided_lower: Annotated[float | None, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def _counts_and_optional_values_agree(self) -> Self:
        if self.successes > self.trials:
            raise ValueError("binomial successes exceed trials")
        values = (
            self.point_estimate,
            self.wilson_one_sided_lower,
            self.clopper_pearson_one_sided_lower,
        )
        if self.trials == 0 and any(value is not None for value in values):
            raise ValueError("zero-trial bounds must be null")
        if self.trials > 0 and any(value is None for value in values):
            raise ValueError("nonzero-trial bounds must be present")
        return self


class MatchedPilotAcceptanceReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    artifact_id: Identifier
    config: MatchedPilotAcceptanceConfigV1
    input_manifest_digest: Sha256Digest
    path_identity: ReceiverPathIdentityV1
    calibration_id: Identifier | None
    calibration_digest: Sha256Digest | None
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
    maximum_working_set_bytes: Annotated[int, Field(ge=0)]
    windows: tuple[MatchedPilotWindowV1, ...]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    attribution_claimed: Literal[False] = False

    @model_validator(mode="after")
    def _receipt_accounting_is_exact(self) -> Self:
        if len(self.windows) != self.scheduled_window_count:
            raise ValueError("receipt must retain all 600 scheduled window records")
        if tuple(item.window_index for item in self.windows) != tuple(range(600)):
            raise ValueError("receipt windows must be complete and canonically ordered")
        if self.evaluated_pair_count + self.missing_or_insufficient_window_count != 600:
            raise ValueError("evaluated and insufficient counts must cover the denominator")
        if self.counts.total != self.evaluated_pair_count:
            raise ValueError("matched candidate counts must equal evaluated pairs")
        if self.recovery.trials != self.counts.n11 + self.counts.n10:
            raise ValueError("recovery denominator must be reference-positive windows")
        if self.recovery.successes != self.associated_reference_positive_count:
            raise ValueError("recovery successes must count associated reference positives")
        if (self.calibration_id is None) != (self.calibration_digest is None):
            raise ValueError("calibration ID and digest must appear together")
        if self.mean_qam_accuracy_difference is not None and not math.isfinite(
            self.mean_qam_accuracy_difference
        ):
            raise ValueError("mean QAM accuracy difference must be finite")
        if self.qam_accuracy_difference_lower_bound is not None and not math.isfinite(
            self.qam_accuracy_difference_lower_bound
        ):
            raise ValueError("QAM accuracy lower bound must be finite")
        return self


class AcceptanceCampaignStratumV1(ContractModel):
    schema_version: Literal[1] = 1
    stratum_id: Identifier
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    role: AcceptanceStreamRole
    required_session_count: Literal[10] = 10
    minimum_reference_positive_count: Literal[30] = 30


class MatchedPilotAcceptanceCampaignConfigV1(ContractModel):
    """Predeclared two-radio, 30-session acceptance campaign."""

    schema_version: Literal[1] = 1
    campaign_id: Identifier
    capture_campaign_receipt_digest: Sha256Digest
    config_digest: Sha256Digest
    paired_session_count: Literal[10] = 10
    strata: tuple[AcceptanceCampaignStratumV1, ...]

    @model_validator(mode="after")
    def _inventory_and_digest_are_exact(self) -> Self:
        if len(self.strata) != 4:
            raise ValueError("campaign requires two independent and two paired strata")
        if len({item.stratum_id for item in self.strata}) != 4:
            raise ValueError("campaign stratum IDs must be unique")
        identities = {
            (item.radio_id, item.radio_serial, item.receiver_id, item.physical_receiver_id)
            for item in self.strata
        }
        if len(identities) != 2:
            raise ValueError("campaign requires exactly two physical radio paths")
        for identity in identities:
            roles = {
                item.role
                for item in self.strata
                if (
                    item.radio_id,
                    item.radio_serial,
                    item.receiver_id,
                    item.physical_receiver_id,
                )
                == identity
            }
            if roles != {AcceptanceStreamRole.INDEPENDENT, AcceptanceStreamRole.PAIRED}:
                raise ValueError("each campaign radio path requires both roles")
        expected = matched_pilot_campaign_config_digest(self)
        if self.config_digest != expected:
            raise ValueError(f"campaign config digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        campaign_id: str,
        capture_campaign_receipt_digest: str,
        strata: tuple[AcceptanceCampaignStratumV1, ...],
    ) -> MatchedPilotAcceptanceCampaignConfigV1:
        ordered = tuple(sorted(strata, key=lambda item: item.stratum_id))
        values = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "capture_campaign_receipt_digest": capture_campaign_receipt_digest,
            "paired_session_count": 10,
            "strata": tuple(item.model_dump(mode="json") for item in ordered),
        }
        return cls(
            campaign_id=campaign_id,
            capture_campaign_receipt_digest=capture_campaign_receipt_digest,
            config_digest=canonical_digest(values),
            strata=ordered,
        )


class AcceptanceCampaignStreamV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    stream_id: Identifier
    stratum_id: Identifier
    pairing_group_id: Identifier | None = None
    receipt: MatchedPilotAcceptanceReceiptV1

    @model_validator(mode="after")
    def _pairing_matches_role_later(self) -> Self:
        if not self.session_id or not self.stream_id:
            raise ValueError("campaign stream identity is required")
        return self


class AcceptanceCampaignStratumResultV1(ContractModel):
    schema_version: Literal[1] = 1
    stratum_id: Identifier
    observed_session_count: Annotated[int, Field(ge=0, le=10)]
    reference_positive_count: Annotated[int, Field(ge=0)]
    associated_reference_positive_count: Annotated[int, Field(ge=0)]
    recovery: BinomialLowerBoundsV1
    reference_qam_positive_count: Annotated[int, Field(ge=0)]
    mean_qam_accuracy_difference: float | None
    qam_accuracy_difference_lower_bound: float | None
    qam_interval_method: Literal["paired-student-t-one-sided-95"]
    qam_noninferiority_passed: bool | None
    status: MatchedAcceptanceStatus
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class MatchedPilotAcceptanceCampaignReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    artifact_id: Identifier
    config: MatchedPilotAcceptanceCampaignConfigV1
    status: MatchedAcceptanceStatus
    reason: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    expected_stream_count: Literal[40] = 40
    observed_stream_count: Annotated[int, Field(ge=0, le=40)]
    expected_independent_session_count: Literal[20] = 20
    expected_paired_session_count: Literal[10] = 10
    observed_paired_session_count: Annotated[int, Field(ge=0, le=10)]
    streams: tuple[AcceptanceCampaignStreamV1, ...]
    strata: tuple[AcceptanceCampaignStratumResultV1, ...]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    attribution_claimed: Literal[False] = False

    @model_validator(mode="after")
    def _campaign_accounting_is_exact(self) -> Self:
        if self.observed_stream_count != len(self.streams):
            raise ValueError("observed stream count disagrees with inventory")
        if len({(item.session_id, item.stream_id) for item in self.streams}) != len(self.streams):
            raise ValueError("campaign stream identities must be unique")
        expected_strata = tuple(item.stratum_id for item in self.config.strata)
        if tuple(item.stratum_id for item in self.strata) != expected_strata:
            raise ValueError("campaign results must follow the predeclared strata")
        return self


def matched_pilot_acceptance_config_digest(value: MatchedPilotAcceptanceConfigV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"config_digest"}))


def matched_pilot_campaign_config_digest(
    value: MatchedPilotAcceptanceCampaignConfigV1,
) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"config_digest"}))


def pilot_window_decision_digest(value: PilotWindowDecisionV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"evidence_digest"}))
