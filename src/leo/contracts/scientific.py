"""Versioned scientific qualification artifacts."""

from __future__ import annotations

import math
import posixpath
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier

_LEGACY_REVISION: Literal["0bb80d14759fd8496b74e7d3219a690be18565a6"] = (
    "0bb80d14759fd8496b74e7d3219a690be18565a6"
)
_LEGACY_SOURCE_TREE: Literal["631bc74222f1d03dad99f418ee21e75d94dbb27d"] = (
    "631bc74222f1d03dad99f418ee21e75d94dbb27d"
)
_LEGACY_EXECUTABLE_DIGEST: Literal[
    "sha256:b2c0542f431118dc7f1ebc625e375cd1d91f48fd99db43f0a889f7c061da503a"
] = "sha256:b2c0542f431118dc7f1ebc625e375cd1d91f48fd99db43f0a889f7c061da503a"
_LEGACY_ENVIRONMENT_DIGEST: Literal[
    "sha256:dde115d44ca682b61d9f468757ee3a9ee9596705dbc1ecea7b78a3cb8b810b56"
] = "sha256:dde115d44ca682b61d9f468757ee3a9ee9596705dbc1ecea7b78a3cb8b810b56"
_LEGACY_WORKER_DIGEST: Literal[
    "sha256:07162739e640b824421a3640ccd53001cdaee876cd429203496b8e1f6b209e77"
] = "sha256:07162739e640b824421a3640ccd53001cdaee876cd429203496b8e1f6b209e77"


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


class DetectorPipelineBindingV1(ContractModel):
    """Pinned scientific and production revisions shared by every campaign stream."""

    schema_version: Literal[1] = 1
    legacy_source_revision: Literal["0bb80d14759fd8496b74e7d3219a690be18565a6"]
    legacy_source_tree: Literal["631bc74222f1d03dad99f418ee21e75d94dbb27d"]
    legacy_executable_tree_digest: Literal[
        "sha256:b2c0542f431118dc7f1ebc625e375cd1d91f48fd99db43f0a889f7c061da503a"
    ]
    legacy_environment_digest: Literal[
        "sha256:dde115d44ca682b61d9f468757ee3a9ee9596705dbc1ecea7b78a3cb8b810b56"
    ]
    legacy_worker_digest: Literal[
        "sha256:07162739e640b824421a3640ccd53001cdaee876cd429203496b8e1f6b209e77"
    ]
    native_source_revision: Annotated[str, StringConstraints(min_length=7, max_length=128)]
    native_source_tree_digest: Sha256Digest
    native_release_manifest_digest: Sha256Digest
    native_template_digest: Sha256Digest
    native_acquisition_configuration_digest: Sha256Digest
    native_qam_configuration_digest: Sha256Digest
    calibration_uncertainty_policy: Literal[
        "receiver-prior-plus-300khz-doppler-and-pilot-occupied-band-v1"
    ] = "receiver-prior-plus-300khz-doppler-and-pilot-occupied-band-v1"
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    binding_digest: Sha256Digest

    @model_validator(mode="after")
    def _digest_is_exact(self) -> Self:
        expected = detector_pipeline_binding_digest(self)
        if self.binding_digest != expected:
            raise ValueError(f"detector binding digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        native_source_revision: str,
        native_source_tree_digest: str,
        native_release_manifest_digest: str,
        native_template_digest: str,
        native_acquisition_configuration_digest: str,
        native_qam_configuration_digest: str,
        pipeline_release: str,
    ) -> DetectorPipelineBindingV1:
        document = {
            "schema_version": 1,
            "legacy_source_revision": _LEGACY_REVISION,
            "legacy_source_tree": _LEGACY_SOURCE_TREE,
            "legacy_executable_tree_digest": _LEGACY_EXECUTABLE_DIGEST,
            "legacy_environment_digest": _LEGACY_ENVIRONMENT_DIGEST,
            "legacy_worker_digest": _LEGACY_WORKER_DIGEST,
            "native_source_revision": native_source_revision,
            "native_source_tree_digest": native_source_tree_digest,
            "native_release_manifest_digest": native_release_manifest_digest,
            "native_template_digest": native_template_digest,
            "native_acquisition_configuration_digest": native_acquisition_configuration_digest,
            "native_qam_configuration_digest": native_qam_configuration_digest,
            "pipeline_release": pipeline_release,
        }
        document["calibration_uncertainty_policy"] = (
            "receiver-prior-plus-300khz-doppler-and-pilot-occupied-band-v1"
        )
        return cls(
            legacy_source_revision=_LEGACY_REVISION,
            legacy_source_tree=_LEGACY_SOURCE_TREE,
            legacy_executable_tree_digest=_LEGACY_EXECUTABLE_DIGEST,
            legacy_environment_digest=_LEGACY_ENVIRONMENT_DIGEST,
            legacy_worker_digest=_LEGACY_WORKER_DIGEST,
            native_source_revision=native_source_revision,
            native_source_tree_digest=native_source_tree_digest,
            native_release_manifest_digest=native_release_manifest_digest,
            native_template_digest=native_template_digest,
            native_acquisition_configuration_digest=native_acquisition_configuration_digest,
            native_qam_configuration_digest=native_qam_configuration_digest,
            pipeline_release=pipeline_release,
            binding_digest=canonical_digest(document),
        )


class MatchedPilotAcceptanceConfigV1(ContractModel):
    """Frozen geometry and candidate-recovery gates for one 60-second stream."""

    schema_version: Literal[1] = 1
    config_digest: Sha256Digest
    detector_binding: DetectorPipelineBindingV1
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
    expected_doppler_guard_hz: float = 300_000.0
    residual_search_lower_hz: float = -400_000.0
    residual_search_upper_hz: float = 400_000.0
    sampled_band_edge_guard_hz: float = 0.0
    occupied_pilot_half_span_hz: float = 937_500.0

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
        "expected_doppler_guard_hz",
        "residual_search_lower_hz",
        "residual_search_upper_hz",
        "sampled_band_edge_guard_hz",
        "occupied_pilot_half_span_hz",
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
            self.expected_doppler_guard_hz,
            self.residual_search_lower_hz,
            self.residual_search_upper_hz,
            self.sampled_band_edge_guard_hz,
            self.occupied_pilot_half_span_hz,
        )
        if frozen != (
            500.0,
            0.90,
            0.80,
            0.80,
            0.05,
            0.60,
            1.25,
            0.05,
            0.05,
            0.05,
            300_000.0,
            -400_000.0,
            400_000.0,
            0.0,
            937_500.0,
        ):
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
        detector_binding: DetectorPipelineBindingV1,
        block_sample_count: int = 262_144,
    ) -> MatchedPilotAcceptanceConfigV1:
        values: dict[str, object] = {
            "schema_version": 1,
            "detector_binding": detector_binding.model_dump(mode="json"),
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
            "expected_doppler_guard_hz": 300_000.0,
            "residual_search_lower_hz": -400_000.0,
            "residual_search_upper_hz": 400_000.0,
            "sampled_band_edge_guard_hz": 0.0,
            "occupied_pilot_half_span_hz": 937_500.0,
        }
        return cls(
            config_digest=canonical_digest(values),
            detector_binding=detector_binding,
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


class NativeExecutionReceiptV1(ContractModel):
    """Sealed native execution evidence; no current production composer emits this yet."""

    schema_version: Literal[1] = 1
    kind: Literal["sealed-native-known-pilot-execution"] = "sealed-native-known-pilot-execution"
    status: Literal["complete"] = "complete"
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    source_revision: Annotated[str, StringConstraints(min_length=7, max_length=128)]
    source_tree_digest: Sha256Digest
    release_manifest_digest: Sha256Digest
    template_digest: Sha256Digest
    acquisition_configuration_digest: Sha256Digest
    qam_configuration_digest: Sha256Digest
    input_manifest_digest: Sha256Digest
    session_id: Identifier
    stream_id: Identifier
    calibration_digest: Sha256Digest
    decisions: tuple[PilotWindowDecisionV1, ...]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_digest_is_exact(self) -> Self:
        if len(self.decisions) != 600 or tuple(
            decision.window_index for decision in self.decisions
        ) != tuple(range(600)):
            raise ValueError("sealed native execution must contain all 600 ordered decisions")
        if any(
            decision.source != "native"
            or (
                decision.algorithm_id,
                decision.algorithm_version,
            )
            not in {
                ("native-symbolwise-known-pilot", "1.0.0"),
                ("unavailable-window-decision", "1.0.0"),
            }
            for decision in self.decisions
        ):
            raise ValueError("sealed native execution contains an unfrozen decision implementation")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"receipt_digest"}))
        if self.receipt_digest != expected:
            raise ValueError(f"native execution receipt digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        pipeline_release: str,
        source_revision: str,
        source_tree_digest: str,
        release_manifest_digest: str,
        template_digest: str,
        acquisition_configuration_digest: str,
        qam_configuration_digest: str,
        input_manifest_digest: str,
        session_id: str,
        stream_id: str,
        calibration_digest: str,
        decisions: tuple[PilotWindowDecisionV1, ...],
    ) -> NativeExecutionReceiptV1:
        values = {
            "schema_version": 1,
            "kind": "sealed-native-known-pilot-execution",
            "status": "complete",
            "pipeline_release": pipeline_release,
            "source_revision": source_revision,
            "source_tree_digest": source_tree_digest,
            "release_manifest_digest": release_manifest_digest,
            "template_digest": template_digest,
            "acquisition_configuration_digest": acquisition_configuration_digest,
            "qam_configuration_digest": qam_configuration_digest,
            "input_manifest_digest": input_manifest_digest,
            "session_id": session_id,
            "stream_id": stream_id,
            "calibration_digest": calibration_digest,
            "decisions": tuple(item.model_dump(mode="json") for item in decisions),
        }
        return cls(
            pipeline_release=pipeline_release,
            source_revision=source_revision,
            source_tree_digest=source_tree_digest,
            release_manifest_digest=release_manifest_digest,
            template_digest=template_digest,
            acquisition_configuration_digest=acquisition_configuration_digest,
            qam_configuration_digest=qam_configuration_digest,
            input_manifest_digest=input_manifest_digest,
            session_id=session_id,
            stream_id=stream_id,
            calibration_digest=calibration_digest,
            decisions=decisions,
            receipt_digest=canonical_digest(values),
        )


class TrustedNativeReleaseEvidenceV1(ContractModel):
    """Evidence emitted only after validating the selected published release."""

    schema_version: Literal[1] = 1
    kind: Literal["validated-current-native-release"] = "validated-current-native-release"
    pipeline_release: Identifier
    source_revision: Annotated[
        str, StringConstraints(pattern=r"^[0-9a-f]{40}$", min_length=40, max_length=40)
    ]
    git_tree: Annotated[
        str, StringConstraints(pattern=r"^[0-9a-f]{40}$", min_length=40, max_length=40)
    ]
    source_tree_digest: Sha256Digest
    release_metadata_digest: Sha256Digest
    release_path: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    validator: Literal["deployed-release-validators-v1"] = "deployed-release-validators-v1"
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def _release_evidence_digest_is_exact(self) -> Self:
        if not self.release_path.startswith("/") or self.release_path.startswith("/mnt/qnap01/"):
            raise ValueError("validated native release path is unsafe")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"evidence_digest"}))
        if self.evidence_digest != expected:
            raise ValueError(f"native release evidence digest does not match content: {expected}")
        return self


class NativeKnownPilotEvidenceProductV1(ContractModel):
    """Evidence-only native execution product; never grants scientific acceptance."""

    schema_version: Literal[1] = 1
    kind: Literal["native-known-pilot-evidence"] = "native-known-pilot-evidence"
    analysis_run_id: Identifier
    scope_key: Identifier
    release: TrustedNativeReleaseEvidenceV1
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1
    execution: NativeExecutionReceiptV1
    acceptance_eligible: Literal[False] = False
    product_digest: Sha256Digest

    @model_validator(mode="after")
    def _product_is_exactly_bound(self) -> Self:
        if (
            not self.calibration.matches(self.path_identity)
            or self.execution.pipeline_release != self.release.pipeline_release
            or self.execution.source_revision != self.release.source_revision
            or self.execution.source_tree_digest != self.release.source_tree_digest
            or self.execution.release_manifest_digest != self.release.release_metadata_digest
            or self.execution.input_manifest_digest != self.path_identity.manifest_digest
            or self.execution.session_id != self.path_identity.session_id
            or self.execution.stream_id != self.path_identity.stream_id
            or self.execution.calibration_digest != self.calibration.calibration_digest
        ):
            raise ValueError("native evidence product lineage is inconsistent")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"product_digest"}))
        if self.product_digest != expected:
            raise ValueError(f"native evidence product digest does not match content: {expected}")
        return self


class NativeExecutionReceiptV2(ContractModel):
    """Release-worker execution evidence with environment and output seals."""

    schema_version: Literal[2] = 2
    kind: Literal["sealed-native-known-pilot-execution"] = "sealed-native-known-pilot-execution"
    status: Literal["complete"] = "complete"
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    source_revision: Annotated[str, StringConstraints(min_length=7, max_length=128)]
    source_tree_digest: Sha256Digest
    release_manifest_digest: Sha256Digest
    template_digest: Sha256Digest
    acquisition_configuration_digest: Sha256Digest
    qam_configuration_digest: Sha256Digest
    worker_digest: Sha256Digest
    interpreter_digest: Sha256Digest
    runtime_package_tree_digest: Sha256Digest
    execution_environment_digest: Sha256Digest
    worker_output_digest: Sha256Digest
    input_manifest_digest: Sha256Digest
    session_id: Identifier
    stream_id: Identifier
    calibration_digest: Sha256Digest
    decisions: tuple[PilotWindowDecisionV1, ...]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_digest_is_exact(self) -> Self:
        if len(self.decisions) != 600 or tuple(
            decision.window_index for decision in self.decisions
        ) != tuple(range(600)):
            raise ValueError("sealed native execution must contain all 600 ordered decisions")
        if any(
            decision.source != "native"
            or (
                decision.algorithm_id,
                decision.algorithm_version,
            )
            not in {
                ("native-symbolwise-known-pilot", "1.0.0"),
                ("unavailable-window-decision", "1.0.0"),
            }
            for decision in self.decisions
        ):
            raise ValueError("sealed native execution contains an unfrozen implementation")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"receipt_digest"}))
        if self.receipt_digest != expected:
            raise ValueError(f"native execution receipt digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        pipeline_release: str,
        source_revision: str,
        source_tree_digest: str,
        release_manifest_digest: str,
        template_digest: str,
        acquisition_configuration_digest: str,
        qam_configuration_digest: str,
        worker_digest: str,
        interpreter_digest: str,
        runtime_package_tree_digest: str,
        execution_environment_digest: str,
        worker_output_digest: str,
        input_manifest_digest: str,
        session_id: str,
        stream_id: str,
        calibration_digest: str,
        decisions: tuple[PilotWindowDecisionV1, ...],
    ) -> NativeExecutionReceiptV2:
        values = {
            "schema_version": 2,
            "kind": "sealed-native-known-pilot-execution",
            "status": "complete",
            "pipeline_release": pipeline_release,
            "source_revision": source_revision,
            "source_tree_digest": source_tree_digest,
            "release_manifest_digest": release_manifest_digest,
            "template_digest": template_digest,
            "acquisition_configuration_digest": acquisition_configuration_digest,
            "qam_configuration_digest": qam_configuration_digest,
            "worker_digest": worker_digest,
            "interpreter_digest": interpreter_digest,
            "runtime_package_tree_digest": runtime_package_tree_digest,
            "execution_environment_digest": execution_environment_digest,
            "worker_output_digest": worker_output_digest,
            "input_manifest_digest": input_manifest_digest,
            "session_id": session_id,
            "stream_id": stream_id,
            "calibration_digest": calibration_digest,
            "decisions": tuple(item.model_dump(mode="json") for item in decisions),
        }
        return cls.model_validate({**values, "receipt_digest": canonical_digest(values)})


class TrustedNativeReleaseEvidenceV2(ContractModel):
    """Validated release identity including exact worker and interpreter seals."""

    schema_version: Literal[2] = 2
    kind: Literal["validated-current-native-release"] = "validated-current-native-release"
    pipeline_release: Identifier
    source_revision: Annotated[
        str, StringConstraints(pattern=r"^[0-9a-f]{40}$", min_length=40, max_length=40)
    ]
    git_tree: Annotated[
        str, StringConstraints(pattern=r"^[0-9a-f]{40}$", min_length=40, max_length=40)
    ]
    source_tree_digest: Sha256Digest
    release_metadata_digest: Sha256Digest
    worker_digest: Sha256Digest
    interpreter_digest: Sha256Digest
    runtime_package_tree_digest: Sha256Digest
    release_path: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    validator: Literal["deployed-release-validators-v1"] = "deployed-release-validators-v1"
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def _release_evidence_digest_is_exact(self) -> Self:
        normalized = posixpath.normpath(self.release_path)
        if (
            not self.release_path.startswith("/")
            or self.release_path != normalized
            or normalized == "/mnt/qnap01"
            or normalized.startswith("/mnt/qnap01/")
        ):
            raise ValueError("validated native release path is unsafe")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"evidence_digest"}))
        if self.evidence_digest != expected:
            raise ValueError(f"native release evidence digest does not match content: {expected}")
        return self


class NativeKnownPilotEvidenceProductV2(ContractModel):
    """Release-local evidence product; intentionally still acceptance-ineligible."""

    schema_version: Literal[2] = 2
    kind: Literal["native-known-pilot-evidence"] = "native-known-pilot-evidence"
    analysis_run_id: Identifier
    scope_key: Identifier
    release: TrustedNativeReleaseEvidenceV2
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1
    execution: NativeExecutionReceiptV2
    acceptance_eligible: Literal[False] = False
    product_digest: Sha256Digest

    @model_validator(mode="after")
    def _product_is_exactly_bound(self) -> Self:
        if (
            not self.calibration.matches(self.path_identity)
            or self.execution.pipeline_release != self.release.pipeline_release
            or self.execution.source_revision != self.release.source_revision
            or self.execution.source_tree_digest != self.release.source_tree_digest
            or self.execution.release_manifest_digest != self.release.release_metadata_digest
            or self.execution.worker_digest != self.release.worker_digest
            or self.execution.interpreter_digest != self.release.interpreter_digest
            or self.execution.runtime_package_tree_digest
            != self.release.runtime_package_tree_digest
            or self.execution.input_manifest_digest != self.path_identity.manifest_digest
            or self.execution.session_id != self.path_identity.session_id
            or self.execution.stream_id != self.path_identity.stream_id
            or self.execution.calibration_digest != self.calibration.calibration_digest
        ):
            raise ValueError("native evidence product lineage is inconsistent")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"product_digest"}))
        if self.product_digest != expected:
            raise ValueError(f"native evidence product digest does not match content: {expected}")
        return self


class LegacyExecutionEnvelopeV1(ContractModel):
    """Complete legacy oracle evidence contextualized by a trusted scope resolver."""

    schema_version: Literal[1] = 1
    kind: Literal["loaded-sealed-legacy-pilot-oracle"] = "loaded-sealed-legacy-pilot-oracle"
    oracle_receipt_digest: Sha256Digest
    oracle_configuration_digest: Sha256Digest
    oracle_environment_digest: Sha256Digest
    oracle_worker_output_digest: Sha256Digest
    oracle_iq_digest: Sha256Digest
    receiver_center_hz: float
    input_manifest_digest: Sha256Digest
    session_id: Identifier
    stream_id: Identifier
    calibration_digest: Sha256Digest
    decisions: tuple[PilotWindowDecisionV1, ...]
    envelope_digest: Sha256Digest

    @model_validator(mode="after")
    def _complete_frozen_oracle_is_embedded(self) -> Self:
        if len(self.decisions) != 600 or tuple(
            item.window_index for item in self.decisions
        ) != tuple(range(600)):
            raise ValueError("legacy execution envelope requires all 600 ordered decisions")
        if any(
            item.source != "legacy_reference"
            or item.algorithm_id != "leo-tracker-pilot-symbolwise-v3-single-rx"
            or item.algorithm_version != _LEGACY_REVISION
            or item.status is not PilotDecisionStatus.EVALUATED
            for item in self.decisions
        ):
            raise ValueError("legacy execution envelope decisions are not the frozen oracle")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"envelope_digest"}))
        if self.envelope_digest != expected:
            raise ValueError(f"legacy execution envelope digest does not match content: {expected}")
        return self


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
        if self.reference.source != "legacy_reference" or self.native.source != "native":
            raise ValueError("persisted window detector roles are not frozen v1")
        expected_algorithms = (
            (
                "leo-tracker-pilot-symbolwise-v3-single-rx",
                "0bb80d14759fd8496b74e7d3219a690be18565a6",
            )
            if self.reference.status is PilotDecisionStatus.EVALUATED
            else ("unavailable-window-decision", "1.0.0"),
            (
                "native-symbolwise-known-pilot",
                "1.0.0",
            )
            if self.native.status is PilotDecisionStatus.EVALUATED
            else ("unavailable-window-decision", "1.0.0"),
        )
        actual_algorithms = (
            (self.reference.algorithm_id, self.reference.algorithm_version),
            (self.native.algorithm_id, self.native.algorithm_version),
        )
        if actual_algorithms != expected_algorithms:
            raise ValueError("persisted window detector algorithms are not frozen v1")
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
        expected_epoch: int | None = None
        expected_cfo: float | None = None
        expected_associated = False
        if self.reference.candidate is True and self.native.candidate is True:
            assert self.reference.epoch_sample is not None and self.native.epoch_sample is not None
            assert self.reference.cfo_hz is not None and self.native.cfo_hz is not None
            period = round(2_500_000 / 750)
            raw_error = abs(self.reference.epoch_sample - self.native.epoch_sample) % period
            expected_epoch = min(raw_error, period - raw_error)
            expected_cfo = abs(self.reference.cfo_hz - self.native.cfo_hz)
            expected_associated = expected_epoch <= 8 and expected_cfo <= 500.0
        expected_reference_qam = _decision_qam_positive(self.reference)
        expected_native_qam = _decision_qam_positive(self.native)
        expected_difference = (
            self.native.qam_accuracy - self.reference.qam_accuracy
            if expected_associated
            and self.reference.qam_accuracy is not None
            and self.native.qam_accuracy is not None
            else None
        )
        if (
            self.candidate_associated != expected_associated
            or self.circular_epoch_error_samples != expected_epoch
            or self.absolute_cfo_error_hz != expected_cfo
            or self.reference_qam_positive != expected_reference_qam
            or self.native_qam_positive != expected_native_qam
            or self.qam_accuracy_difference != expected_difference
        ):
            raise ValueError("matched window derived flags/metrics were not exactly recomputed")
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
    analysis_run_id: Identifier
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    production_source_revision: Annotated[str, StringConstraints(min_length=7, max_length=128)]
    config: MatchedPilotAcceptanceConfigV1
    legacy_oracle_receipt_digest: Sha256Digest
    legacy_execution: LegacyExecutionEnvelopeV1 | None = None
    legacy_stream_configuration_digest: Sha256Digest
    legacy_receiver_center_hz: float
    legacy_execution_verified: Literal[False] = False
    native_execution: NativeExecutionReceiptV1 | None
    execution_evidence_verified: Literal[False] = False
    input_manifest_digest: Sha256Digest
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1 | None
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
        evaluated = tuple(
            item
            for item in self.windows
            if item.reference.status is PilotDecisionStatus.EVALUATED
            and item.native.status is PilotDecisionStatus.EVALUATED
        )
        recomputed_counts = MatchedCandidateCountsV1(
            n11=sum(
                item.reference.candidate is True and item.native.candidate is True
                for item in evaluated
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
        recomputed_associated = sum(
            item.reference.candidate is True and item.candidate_associated for item in evaluated
        )
        if (
            self.complete_raw_window_count != sum(item.raw_window_complete for item in self.windows)
            or self.evaluated_pair_count != len(evaluated)
            or self.missing_or_insufficient_window_count != 600 - len(evaluated)
            or self.counts != recomputed_counts
            or self.associated_reference_positive_count != recomputed_associated
        ):
            raise ValueError("receipt window counts were not exactly recomputed")
        if self.recovery.trials != self.counts.n11 + self.counts.n10:
            raise ValueError("recovery denominator must be reference-positive windows")
        if self.recovery.successes != self.associated_reference_positive_count:
            raise ValueError("recovery successes must count associated reference positives")
        if self.pipeline_release != self.config.detector_binding.pipeline_release:
            raise ValueError("receipt pipeline release disagrees with detector binding")
        if self.production_source_revision != self.config.detector_binding.native_source_revision:
            raise ValueError("receipt source revision disagrees with detector binding")
        if self.input_manifest_digest != self.path_identity.manifest_digest:
            raise ValueError("receipt input manifest is not bound to receiver-path identity")
        if (
            self.calibration is not None
            and self.legacy_receiver_center_hz != self.calibration.center_hz
        ):
            raise ValueError("legacy oracle center differs from embedded stream calibration")
        if self.native_execution is not None and (
            self.native_execution.input_manifest_digest != self.input_manifest_digest
            or self.native_execution.session_id != self.path_identity.session_id
            or self.native_execution.stream_id != self.path_identity.stream_id
            or self.calibration is None
            or self.native_execution.calibration_digest != self.calibration.calibration_digest
            or self.native_execution.pipeline_release != self.pipeline_release
            or self.native_execution.source_revision != self.production_source_revision
            or self.native_execution.source_tree_digest
            != self.config.detector_binding.native_source_tree_digest
            or self.native_execution.release_manifest_digest
            != self.config.detector_binding.native_release_manifest_digest
            or self.native_execution.template_digest
            != self.config.detector_binding.native_template_digest
            or self.native_execution.acquisition_configuration_digest
            != self.config.detector_binding.native_acquisition_configuration_digest
            or self.native_execution.qam_configuration_digest
            != self.config.detector_binding.native_qam_configuration_digest
        ):
            raise ValueError("sealed native execution receipt is not bound to this analysis")
        if self.legacy_execution is not None and (
            self.legacy_execution.oracle_receipt_digest != self.legacy_oracle_receipt_digest
            or self.legacy_execution.oracle_configuration_digest
            != self.legacy_stream_configuration_digest
            or self.legacy_execution.receiver_center_hz != self.legacy_receiver_center_hz
            or self.legacy_execution.input_manifest_digest != self.input_manifest_digest
            or self.legacy_execution.session_id != self.path_identity.session_id
            or self.legacy_execution.stream_id != self.path_identity.stream_id
            or self.calibration is None
            or self.legacy_execution.calibration_digest != self.calibration.calibration_digest
            or self.legacy_execution.decisions != tuple(window.reference for window in self.windows)
        ):
            raise ValueError("sealed legacy execution envelope is not bound to matched windows")
        if self.native_execution is not None and self.native_execution.decisions != tuple(
            window.native for window in self.windows
        ):
            raise ValueError("sealed native execution receipt differs from matched windows")
        if self.mean_qam_accuracy_difference is not None and not math.isfinite(
            self.mean_qam_accuracy_difference
        ):
            raise ValueError("mean QAM accuracy difference must be finite")
        if self.qam_accuracy_difference_lower_bound is not None and not math.isfinite(
            self.qam_accuracy_difference_lower_bound
        ):
            raise ValueError("QAM accuracy lower bound must be finite")
        # Importing the neutral numerical evaluator lazily avoids an import cycle while
        # ensuring persisted summaries are always recomputed from their 600 windows.
        from leo.analysis.starlink.acceptance import (  # noqa: PLC0415
            binomial_lower_bounds,
            paired_student_t_lower_bound,
        )

        expected_recovery = binomial_lower_bounds(
            recomputed_associated,
            recomputed_counts.n11 + recomputed_counts.n10,
            alpha=self.config.confidence_alpha,
        )
        reference_qam = sum(item.reference_qam_positive for item in evaluated)
        native_qam = sum(
            item.reference_qam_positive
            and item.candidate_associated
            and item.native_qam_positive
            and item.qam_accuracy_difference is not None
            and item.qam_accuracy_difference >= -self.config.qam_accuracy_noninferiority_margin
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
        expected_mean = sum(differences) / len(differences) if differences else None
        expected_lower = paired_student_t_lower_bound(
            differences,
            alpha=self.config.qam_confidence_alpha,
        )
        expected_qam_pass = (
            None
            if reference_qam < 2 or expected_lower is None
            else native_qam == reference_qam
            and expected_lower >= -self.config.qam_accuracy_noninferiority_margin
        )
        if (
            self.recovery != expected_recovery
            or self.reference_qam_positive_count != reference_qam
            or self.native_qam_recovery_count != native_qam
            or self.mean_qam_accuracy_difference != expected_mean
            or self.qam_accuracy_difference_lower_bound != expected_lower
            or self.qam_noninferiority_passed != expected_qam_pass
        ):
            raise ValueError("receipt statistical summaries were not exactly recomputed")
        preflight_failed = (
            not self.execution_evidence_verified
            or self.calibration is None
            or not self.calibration.matches(self.path_identity)
            or not calibration_search_domain_covers(self.calibration, self.config)
        )
        expected_status, expected_reason = _recomputed_receipt_status(
            preflight_failed=preflight_failed,
            complete_raw=self.complete_raw_window_count,
            insufficient=self.missing_or_insufficient_window_count,
            recovery=expected_recovery,
            reference_qam=reference_qam,
            qam_passed=expected_qam_pass,
            config=self.config,
        )
        if self.status is not expected_status or self.reason != expected_reason:
            raise ValueError("receipt status/reason were not exactly recomputed")
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


class AcceptedCaptureStreamInventoryV1(ContractModel):
    """One immutable stream admitted by the accepted capture campaign receipt."""

    schema_version: Literal[1] = 1
    session_id: Identifier
    stream_id: Identifier
    manifest_digest: Sha256Digest
    profile_revision_digest: Sha256Digest
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Literal[1] = 1
    physical_receiver_id: Identifier
    hardware_epoch_id: Identifier
    station_topology_evidence_digest: Sha256Digest
    role: AcceptanceStreamRole
    pairing_group_id: Identifier | None = None
    synchronization_grade: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    estimated_overlap_fraction: Annotated[float | None, Field(ge=0, le=1)] = None
    guaranteed_overlap_fraction: Annotated[float | None, Field(ge=0, le=1)] = None
    start_skew_uncertainty_ns: Annotated[int | None, Field(ge=0)] = None
    sample_loss_observability: Literal["not_observable"] = "not_observable"
    dwell_start_utc_ns: Annotated[int, Field(ge=0)]
    dwell_end_utc_ns: Annotated[int, Field(gt=0)]
    sample_count: Literal[150_000_000] = 150_000_000

    @model_validator(mode="after")
    def _identity_and_dwell_are_consistent(self) -> Self:
        if self.dwell_end_utc_ns <= self.dwell_start_utc_ns:
            raise ValueError("capture inventory dwell must be non-empty")
        if (self.role is AcceptanceStreamRole.PAIRED) != (self.pairing_group_id is not None):
            raise ValueError("capture inventory pairing identity disagrees with role")
        overlap = (
            self.estimated_overlap_fraction,
            self.guaranteed_overlap_fraction,
            self.start_skew_uncertainty_ns,
        )
        if self.role is AcceptanceStreamRole.PAIRED:
            if any(value is None for value in overlap):
                raise ValueError("paired inventory requires estimated overlap and uncertainty")
        elif any(value is not None for value in overlap):
            raise ValueError("independent inventory cannot claim paired overlap")
        return self


class MatchedPilotAcceptanceCampaignConfigV1(ContractModel):
    """Predeclared two-radio, 30-session acceptance campaign."""

    schema_version: Literal[1] = 1
    campaign_id: Identifier
    capture_campaign_receipt_digest: Sha256Digest
    capture_campaign_receipt: dict[str, JsonValue]
    capture_inventory_derivation: Literal["capture-mode-v2-authoritative-revalidation"] = (
        "capture-mode-v2-authoritative-revalidation"
    )
    detector_binding: DetectorPipelineBindingV1
    config_digest: Sha256Digest
    paired_session_count: Literal[10] = 10
    strata: tuple[AcceptanceCampaignStratumV1, ...]
    capture_inventory: tuple[AcceptedCaptureStreamInventoryV1, ...]

    @model_validator(mode="after")
    def _inventory_and_digest_are_exact(self) -> Self:
        from leo.qualification.capture_modes import (  # noqa: PLC0415
            CaptureModeCampaignAcceptanceReceiptV2,
        )
        from leo.qualification.scientific_campaign import (  # noqa: PLC0415
            _derive_capture_campaign_components,
        )

        capture_receipt = CaptureModeCampaignAcceptanceReceiptV2.model_validate(
            self.capture_campaign_receipt
        )
        if not capture_receipt.accepted:
            raise ValueError("scientific campaign requires an accepted typed capture receipt")
        expected_capture_digest = canonical_digest(capture_receipt.model_dump(mode="json"))
        if self.capture_campaign_receipt_digest != expected_capture_digest:
            raise ValueError("capture campaign receipt digest does not match embedded receipt")
        expected_strata, expected_inventory = _derive_capture_campaign_components(capture_receipt)
        if self.strata != tuple(sorted(expected_strata, key=lambda item: item.stratum_id)) or (
            self.capture_inventory
            != tuple(sorted(expected_inventory, key=lambda item: (item.session_id, item.stream_id)))
        ):
            raise ValueError("campaign inventory was not derived from embedded capture receipt")
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
        if len(self.capture_inventory) != 40:
            raise ValueError("accepted capture inventory must contain exactly 40 streams")
        if len({(item.session_id, item.stream_id) for item in self.capture_inventory}) != 40:
            raise ValueError("accepted capture inventory stream identities must be unique")
        inventory_identities = {
            (item.radio_id, item.radio_serial, item.receiver_id, item.physical_receiver_id)
            for item in self.capture_inventory
        }
        if inventory_identities != identities:
            raise ValueError("capture inventory hardware paths disagree with strata")
        if len({item.profile_revision_digest for item in self.capture_inventory}) != 1:
            raise ValueError("capture inventory must use one frozen profile revision")
        independent = tuple(
            item for item in self.capture_inventory if item.role is AcceptanceStreamRole.INDEPENDENT
        )
        paired = tuple(
            item for item in self.capture_inventory if item.role is AcceptanceStreamRole.PAIRED
        )
        if len(independent) != 20 or len({item.session_id for item in independent}) != 20:
            raise ValueError("capture inventory requires 20 distinct independent sessions")
        groups: dict[str, list[AcceptedCaptureStreamInventoryV1]] = {}
        for item in paired:
            assert item.pairing_group_id is not None
            groups.setdefault(item.pairing_group_id, []).append(item)
        if len(groups) != 10 or any(
            len(group) != 2
            or len({item.session_id for item in group}) != 1
            or {
                (item.radio_id, item.radio_serial, item.receiver_id, item.physical_receiver_id)
                for item in group
            }
            != identities
            for group in groups.values()
        ):
            raise ValueError("capture inventory requires 10 exact two-radio paired sessions")
        paired_sessions = {group[0].session_id for group in groups.values()}
        if paired_sessions & {item.session_id for item in independent}:
            raise ValueError("paired and independent capture session IDs must be distinct")
        for identity in identities:
            for role in (AcceptanceStreamRole.INDEPENDENT, AcceptanceStreamRole.PAIRED):
                count = sum(
                    (
                        item.radio_id,
                        item.radio_serial,
                        item.receiver_id,
                        item.physical_receiver_id,
                    )
                    == identity
                    and item.role is role
                    for item in self.capture_inventory
                )
                if count != 10:
                    raise ValueError("capture inventory requires 10 streams per path/role stratum")
        expected = matched_pilot_campaign_config_digest(self)
        if self.config_digest != expected:
            raise ValueError(f"campaign config digest does not match content: {expected}")
        return self

    @classmethod
    def _from_trusted_capture_resolver(
        cls,
        *,
        campaign_id: str,
        capture_campaign_receipt: dict[str, JsonValue],
        detector_binding: DetectorPipelineBindingV1,
        strata: tuple[AcceptanceCampaignStratumV1, ...],
        capture_inventory: tuple[AcceptedCaptureStreamInventoryV1, ...],
    ) -> MatchedPilotAcceptanceCampaignConfigV1:
        ordered = tuple(sorted(strata, key=lambda item: item.stratum_id))
        capture_campaign_receipt_digest = canonical_digest(capture_campaign_receipt)
        values = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "capture_campaign_receipt_digest": capture_campaign_receipt_digest,
            "capture_campaign_receipt": capture_campaign_receipt,
            "capture_inventory_derivation": "capture-mode-v2-authoritative-revalidation",
            "detector_binding": detector_binding.model_dump(mode="json"),
            "paired_session_count": 10,
            "strata": tuple(item.model_dump(mode="json") for item in ordered),
            "capture_inventory": tuple(
                item.model_dump(mode="json")
                for item in sorted(
                    capture_inventory, key=lambda item: (item.session_id, item.stream_id)
                )
            ),
        }
        return cls(
            campaign_id=campaign_id,
            capture_campaign_receipt_digest=capture_campaign_receipt_digest,
            capture_campaign_receipt=capture_campaign_receipt,
            detector_binding=detector_binding,
            config_digest=canonical_digest(values),
            strata=ordered,
            capture_inventory=tuple(
                sorted(capture_inventory, key=lambda item: (item.session_id, item.stream_id))
            ),
        )


class AcceptanceCampaignStreamV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    stream_id: Identifier
    stratum_id: Identifier
    pairing_group_id: Identifier | None = None
    pipeline_run_id: Identifier
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    production_source_revision: Annotated[str, StringConstraints(min_length=7, max_length=128)]
    analysis_product_digest: Sha256Digest
    analysis_product_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    receipt: MatchedPilotAcceptanceReceiptV1

    @model_validator(mode="after")
    def _pairing_matches_role_later(self) -> Self:
        if not self.session_id or not self.stream_id:
            raise ValueError("campaign stream identity is required")
        if (
            self.receipt.path_identity.session_id != self.session_id
            or self.receipt.path_identity.stream_id != self.stream_id
            or self.receipt.analysis_run_id != self.pipeline_run_id
            or self.receipt.pipeline_release != self.pipeline_release
            or self.receipt.production_source_revision != self.production_source_revision
        ):
            raise ValueError("campaign stream pipeline/product identity is not bound to receipt")
        expected_product_digest = canonical_digest(self.receipt.model_dump(mode="json"))
        expected_uri = (
            f"bulk://analysis/{self.session_id}/{self.pipeline_run_id}/scientific/"
            f"matched-pilot-acceptance/{self.stream_id}/"
            "starlink.matched-acceptance.v1.json"
        )
        if (
            self.analysis_product_digest != expected_product_digest
            or self.analysis_product_uri != expected_uri
        ):
            raise ValueError("campaign product digest/URI is not canonical receipt evidence")
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
    catalog_artifact_uri: None = None
    cli_projection_receipt_digest: None = None
    ui_projection_receipt_digest: None = None
    production_accepted: Literal[False] = False
    production_acceptance_rule: Literal[
        "v1_never_accepts_without_future_typed_catalog_cli_ui_verifier"
    ] = "v1_never_accepts_without_future_typed_catalog_cli_ui_verifier"
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
        if (
            len({item.pipeline_run_id for item in self.streams}) != len(self.streams)
            or len({item.analysis_product_digest for item in self.streams}) != len(self.streams)
            or len({item.analysis_product_uri for item in self.streams}) != len(self.streams)
            or len({item.receipt.legacy_oracle_receipt_digest for item in self.streams})
            != len(self.streams)
        ):
            raise ValueError("campaign pipeline runs/products must be uniquely bound")
        expected_strata = tuple(item.stratum_id for item in self.config.strata)
        if tuple(item.stratum_id for item in self.strata) != expected_strata:
            raise ValueError("campaign results must follow the predeclared strata")
        inventory = {
            (item.session_id, item.stream_id): item for item in self.config.capture_inventory
        }
        strata = {item.stratum_id: item for item in self.config.strata}
        pairing_groups: dict[str, list[AcceptanceCampaignStreamV1]] = {}
        for stream in self.streams:
            key = (stream.session_id, stream.stream_id)
            expected = inventory.get(key)
            declaration = strata.get(stream.stratum_id)
            identity = stream.receipt.path_identity
            if expected is None or declaration is None:
                raise ValueError("campaign stream is outside accepted capture lineage")
            if (
                identity.radio_id != expected.radio_id
                or identity.radio_serial != expected.radio_serial
                or identity.receiver_id != expected.receiver_id
                or identity.physical_receiver_id != expected.physical_receiver_id
                or identity.hardware_epoch_id != expected.hardware_epoch_id
                or identity.manifest_digest != expected.manifest_digest
                or identity.profile_revision_digest != expected.profile_revision_digest
                or identity.capture_utc_ns != expected.dwell_start_utc_ns
                or identity.capture_end_utc_ns != expected.dwell_end_utc_ns
                or stream.pairing_group_id != expected.pairing_group_id
                or declaration.radio_id != expected.radio_id
                or declaration.radio_serial != expected.radio_serial
                or declaration.receiver_id != expected.receiver_id
                or declaration.physical_receiver_id != expected.physical_receiver_id
                or declaration.role is not expected.role
                or stream.analysis_product_digest
                != canonical_digest(stream.receipt.model_dump(mode="json"))
                or stream.analysis_product_uri
                != (
                    f"bulk://analysis/{stream.session_id}/{stream.pipeline_run_id}/scientific/"
                    f"matched-pilot-acceptance/{stream.stream_id}/"
                    "starlink.matched-acceptance.v1.json"
                )
            ):
                raise ValueError("campaign stream lineage/product does not match predeclaration")
            if stream.pairing_group_id is not None:
                pairing_groups.setdefault(stream.pairing_group_id, []).append(stream)
        paired_strata = {
            item.stratum_id
            for item in self.config.strata
            if item.role is AcceptanceStreamRole.PAIRED
        }
        if any(
            len(group) != 2
            or len({item.session_id for item in group}) != 1
            or {item.stratum_id for item in group} != paired_strata
            for group in pairing_groups.values()
        ):
            raise ValueError("persisted campaign pairing lineage is invalid")
        if self.observed_paired_session_count != len(pairing_groups):
            raise ValueError("observed paired-session count was not recomputed")
        from leo.analysis.starlink.acceptance import _aggregate_campaign_stratum  # noqa: PLC0415

        recomputed = tuple(
            _aggregate_campaign_stratum(
                declaration.stratum_id,
                tuple(item for item in self.streams if item.stratum_id == declaration.stratum_id),
                declaration,
            )
            for declaration in self.config.strata
        )
        if self.strata != recomputed:
            raise ValueError("campaign strata were not exactly recomputed from stream receipts")
        statuses = {item.status for item in recomputed}
        if MatchedAcceptanceStatus.INCONCLUSIVE in statuses:
            expected_status = MatchedAcceptanceStatus.INCONCLUSIVE
            expected_reason = (
                "campaign lacks the predeclared sessions or reference-positive evidence"
            )
        elif MatchedAcceptanceStatus.FAIL in statuses:
            expected_status = MatchedAcceptanceStatus.FAIL
            expected_reason = "one or more predeclared campaign strata failed a frozen gate"
        else:
            expected_status = MatchedAcceptanceStatus.PASS
            expected_reason = "all predeclared campaign strata passed the frozen aggregate gates"
        if self.status is not expected_status or self.reason != expected_reason:
            raise ValueError("campaign status/reason were not exactly recomputed")
        if any(
            item.pipeline_release != self.config.detector_binding.pipeline_release
            or item.production_source_revision
            != self.config.detector_binding.native_source_revision
            for item in self.streams
        ):
            raise ValueError("campaign stream revisions disagree with pinned detector binding")
        return self


def matched_pilot_acceptance_config_digest(value: MatchedPilotAcceptanceConfigV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"config_digest"}))


def matched_pilot_campaign_config_digest(
    value: MatchedPilotAcceptanceCampaignConfigV1,
) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"config_digest"}))


def pilot_window_decision_digest(value: PilotWindowDecisionV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"evidence_digest"}))


def detector_pipeline_binding_digest(value: DetectorPipelineBindingV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"binding_digest"}))


def _decision_qam_positive(decision: PilotWindowDecisionV1) -> bool:
    return bool(
        decision.candidate is True
        and decision.qam_accuracy is not None
        and decision.qam_evm is not None
        and decision.qam_accuracy >= 0.60
        and decision.qam_evm <= 1.25
    )


def calibration_search_domain_covers(
    calibration: ReceiverFrequencyCalibrationV1,
    config: MatchedPilotAcceptanceConfigV1,
) -> bool:
    residual_lower = (
        calibration.uncertainty_lower_hz - calibration.center_hz - config.expected_doppler_guard_hz
    )
    residual_upper = (
        calibration.uncertainty_upper_hz - calibration.center_hz + config.expected_doppler_guard_hz
    )
    absolute_lower = (
        calibration.uncertainty_lower_hz
        - config.expected_doppler_guard_hz
        - config.occupied_pilot_half_span_hz
    )
    absolute_upper = (
        calibration.uncertainty_upper_hz
        + config.expected_doppler_guard_hz
        + config.occupied_pilot_half_span_hz
    )
    sampled_limit = config.sample_rate_hz / 2 - config.sampled_band_edge_guard_hz
    return (
        residual_lower >= config.residual_search_lower_hz
        and residual_upper <= config.residual_search_upper_hz
        and absolute_lower >= -sampled_limit
        and absolute_upper <= sampled_limit
    )


def _recomputed_receipt_status(
    *,
    preflight_failed: bool,
    complete_raw: int,
    insufficient: int,
    recovery: BinomialLowerBoundsV1,
    reference_qam: int,
    qam_passed: bool | None,
    config: MatchedPilotAcceptanceConfigV1,
) -> tuple[MatchedAcceptanceStatus, str]:
    if preflight_failed or complete_raw != 600 or insufficient:
        return (
            MatchedAcceptanceStatus.INSUFFICIENT,
            "the fixed 600-window denominator has missing or insufficient evidence",
        )
    if recovery.trials < 30:
        return (
            MatchedAcceptanceStatus.INCONCLUSIVE,
            "too few legacy-reference positive windows for candidate-recovery inference",
        )
    if reference_qam < 1:
        return (
            MatchedAcceptanceStatus.INCONCLUSIVE,
            "too few legacy-reference QAM-positive windows for QAM noninferiority",
        )
    if qam_passed is None:
        return (
            MatchedAcceptanceStatus.INCONCLUSIVE,
            "paired QAM evidence cannot estimate the declared one-sided interval",
        )
    passed = bool(
        recovery.point_estimate is not None
        and recovery.point_estimate >= config.minimum_recovery_fraction
        and recovery.wilson_one_sided_lower is not None
        and recovery.wilson_one_sided_lower >= config.minimum_wilson_lower_bound
        and recovery.clopper_pearson_one_sided_lower is not None
        and recovery.clopper_pearson_one_sided_lower >= config.minimum_exact_lower_bound
        and qam_passed
    )
    if passed:
        return (
            MatchedAcceptanceStatus.PASS,
            "native candidate recovery and known-pilot QAM are noninferior under frozen gates",
        )
    return (
        MatchedAcceptanceStatus.FAIL,
        "one or more frozen candidate-recovery or known-pilot QAM gates failed",
    )
