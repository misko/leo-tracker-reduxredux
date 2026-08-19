"""Matched known-pilot candidate-recovery acceptance.

This module never imports a historical repository.  A reference decision port
supplies sealed legacy-oracle results, while a separate native port evaluates
the same immutable IQ window.  Every one of the fixed 600 windows remains in
the receipt, including missing and insufficient observations.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

from leo.analysis._streaming import IqStreamError, validated_blocks
from leo.analysis.qam import analyze_pilot_qam
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame, template_sha256
from leo.contracts.calibration import (
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest
from leo.contracts.scientific import (
    AcceptanceCampaignStratumResultV1,
    AcceptanceCampaignStratumV1,
    AcceptanceCampaignStreamV1,
    AcceptanceStreamRole,
    BinomialLowerBoundsV1,
    LegacyExecutionEnvelopeV1,
    MatchedAcceptanceStatus,
    MatchedCandidateCountsV1,
    MatchedPilotAcceptanceCampaignConfigV1,
    MatchedPilotAcceptanceCampaignReceiptV1,
    MatchedPilotAcceptanceConfigV1,
    MatchedPilotAcceptanceReceiptV1,
    MatchedPilotWindowV1,
    NativeExecutionReceiptV1,
    NativeExecutionReceiptV2,
    NativeKnownPilotEvidenceProductV2,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    TrustedNativeReleaseEvidenceV2,
    calibration_search_domain_covers,
)
from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    ResourceClass,
    StageOutcome,
    StageResult,
    StageSpec,
)


class PilotWindowDecisionPort(Protocol):
    """One candidate decision implementation evaluated on a fixed window."""

    @property
    def source(self) -> str: ...

    @property
    def maximum_working_set_bytes(self) -> int: ...

    @property
    def detector_binding_digest(self) -> str: ...

    @property
    def execution_verified(self) -> bool: ...

    @property
    def native_execution_receipt(self) -> NativeExecutionReceiptV1 | None: ...

    def evaluate(
        self,
        *,
        window_index: int,
        sample_start: int,
        samples: npt.NDArray[np.complex64],
        sample_rate_hz: int,
        calibration: ReceiverFrequencyCalibrationV1,
    ) -> PilotWindowDecisionV1: ...


class LegacyPilotWindowDecisionPort(PilotWindowDecisionPort, Protocol):
    @property
    def oracle_receipt_digest(self) -> str: ...

    @property
    def stream_configuration_digest(self) -> str: ...

    @property
    def receiver_center_hz(self) -> float: ...


@dataclass(frozen=True, slots=True)
class MatchedAcceptanceBinding:
    input_manifest_digest: Sha256Digest
    legacy_oracle_receipt_digest: Sha256Digest
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1 | None
    reference: LegacyPilotWindowDecisionPort
    native: PilotWindowDecisionPort | None = None
    legacy_execution: LegacyExecutionEnvelopeV1 | None = None
    native_execution: NativeExecutionReceiptV1 | None = None


class MatchedAcceptanceBindingProvider(Protocol):
    def resolve(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
    ) -> MatchedAcceptanceBinding: ...


@dataclass(frozen=True, slots=True)
class StaticMatchedAcceptanceBindingProvider:
    """Explicit binding useful to composition roots and deterministic tests."""

    binding: MatchedAcceptanceBinding

    def resolve(
        self,
        _context: AnalysisContext,
        _iq: IqReader,
        _products: ProductReader,
    ) -> MatchedAcceptanceBinding:
        return self.binding


@dataclass(frozen=True, slots=True)
class NativeEvidenceScopeBinding:
    input_manifest_digest: Sha256Digest
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1


class NativeEvidenceScopeBindingProvider(Protocol):
    def resolve(self, context: AnalysisContext, iq: IqReader) -> NativeEvidenceScopeBinding: ...


class NativeReleaseEvidenceProvider(Protocol):
    def resolve(self, context: AnalysisContext) -> TrustedNativeReleaseEvidenceV2: ...


@dataclass(frozen=True, slots=True)
class NativeEvidenceExecutionResult:
    decisions: tuple[PilotWindowDecisionV1, ...]
    execution_environment_digest: Sha256Digest
    worker_output_digest: Sha256Digest


class NativeEvidenceExecutor(Protocol):
    def execute(
        self,
        *,
        iq: IqReader,
        path_identity: ReceiverPathIdentityV1,
        calibration: ReceiverFrequencyCalibrationV1,
        release: TrustedNativeReleaseEvidenceV2,
        config: MatchedPilotAcceptanceConfigV1,
    ) -> NativeEvidenceExecutionResult: ...


class NativeKnownPilotDecisionPort:
    """Current native acquisition and known-pilot QAM implementation."""

    source = "native"

    def __init__(self, config: MatchedPilotAcceptanceConfigV1) -> None:
        self._config = config
        self._acquisition_config = SymbolwiseAcquisitionConfig(
            maximum_probe_samples=config.window_sample_count
        )
        binding = config.detector_binding
        if binding.native_template_digest != native_template_digest():
            raise ValueError("pinned native template digest differs from implementation")
        if (
            binding.native_acquisition_configuration_digest
            != native_acquisition_configuration_digest(self._acquisition_config)
        ):
            raise ValueError("pinned native acquisition configuration differs from implementation")
        if binding.native_qam_configuration_digest != native_qam_configuration_digest():
            raise ValueError("pinned native QAM configuration differs from implementation")

    @property
    def detector_binding_digest(self) -> str:
        return self._config.detector_binding.binding_digest

    @property
    def execution_verified(self) -> bool:
        # This numerical implementation is not acceptance evidence until a sealed
        # native release/source-tree execution receipt is introduced.
        return False

    @property
    def native_execution_receipt(self) -> NativeExecutionReceiptV1 | None:
        return None

    @property
    def maximum_working_set_bytes(self) -> int:
        # The bounded acquisition/QAM kernels operate on at most one 25k complex128
        # working copy plus templates and score grids.  This is a conservative
        # declared bound, exercised independently by their component tests.
        return 16 * 1024 * 1024

    def evaluate(
        self,
        *,
        window_index: int,
        sample_start: int,
        samples: npt.NDArray[np.complex64],
        sample_rate_hz: int,
        calibration: ReceiverFrequencyCalibrationV1,
    ) -> PilotWindowDecisionV1:
        window_iq_digest = _window_iq_digest(samples)
        numerical_calibration = ReceiverFrequencyCalibration(
            receiver_id=calibration.physical_receiver_id,
            center_hz=calibration.center_hz,
            calibration_sha256=calibration.calibration_digest.removeprefix("sha256:"),
        )
        acquisition = acquire_symbolwise(
            samples,
            sample_rate_hz,
            numerical_calibration,
            config=self._acquisition_config,
        )
        winner = acquisition.winner
        if winner is None or winner.verify_minus_control_margin < (
            self._config.minimum_native_candidate_margin
        ):
            return PilotWindowDecisionV1.create(
                source="native",
                algorithm_id="native-symbolwise-known-pilot",
                algorithm_version="1.0.0",
                window_iq_digest=window_iq_digest,
                window_index=window_index,
                sample_start=sample_start,
                status=PilotDecisionStatus.EVALUATED,
                candidate=False,
                reason="native acquisition did not pass the frozen candidate-margin gate",
            )
        qam = analyze_pilot_qam(
            samples,
            sample_rate_hz,
            epoch_sample=winner.refined_epoch_sample,
            absolute_cfo_hz=winner.absolute_cfo_hz,
        )
        metrics = qam.metrics if qam.status is NumericalStatus.COMPLETE else None
        return PilotWindowDecisionV1.create(
            source="native",
            algorithm_id="native-symbolwise-known-pilot",
            algorithm_version="1.0.0",
            window_iq_digest=window_iq_digest,
            window_index=window_index,
            sample_start=sample_start,
            status=PilotDecisionStatus.EVALUATED,
            candidate=True,
            epoch_sample=winner.refined_epoch_sample,
            cfo_hz=winner.absolute_cfo_hz,
            qam_accuracy=None if metrics is None else metrics.hard_symbol_accuracy,
            qam_evm=None if metrics is None else metrics.rms_evm,
            reason="native candidate passed the frozen margin gate; candidate evidence only",
        )


MATCHED_ACCEPTANCE_PRODUCT = ProductSpec(kind="starlink.matched-acceptance", schema_version=1)
NATIVE_KNOWN_PILOT_EVIDENCE_PRODUCT = ProductSpec(
    kind="starlink.native-known-pilot-evidence",
    schema_version=2,
)
MATCHED_ACCEPTANCE_CAMPAIGN_PRODUCT = ProductSpec(
    kind="starlink.matched-acceptance-campaign",
    schema_version=1,
)
MATCHED_ACCEPTANCE_STAGE = StageSpec(
    key="matched-pilot-acceptance",
    algorithm_version="1.0.0",
    configuration_schema="matched-known-pilot-acceptance.v1",
    dependencies=("native-known-pilot-evidence",),
    input_products=(
        ProductRequirement(
            kind=NATIVE_KNOWN_PILOT_EVIDENCE_PRODUCT.kind,
            accepted_schema_versions=(1, 2),
        ),
    ),
    output_products=(MATCHED_ACCEPTANCE_PRODUCT,),
    resource_class=ResourceClass.HEAVY,
)
NATIVE_KNOWN_PILOT_EVIDENCE_STAGE = StageSpec(
    key="native-known-pilot-evidence",
    algorithm_version="2.0.0",
    configuration_schema="native-known-pilot-evidence.v2",
    output_products=(NATIVE_KNOWN_PILOT_EVIDENCE_PRODUCT,),
    resource_class=ResourceClass.HEAVY,
)


def native_template_digest() -> str:
    return "sha256:" + template_sha256(qin_edge_pilot_frame(2_500_000.0, "lower"))


def native_acquisition_configuration_digest(config: SymbolwiseAcquisitionConfig) -> str:
    return canonical_digest(asdict(config))


def native_qam_configuration_digest() -> str:
    return canonical_digest(
        {
            "algorithm": "known-pilot-qam-v1",
            "sample_rate_hz": 2_500_000,
            "minimum_qam_accuracy": 0.60,
            "maximum_qam_evm": 1.25,
            "paired_interval": "paired-student-t-one-sided-95",
            "paired_alpha": 0.05,
        }
    )


class NativeKnownPilotEvidenceAnalyzer:
    """Evaluate and seal native decisions under independently validated release evidence."""

    spec = NATIVE_KNOWN_PILOT_EVIDENCE_STAGE

    def __init__(
        self,
        *,
        config: MatchedPilotAcceptanceConfigV1,
        scopes: NativeEvidenceScopeBindingProvider,
        releases: NativeReleaseEvidenceProvider,
        executor: NativeEvidenceExecutor,
    ) -> None:
        self._config = config
        self._scopes = scopes
        self._releases = releases
        self._executor = executor

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        _products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        scope = self._scopes.resolve(context, iq)
        release = self._releases.resolve(context)
        binding = self._config.detector_binding
        if (
            context.pipeline_release != release.pipeline_release
            or release.pipeline_release != binding.pipeline_release
            or release.source_revision != binding.native_source_revision
            or release.source_tree_digest != binding.native_source_tree_digest
            or release.release_metadata_digest != binding.native_release_manifest_digest
        ):
            raise ValueError("validated current release differs from native detector binding")
        if (
            scope.input_manifest_digest != scope.path_identity.manifest_digest
            or not scope.calibration.matches(scope.path_identity)
        ):
            raise ValueError("native evidence scope lacks exact manifest/calibration lineage")
        execution_result = self._executor.execute(
            iq=iq,
            path_identity=scope.path_identity,
            calibration=scope.calibration,
            release=release,
            config=self._config,
        )
        decisions = execution_result.decisions
        execution = NativeExecutionReceiptV2.create(
            pipeline_release=release.pipeline_release,
            source_revision=release.source_revision,
            source_tree_digest=release.source_tree_digest,
            release_manifest_digest=release.release_metadata_digest,
            template_digest=binding.native_template_digest,
            acquisition_configuration_digest=binding.native_acquisition_configuration_digest,
            qam_configuration_digest=binding.native_qam_configuration_digest,
            worker_digest=release.worker_digest,
            interpreter_digest=release.interpreter_digest,
            execution_environment_digest=(
                execution_result.execution_environment_digest
            ),
            worker_output_digest=execution_result.worker_output_digest,
            input_manifest_digest=scope.input_manifest_digest,
            session_id=scope.path_identity.session_id,
            stream_id=scope.path_identity.stream_id,
            calibration_digest=scope.calibration.calibration_digest,
            decisions=decisions,
        )
        values = {
            "schema_version": 2,
            "kind": "native-known-pilot-evidence",
            "analysis_run_id": context.run_id,
            "scope_key": context.scope_key,
            "release": release.model_dump(mode="json"),
            "path_identity": scope.path_identity.model_dump(mode="json"),
            "calibration": scope.calibration.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json"),
            "acceptance_eligible": False,
        }
        product_document = NativeKnownPilotEvidenceProductV2(
            analysis_run_id=context.run_id,
            scope_key=context.scope_key,
            release=release,
            path_identity=scope.path_identity,
            calibration=scope.calibration,
            execution=execution,
            product_digest=canonical_digest(values),
        )
        published = outputs.publish_json(
            NATIVE_KNOWN_PILOT_EVIDENCE_PRODUCT,
            product_document.model_dump(mode="json"),
        )
        complete = all(item.status is PilotDecisionStatus.EVALUATED for item in decisions)
        return StageResult(
            outcome=StageOutcome.COMPLETE if complete else StageOutcome.INSUFFICIENT_DATA,
            products=(published,),
            summary={
                "decision_count": len(decisions),
                "complete": complete,
                "acceptance_eligible": False,
            },
            message=(
                "sealed 600 native decisions under validated release evidence"
                if complete
                else "native evidence retained all windows but one or more were insufficient"
            ),
        )


class MatchedPilotAcceptanceAnalyzer:
    """Standalone reprocessing analyzer publishing through the normal sink."""

    spec = MATCHED_ACCEPTANCE_STAGE

    def __init__(
        self,
        *,
        config: MatchedPilotAcceptanceConfigV1,
        bindings: MatchedAcceptanceBindingProvider,
        native: PilotWindowDecisionPort,
    ) -> None:
        if native.source != "native":
            raise ValueError("native port must declare native source")
        self._config = config
        self._bindings = bindings
        self._native = native

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        _products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        binding = self._bindings.resolve(context, iq, _products)
        if binding.reference.source != "legacy_reference":
            raise ValueError("resolved reference must declare legacy_reference source")
        receipt = evaluate_matched_known_pilot(
            artifact_id=f"matched-{context.run_id}-{context.scope_key}",
            analysis_run_id=context.run_id,
            pipeline_release=context.pipeline_release,
            production_source_revision=self._config.detector_binding.native_source_revision,
            input_manifest_digest=binding.input_manifest_digest,
            legacy_oracle_receipt_digest=binding.legacy_oracle_receipt_digest,
            iq=iq,
            path_identity=binding.path_identity,
            calibration=binding.calibration,
            reference=binding.reference,
            native=binding.native or self._native,
            legacy_execution=binding.legacy_execution,
            native_execution=binding.native_execution,
            config=self._config,
        )
        product = outputs.publish_json(
            MATCHED_ACCEPTANCE_PRODUCT,
            receipt.model_dump(mode="json"),
        )
        if receipt.status in {
            MatchedAcceptanceStatus.INSUFFICIENT,
            MatchedAcceptanceStatus.INCONCLUSIVE,
        }:
            outcome = StageOutcome.INSUFFICIENT_DATA
        else:
            outcome = StageOutcome.COMPLETE
        return StageResult(
            outcome=outcome,
            products=(product,),
            summary={
                "acceptance_status": receipt.status.value,
                "reference_positive_count": receipt.recovery.trials,
                "associated_reference_positive_count": (
                    receipt.associated_reference_positive_count
                ),
                "candidate_only": True,
                "specificity_claimed": False,
            },
            message=receipt.reason,
        )


def evaluate_matched_known_pilot(
    *,
    artifact_id: str,
    analysis_run_id: str,
    pipeline_release: str,
    production_source_revision: str,
    input_manifest_digest: Sha256Digest,
    legacy_oracle_receipt_digest: Sha256Digest,
    iq: IqReader,
    path_identity: ReceiverPathIdentityV1,
    calibration: ReceiverFrequencyCalibrationV1 | None,
    reference: LegacyPilotWindowDecisionPort,
    native: PilotWindowDecisionPort,
    legacy_execution: LegacyExecutionEnvelopeV1 | None = None,
    native_execution: NativeExecutionReceiptV1 | None = None,
    config: MatchedPilotAcceptanceConfigV1,
) -> MatchedPilotAcceptanceReceiptV1:
    """Evaluate the complete fixed denominator with bounded streaming memory."""

    if reference.detector_binding_digest != config.detector_binding.binding_digest:
        raise ValueError("legacy reference port is not bound to the pinned detector receipt")
    if getattr(reference, "oracle_receipt_digest", None) != legacy_oracle_receipt_digest:
        raise ValueError("legacy reference port oracle envelope digest differs from stream binding")
    if calibration is not None and reference.receiver_center_hz != calibration.center_hz:
        raise ValueError("legacy oracle receiver center differs from immutable stream calibration")
    if native.detector_binding_digest != config.detector_binding.binding_digest:
        raise ValueError("native detector port is not bound to the pinned detector configuration")
    # V1 deliberately has no trusted native release publisher/resolver. Complete
    # envelopes are retained and cross-checked, but cannot assert acceptance.

    preflight_reason = _preflight_reason(iq, path_identity, calibration, config)
    windows: dict[int, MatchedPilotWindowV1] = {}
    maximum_working_set = max(
        0,
        reference.maximum_working_set_bytes,
        native.maximum_working_set_bytes,
    )
    stream_error: str | None = None
    if preflight_reason is None and calibration is not None:
        try:
            for index, start, samples, complete, buffered_bytes in _scheduled_windows(
                iq,
                path_identity.receiver_id,
                config,
            ):
                maximum_working_set = max(
                    maximum_working_set,
                    buffered_bytes
                    + reference.maximum_working_set_bytes
                    + native.maximum_working_set_bytes,
                )
                if not complete or samples is None:
                    windows[index] = _missing_window(index, start, "raw IQ window is incomplete")
                    continue
                reference_decision = _safe_decision(
                    reference,
                    expected_source="legacy_reference",
                    window_index=index,
                    sample_start=start,
                    samples=samples,
                    sample_rate_hz=config.sample_rate_hz,
                    calibration=calibration,
                )
                native_decision = _safe_decision(
                    native,
                    expected_source="native",
                    window_index=index,
                    sample_start=start,
                    samples=samples,
                    sample_rate_hz=config.sample_rate_hz,
                    calibration=calibration,
                )
                windows[index] = _match_window(
                    index,
                    start,
                    reference_decision,
                    native_decision,
                    config,
                )
        except (IqStreamError, ValueError) as exc:
            stream_error = f"invalid IQ stream: {exc}"

    absent_reason = preflight_reason or stream_error or "window was not produced by IQ stream"
    for index in range(config.scheduled_window_count):
        windows.setdefault(
            index,
            _missing_window(index, index * config.interval_sample_count, absent_reason),
        )
    ordered = tuple(windows[index] for index in range(config.scheduled_window_count))
    evaluated = tuple(
        item
        for item in ordered
        if item.reference.status is PilotDecisionStatus.EVALUATED
        and item.native.status is PilotDecisionStatus.EVALUATED
    )
    counts = _candidate_counts(evaluated)
    associated = sum(
        item.reference.candidate is True and item.candidate_associated for item in evaluated
    )
    recovery = binomial_lower_bounds(
        associated,
        counts.n11 + counts.n10,
        alpha=config.confidence_alpha,
    )
    reference_qam = sum(item.reference_qam_positive for item in evaluated)
    native_qam_recovery = sum(
        item.reference_qam_positive
        and item.candidate_associated
        and item.native_qam_positive
        and item.qam_accuracy_difference is not None
        and item.qam_accuracy_difference >= -config.qam_accuracy_noninferiority_margin
        for item in evaluated
    )
    qam_differences = tuple(
        item.qam_accuracy_difference
        for item in evaluated
        if item.reference_qam_positive
        and item.candidate_associated
        and item.native_qam_positive
        and item.qam_accuracy_difference is not None
    )
    mean_qam_difference = (
        float(sum(qam_differences) / len(qam_differences)) if qam_differences else None
    )
    qam_lower_bound = paired_student_t_lower_bound(
        qam_differences,
        alpha=config.qam_confidence_alpha,
    )
    qam_passed = (
        None
        if reference_qam < 2 or qam_lower_bound is None
        else native_qam_recovery == reference_qam
        and qam_lower_bound >= -config.qam_accuracy_noninferiority_margin
    )
    complete_raw = sum(item.raw_window_complete for item in ordered)
    insufficient = len(ordered) - len(evaluated)
    status, reason = _acceptance_status(
        preflight_reason=(
            preflight_reason
            or stream_error
            or "trusted legacy/native execution resolver is unavailable in v1"
        ),
        complete_raw=complete_raw,
        insufficient=insufficient,
        recovery=recovery,
        reference_qam=reference_qam,
        qam_passed=qam_passed,
        config=config,
    )
    return MatchedPilotAcceptanceReceiptV1(
        artifact_id=artifact_id,
        analysis_run_id=analysis_run_id,
        pipeline_release=pipeline_release,
        production_source_revision=production_source_revision,
        config=config,
        legacy_oracle_receipt_digest=legacy_oracle_receipt_digest,
        legacy_execution=legacy_execution,
        legacy_stream_configuration_digest=reference.stream_configuration_digest,
        legacy_receiver_center_hz=reference.receiver_center_hz,
        legacy_execution_verified=False,
        native_execution=native_execution,
        execution_evidence_verified=False,
        input_manifest_digest=input_manifest_digest,
        path_identity=path_identity,
        calibration=calibration,
        status=status,
        reason=reason,
        complete_raw_window_count=complete_raw,
        evaluated_pair_count=len(evaluated),
        missing_or_insufficient_window_count=insufficient,
        counts=counts,
        associated_reference_positive_count=associated,
        recovery=recovery,
        reference_qam_positive_count=reference_qam,
        native_qam_recovery_count=native_qam_recovery,
        mean_qam_accuracy_difference=mean_qam_difference,
        qam_accuracy_difference_lower_bound=qam_lower_bound,
        qam_interval_method=config.qam_interval_method,
        qam_noninferiority_passed=qam_passed,
        maximum_working_set_bytes=maximum_working_set,
        windows=ordered,
    )


def evaluate_acceptance_campaign(
    *,
    artifact_id: str,
    config: MatchedPilotAcceptanceCampaignConfigV1,
    streams: tuple[AcceptanceCampaignStreamV1, ...],
) -> MatchedPilotAcceptanceCampaignReceiptV1:
    """Aggregate the predeclared 30-session campaign without dropping a stratum."""

    config = MatchedPilotAcceptanceCampaignConfigV1.model_validate(config.model_dump(mode="json"))
    if len(streams) > 40:
        raise ValueError("campaign contains more than the predeclared 40 streams")
    strata_by_id = {item.stratum_id: item for item in config.strata}
    if any(item.stratum_id not in strata_by_id for item in streams):
        raise ValueError("campaign stream references an undeclared stratum")
    if len({item.receipt.config.config_digest for item in streams}) > 1:
        raise ValueError("campaign streams use different per-stream acceptance configs")
    if any(item.receipt.config.detector_binding != config.detector_binding for item in streams):
        raise ValueError("campaign stream detector binding differs from predeclaration")
    expected_inventory = {
        (item.session_id, item.stream_id): item for item in config.capture_inventory
    }
    if any((item.session_id, item.stream_id) not in expected_inventory for item in streams):
        raise ValueError("analysis stream is absent from accepted capture inventory")

    algorithm_sets = {
        source: {
            (decision.algorithm_id, decision.algorithm_version)
            for item in streams
            for window in item.receipt.windows
            for decision in (
                (window.reference,) if source == "legacy_reference" else (window.native,)
            )
            if decision.status is PilotDecisionStatus.EVALUATED
        }
        for source in ("legacy_reference", "native")
    }
    if any(len(values) > 1 for values in algorithm_sets.values()):
        raise ValueError("campaign contains heterogeneous detector algorithm revisions")
    expected_algorithms = {
        "legacy_reference": {
            (
                "leo-tracker-pilot-symbolwise-v3-single-rx",
                "0bb80d14759fd8496b74e7d3219a690be18565a6",
            )
        },
        "native": {("native-symbolwise-known-pilot", "1.0.0")},
    }
    if any(
        values and values != expected_algorithms[source]
        for source, values in algorithm_sets.items()
    ):
        raise ValueError("campaign detector algorithm identity differs from frozen v1")

    paired_groups: dict[str, list[AcceptanceCampaignStreamV1]] = {}
    independent_session_ids: set[str] = set()
    for item in streams:
        stratum = strata_by_id[item.stratum_id]
        identity = item.receipt.path_identity
        inventory = expected_inventory[(item.session_id, item.stream_id)]
        if (
            item.pipeline_run_id != item.receipt.analysis_run_id
            or item.pipeline_release != item.receipt.pipeline_release
            or item.production_source_revision != item.receipt.production_source_revision
            or not item.analysis_product_uri
        ):
            raise ValueError("analysis product/run binding disagrees with stream receipt")
        expected_identity = (
            stratum.radio_id,
            stratum.radio_serial,
            stratum.receiver_id,
            stratum.physical_receiver_id,
        )
        actual_identity = (
            identity.radio_id,
            identity.radio_serial,
            identity.receiver_id,
            identity.physical_receiver_id,
        )
        if actual_identity != expected_identity:
            raise ValueError("campaign stream receipt does not match its declared stratum")
        if (
            identity.manifest_digest != inventory.manifest_digest
            or identity.profile_revision_digest != inventory.profile_revision_digest
            or identity.capture_utc_ns != inventory.dwell_start_utc_ns
            or identity.capture_end_utc_ns != inventory.dwell_end_utc_ns
            or identity.hardware_epoch_id != inventory.hardware_epoch_id
            or item.pairing_group_id != inventory.pairing_group_id
        ):
            raise ValueError("analysis stream is not exactly bound to accepted capture evidence")
        if stratum.role is AcceptanceStreamRole.INDEPENDENT:
            if item.pairing_group_id is not None:
                raise ValueError("independent stream cannot declare a pairing group")
            if item.session_id in independent_session_ids:
                raise ValueError("independent campaign session IDs must be globally distinct")
            independent_session_ids.add(item.session_id)
        else:
            if item.pairing_group_id is None:
                raise ValueError("paired stream requires a pairing group")
            paired_groups.setdefault(item.pairing_group_id, []).append(item)

    paired_strata = {
        item.stratum_id for item in config.strata if item.role is AcceptanceStreamRole.PAIRED
    }
    for group in paired_groups.values():
        if len(group) != 2 or {item.stratum_id for item in group} != paired_strata:
            raise ValueError("each pairing group must contain exactly one stream per radio")
        if len({item.session_id for item in group}) != 1:
            raise ValueError("both streams in a pairing group must share one session ID")
    paired_session_ids = {group[0].session_id for group in paired_groups.values()}
    if len(paired_session_ids) != len(paired_groups):
        raise ValueError("paired campaign session IDs must be unique between groups")
    if independent_session_ids & paired_session_ids:
        raise ValueError("independent and paired campaign session IDs must be distinct")
    if len(paired_groups) > config.paired_session_count:
        raise ValueError("campaign contains too many paired sessions")

    results: list[AcceptanceCampaignStratumResultV1] = []
    for stratum in config.strata:
        selected = tuple(item for item in streams if item.stratum_id == stratum.stratum_id)
        if len(selected) > stratum.required_session_count:
            raise ValueError("campaign stratum contains too many sessions")
        if len({item.session_id for item in selected}) != len(selected):
            raise ValueError("campaign stratum repeats a session")
        results.append(_aggregate_campaign_stratum(stratum.stratum_id, selected, stratum))

    statuses = {item.status for item in results}
    if MatchedAcceptanceStatus.INCONCLUSIVE in statuses:
        status = MatchedAcceptanceStatus.INCONCLUSIVE
        reason = "campaign lacks the predeclared sessions or reference-positive evidence"
    elif MatchedAcceptanceStatus.FAIL in statuses:
        status = MatchedAcceptanceStatus.FAIL
        reason = "one or more predeclared campaign strata failed a frozen gate"
    else:
        status = MatchedAcceptanceStatus.PASS
        reason = "all predeclared campaign strata passed the frozen aggregate gates"
    ordered_streams = tuple(
        sorted(streams, key=lambda item: (item.stratum_id, item.session_id, item.stream_id))
    )
    return MatchedPilotAcceptanceCampaignReceiptV1(
        artifact_id=artifact_id,
        config=config,
        status=status,
        reason=reason,
        observed_stream_count=len(streams),
        observed_paired_session_count=len(paired_groups),
        streams=ordered_streams,
        strata=tuple(results),
    )


def publish_acceptance_campaign(
    outputs: OutputSink,
    receipt: MatchedPilotAcceptanceCampaignReceiptV1,
) -> PublishedProduct:
    """Publish a completed campaign receipt through the normal artifact sink."""

    return outputs.publish_json(
        MATCHED_ACCEPTANCE_CAMPAIGN_PRODUCT,
        receipt.model_dump(mode="json"),
    )


def _aggregate_campaign_stratum(
    stratum_id: str,
    streams: tuple[AcceptanceCampaignStreamV1, ...],
    declaration: AcceptanceCampaignStratumV1,
) -> AcceptanceCampaignStratumResultV1:
    required_sessions = declaration.required_session_count
    minimum_positives = declaration.minimum_reference_positive_count
    reference_positive = sum(item.receipt.recovery.trials for item in streams)
    associated = sum(item.receipt.associated_reference_positive_count for item in streams)
    recovery = binomial_lower_bounds(associated, reference_positive, alpha=0.05)
    qam_windows = tuple(
        window
        for item in streams
        for window in item.receipt.windows
        if window.reference_qam_positive
    )
    qam_differences = tuple(
        window.qam_accuracy_difference
        for window in qam_windows
        if window.qam_accuracy_difference is not None
    )
    mean_difference = sum(qam_differences) / len(qam_differences) if qam_differences else None
    lower_bound = paired_student_t_lower_bound(qam_differences, alpha=0.05)
    per_stream_config = streams[0].receipt.config if streams else None
    incomplete = any(
        item.receipt.status is MatchedAcceptanceStatus.INSUFFICIENT for item in streams
    )
    if len(streams) < required_sessions or reference_positive < minimum_positives or incomplete:
        status = MatchedAcceptanceStatus.INCONCLUSIVE
        reason = "stratum requires 10 complete sessions and at least 30 reference positives"
        qam_passed = None
    elif len(qam_differences) < 2:
        status = MatchedAcceptanceStatus.INCONCLUSIVE
        reason = "stratum requires at least two paired QAM-positive differences"
        qam_passed = None
    else:
        assert per_stream_config is not None
        native_qam = sum(item.receipt.native_qam_recovery_count for item in streams)
        reference_qam = len(qam_windows)
        qam_passed = bool(
            reference_qam >= per_stream_config.minimum_reference_qam_positive_count
            and native_qam == reference_qam
            and lower_bound is not None
            and lower_bound >= -per_stream_config.qam_accuracy_noninferiority_margin
        )
        recovery_passed = bool(
            recovery.point_estimate is not None
            and recovery.point_estimate >= per_stream_config.minimum_recovery_fraction
            and recovery.wilson_one_sided_lower is not None
            and recovery.wilson_one_sided_lower >= per_stream_config.minimum_wilson_lower_bound
            and recovery.clopper_pearson_one_sided_lower is not None
            and recovery.clopper_pearson_one_sided_lower
            >= per_stream_config.minimum_exact_lower_bound
        )
        status = (
            MatchedAcceptanceStatus.PASS
            if recovery_passed and qam_passed
            else MatchedAcceptanceStatus.FAIL
        )
        reason = "aggregate candidate-recovery and paired-QAM gates evaluated"
    return AcceptanceCampaignStratumResultV1(
        stratum_id=stratum_id,
        observed_session_count=len(streams),
        reference_positive_count=reference_positive,
        associated_reference_positive_count=associated,
        recovery=recovery,
        reference_qam_positive_count=len(qam_windows),
        mean_qam_accuracy_difference=mean_difference,
        qam_accuracy_difference_lower_bound=lower_bound,
        qam_interval_method="paired-student-t-one-sided-95",
        qam_noninferiority_passed=qam_passed,
        status=status,
        reason=reason,
    )


def binomial_lower_bounds(successes: int, trials: int, *, alpha: float) -> BinomialLowerBoundsV1:
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError("binomial counts are invalid")
    if not 0 < alpha < 0.5:
        raise ValueError("alpha must lie between zero and one half")
    if trials == 0:
        return BinomialLowerBoundsV1(
            successes=0,
            trials=0,
            point_estimate=None,
            confidence_level=1 - alpha,
            wilson_one_sided_lower=None,
            clopper_pearson_one_sided_lower=None,
        )
    point = successes / trials
    z = NormalDist().inv_cdf(1 - alpha)
    denominator = 1 + z * z / trials
    center = point + z * z / (2 * trials)
    radius = z * math.sqrt(point * (1 - point) / trials + z * z / (4 * trials**2))
    wilson = max(0.0, (center - radius) / denominator)
    exact = _clopper_pearson_lower(successes, trials, alpha)
    return BinomialLowerBoundsV1(
        successes=successes,
        trials=trials,
        point_estimate=point,
        confidence_level=1 - alpha,
        wilson_one_sided_lower=wilson,
        clopper_pearson_one_sided_lower=exact,
    )


def paired_student_t_lower_bound(values: tuple[float, ...], *, alpha: float) -> float | None:
    """One-sided 95% paired-t lower bound with conservative tabulated criticals."""

    if alpha != 0.05:
        raise ValueError("published v1 paired-t interval requires alpha=0.05")
    if len(values) < 2:
        return None
    if any(not math.isfinite(value) or value < -1 or value > 1 for value in values):
        raise ValueError("paired QAM accuracy differences must be finite and lie in [-1, 1]")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    standard_error = math.sqrt(variance / len(values))
    return mean - _one_sided_t95_critical(len(values) - 1) * standard_error


def _one_sided_t95_critical(degrees_of_freedom: int) -> float:
    if degrees_of_freedom <= 0:
        raise ValueError("paired-t interval requires positive degrees of freedom")
    low = 0.0
    high = 8.0
    for _ in range(80):
        midpoint = (low + high) / 2
        if _student_t_cdf(midpoint, degrees_of_freedom) < 0.95:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    if value == 0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    tail = 0.5 * _regularized_incomplete_beta(
        x,
        degrees_of_freedom / 2,
        0.5,
    )
    return 1 - tail if value > 0 else tail


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1) / (a + b + 2):
        return front * _beta_continued_fraction(x, a, b) / a
    return 1 - front * _beta_continued_fraction(1 - x, b, a) / b


def _beta_continued_fraction(x: float, a: float, b: float) -> float:
    tiny = 1e-300
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1 - qab * x / qap
    d = 1 / max(abs(d), tiny) * (1 if d >= 0 else -1)
    result = d
    for iteration in range(1, 201):
        m2 = 2 * iteration
        numerator = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1 + numerator * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + numerator / c
        c = c if abs(c) > tiny else tiny
        result *= d * c
        numerator = -(a + iteration) * (qab + iteration) * x / ((a + m2) * (qap + m2))
        d = 1 + numerator * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + numerator / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        result *= delta
        if abs(delta - 1) < 3e-14:
            return result
    raise ArithmeticError("incomplete-beta continued fraction did not converge")


def _clopper_pearson_lower(successes: int, trials: int, alpha: float) -> float:
    if successes == 0:
        return 0.0
    low = 0.0
    high = successes / trials
    for _ in range(80):
        midpoint = (low + high) / 2
        if _binomial_tail(successes, trials, midpoint) < alpha:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def _binomial_tail(successes: int, trials: int, probability: float) -> float:
    if probability <= 0:
        return 0.0
    if probability >= 1:
        return 1.0
    log_term = (
        math.lgamma(trials + 1)
        - math.lgamma(successes + 1)
        - math.lgamma(trials - successes + 1)
        + successes * math.log(probability)
        + (trials - successes) * math.log1p(-probability)
    )
    term = math.exp(log_term)
    total = term
    odds = probability / (1 - probability)
    for value in range(successes, trials):
        term *= (trials - value) / (value + 1) * odds
        total += term
        if term <= total * 1e-16:
            break
    return min(1.0, total)


def _preflight_reason(
    iq: IqReader,
    identity: ReceiverPathIdentityV1,
    calibration: ReceiverFrequencyCalibrationV1 | None,
    config: MatchedPilotAcceptanceConfigV1,
) -> str | None:
    if iq.sample_rate_hz != config.sample_rate_hz:
        return f"sample rate must be exactly {config.sample_rate_hz} Hz"
    if iq.sample_count != config.dwell_sample_count:
        return f"dwell must contain exactly {config.dwell_sample_count} samples"
    if identity.receiver_id not in iq.receiver_ids:
        return "bound physical receiver is absent from IQ stream"
    if calibration is None:
        return "immutable receiver-frequency calibration is absent"
    if not calibration.matches(identity):
        return "receiver-frequency calibration does not cover the full dwell/hardware epoch"
    if not calibration_search_domain_covers(calibration, config):
        return "calibration prior plus Doppler guard exceeds frozen residual search domain"
    return None


def _scheduled_windows(
    iq: IqReader,
    receiver_id: int,
    config: MatchedPilotAcceptanceConfigV1,
):
    channel = iq.receiver_ids.index(receiver_id)
    active: dict[int, tuple[npt.NDArray[np.complex64], npt.NDArray[np.bool_]]] = {}
    next_index = 0
    for block in validated_blocks(iq, block_samples=config.block_sample_count):
        block_start = block.metadata.session_sample_start
        block_stop = block_start + block.metadata.sample_count
        for index, (values, present) in tuple(active.items()):
            start = index * config.interval_sample_count
            if start + config.window_sample_count <= block_start:
                active.pop(index)
                values.setflags(write=False)
                buffered = block.samples.nbytes + values.nbytes + present.nbytes
                complete = bool(np.all(present))
                yield index, start, values if complete else None, complete, buffered
        while next_index < config.scheduled_window_count and (
            next_index * config.interval_sample_count + config.window_sample_count <= block_start
        ):
            start = next_index * config.interval_sample_count
            yield next_index, start, None, False, block.samples.nbytes
            next_index += 1
        while (
            next_index < config.scheduled_window_count
            and next_index * config.interval_sample_count < block_stop
        ):
            active[next_index] = (
                np.zeros(config.window_sample_count, dtype=np.complex64),
                np.zeros(config.window_sample_count, dtype=np.bool_),
            )
            next_index += 1
        for index, (buffer, coverage) in tuple(active.items()):
            start = index * config.interval_sample_count
            stop = start + config.window_sample_count
            overlap_start = max(start, block_start)
            overlap_stop = min(stop, block_stop)
            if overlap_start < overlap_stop:
                source_start = overlap_start - block_start
                source_stop = overlap_stop - block_start
                target_start = overlap_start - start
                target_stop = overlap_stop - start
                iq_values = block.samples[source_start:source_stop, channel]
                buffer[target_start:target_stop] = (
                    iq_values[:, 0].astype(np.float32) + 1j * iq_values[:, 1].astype(np.float32)
                ) / np.float32(32_768)
                coverage[target_start:target_stop] = True
            if stop <= block_stop:
                values, present = active.pop(index)
                values.setflags(write=False)
                buffered = (
                    block.samples.nbytes
                    + sum(candidate.nbytes + mask.nbytes for candidate, mask in active.values())
                    + values.nbytes
                    + present.nbytes
                )
                complete = bool(np.all(present))
                yield index, start, values if complete else None, complete, buffered
    for index, (values, present) in sorted(active.items()):
        start = index * config.interval_sample_count
        values.setflags(write=False)
        buffered = sum(candidate.nbytes + mask.nbytes for candidate, mask in active.values())
        complete = bool(np.all(present))
        yield index, start, values if complete else None, complete, buffered
    while next_index < config.scheduled_window_count:
        start = next_index * config.interval_sample_count
        yield next_index, start, None, False, 0
        next_index += 1


def _safe_decision(
    port: PilotWindowDecisionPort,
    *,
    expected_source: str,
    window_index: int,
    sample_start: int,
    samples: npt.NDArray[np.complex64],
    sample_rate_hz: int,
    calibration: ReceiverFrequencyCalibrationV1,
) -> PilotWindowDecisionV1:
    expected_iq_digest = _window_iq_digest(samples)
    try:
        result = port.evaluate(
            window_index=window_index,
            sample_start=sample_start,
            samples=samples,
            sample_rate_hz=sample_rate_hz,
            calibration=calibration,
        )
        if (
            result.source != expected_source
            or result.window_index != window_index
            or result.sample_start != sample_start
            or result.window_iq_digest != expected_iq_digest
        ):
            raise ValueError("decision port returned mismatched source, identity, or IQ digest")
        return result
    except Exception as exc:  # scientific input failure, retained as insufficient evidence
        return _insufficient_decision(
            expected_source,
            window_index,
            sample_start,
            f"decision port failed: {type(exc).__name__}: {exc}",
        )


def _match_window(
    index: int,
    start: int,
    reference: PilotWindowDecisionV1,
    native: PilotWindowDecisionV1,
    config: MatchedPilotAcceptanceConfigV1,
) -> MatchedPilotWindowV1:
    epoch_error: int | None = None
    cfo_error: float | None = None
    associated = False
    if reference.candidate is True and native.candidate is True:
        assert reference.epoch_sample is not None and native.epoch_sample is not None
        assert reference.cfo_hz is not None and native.cfo_hz is not None
        period = round(config.sample_rate_hz / 750)
        raw_epoch_error = abs(reference.epoch_sample - native.epoch_sample) % period
        epoch_error = min(raw_epoch_error, period - raw_epoch_error)
        cfo_error = abs(reference.cfo_hz - native.cfo_hz)
        associated = (
            epoch_error <= config.epoch_tolerance_samples and cfo_error <= config.cfo_tolerance_hz
        )
    reference_qam = _qam_positive(reference, config)
    native_qam = _qam_positive(native, config)
    difference = (
        native.qam_accuracy - reference.qam_accuracy
        if associated and reference.qam_accuracy is not None and native.qam_accuracy is not None
        else None
    )
    return MatchedPilotWindowV1(
        window_index=index,
        sample_start=start,
        raw_window_complete=True,
        reference=reference,
        native=native,
        candidate_associated=associated,
        circular_epoch_error_samples=epoch_error,
        absolute_cfo_error_hz=cfo_error,
        reference_qam_positive=reference_qam,
        native_qam_positive=native_qam,
        qam_accuracy_difference=difference,
    )


def _qam_positive(
    decision: PilotWindowDecisionV1,
    config: MatchedPilotAcceptanceConfigV1,
) -> bool:
    return bool(
        decision.candidate is True
        and decision.qam_accuracy is not None
        and decision.qam_evm is not None
        and decision.qam_accuracy >= config.minimum_qam_accuracy
        and decision.qam_evm <= config.maximum_qam_evm
    )


def _missing_window(index: int, start: int, reason: str) -> MatchedPilotWindowV1:
    return MatchedPilotWindowV1(
        window_index=index,
        sample_start=start,
        raw_window_complete=False,
        reference=_insufficient_decision("legacy_reference", index, start, reason),
        native=_insufficient_decision("native", index, start, reason),
        candidate_associated=False,
        reference_qam_positive=False,
        native_qam_positive=False,
    )


def _insufficient_decision(
    source: str,
    index: int,
    start: int,
    reason: str,
) -> PilotWindowDecisionV1:
    normalized_source: Literal["legacy_reference", "native"] = (
        "legacy_reference" if source == "legacy_reference" else "native"
    )
    return PilotWindowDecisionV1.create(
        source=normalized_source,
        algorithm_id="unavailable-window-decision",
        algorithm_version="1.0.0",
        window_iq_digest=None,
        window_index=index,
        sample_start=start,
        status=PilotDecisionStatus.INSUFFICIENT,
        candidate=None,
        reason=reason,
    )


def _candidate_counts(windows: tuple[MatchedPilotWindowV1, ...]) -> MatchedCandidateCountsV1:
    n11 = sum(
        item.reference.candidate is True and item.native.candidate is True for item in windows
    )
    n10 = sum(
        item.reference.candidate is True and item.native.candidate is False for item in windows
    )
    n01 = sum(
        item.reference.candidate is False and item.native.candidate is True for item in windows
    )
    n00 = sum(
        item.reference.candidate is False and item.native.candidate is False for item in windows
    )
    return MatchedCandidateCountsV1(n11=n11, n10=n10, n01=n01, n00=n00)


def _window_iq_digest(samples: npt.NDArray[np.complex64]) -> str:
    canonical = np.ascontiguousarray(samples, dtype="<c8")
    return sha256_digest(canonical.tobytes(order="C"))


def _acceptance_status(
    *,
    preflight_reason: str | None,
    complete_raw: int,
    insufficient: int,
    recovery: BinomialLowerBoundsV1,
    reference_qam: int,
    qam_passed: bool | None,
    config: MatchedPilotAcceptanceConfigV1,
) -> tuple[MatchedAcceptanceStatus, str]:
    if preflight_reason is not None:
        return (
            MatchedAcceptanceStatus.INSUFFICIENT,
            "the fixed 600-window denominator has missing or insufficient evidence",
        )
    if complete_raw != config.scheduled_window_count or insufficient:
        return (
            MatchedAcceptanceStatus.INSUFFICIENT,
            "the fixed 600-window denominator has missing or insufficient evidence",
        )
    if recovery.trials < config.minimum_reference_positive_count:
        return (
            MatchedAcceptanceStatus.INCONCLUSIVE,
            "too few legacy-reference positive windows for candidate-recovery inference",
        )
    if reference_qam < config.minimum_reference_qam_positive_count:
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
        and qam_passed is True
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
