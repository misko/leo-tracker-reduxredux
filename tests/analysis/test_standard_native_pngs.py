from __future__ import annotations

from typing import Any

import pytest

from leo.analysis.standard.native_accounting import _accounting_from_sealed_replay
from leo.analysis.standard.native_analyzers import (
    PathStandardNativeEvidenceAnalyzer,
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.analysis.standard.native_products import (
    PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
    STANDARD_NATIVE_PNG_PRODUCTS,
)
from leo.analysis.standard.native_stateful import StandardNativeStatefulRunner
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native_accounting import (
    StandardNativeTrajectoryConditionedAccountingV4,
)
from leo.contracts.standard_native_stateful import (
    NativeConditionedHoughReplayRowV1,
    NativePilotCandidateV1,
    NativePilotMethodScoreV1,
    NativePilotProbeDetectionV1,
    NativePolynomialTrajectoryV1,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV5
from leo.contracts.trajectory_accounting import TrajectoryAccountingConfigV2
from leo.pipeline import AnalysisContext, ScopeIdentityV1, StageOutcome, UpstreamJsonProduct
from tests.analysis.test_standard_native_observability import (
    _fast_glrt_runner,
    _inventory,
    _OutputSink,
    _Reader,
    _SubjectProducts,
)
from tests.contracts.test_standard_path_input_bind_v4 import _values


def _no_result_probe(item: Any, config: Any, edge: Any) -> PilotProbeDetection:
    del config, edge
    return PilotProbeDetection(
        NumericalStatus.NO_RESULT,
        item.segment_local_sample_start,
        item.segment_local_sample_start / item.iq.sample_rate_hz,
        None,
        None,
        (),
        None,
        None,
        "native PNG projection fixture",
    )


def test_native_path_projection_publishes_accounting_and_all_twelve_pngs() -> None:
    inventory = _inventory()
    values = _values(2_500_000)
    values.update(
        schema_version=5,
        algorithm_version="standard-path-input-bind-v5",
        observed_sample_count=2_500_000 - 10_000,
        missing_sample_count=10_000,
        timeline_sha256=inventory.timeline_sha256,
        gap_map_content_digest=inventory.gap_map_content_digest,
        validity_inventory_sha256=inventory.inventory_digest,
        validity_inventory=inventory.model_dump(mode="json"),
    )
    binding = StandardPathInputBindV5.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
    scope = ScopeIdentityV1.receiver_path(
        session_id=binding.session_id,
        stream_id=binding.stream_id,
        receiver_id=binding.receiver_id,
    )
    configuration = production_standard_native_evidence_configuration()
    science_outputs = _OutputSink()
    science = PathStandardNativeEvidenceAnalyzer(
        stateful_runner_factory=lambda config: StandardNativeStatefulRunner(
            config,
            probe_detector=_no_result_probe,
        ),
        full_capture_glrt_runner_factory=_fast_glrt_runner,
    )
    science_result = science.analyze(  # type: ignore[arg-type]
        AnalysisContext(
            session_id=binding.session_id,
            run_id="native-png-science",
            pipeline_release="1" * 40,
            scope_key="path",
            scope=scope,
            stage_config=configuration["path-standard-native"],
        ),
        _Reader(binding.validity_inventory),
        _SubjectProducts(binding),
        science_outputs,
    )
    assert science_result.outcome is StageOutcome.PARTIAL_COVERAGE

    upstream = {
        product.kind: UpstreamJsonProduct(
            producer_node_id="path-node",
            producer_scope=scope,
            outcome=science_result.outcome,
            product_digest=canonical_digest(
                science_outputs.documents[(product.kind, product.schema_version)]
            ),
            document=science_outputs.documents[(product.kind, product.schema_version)],
        )
        for product in production_standard_native_evidence_registry()
        .get("path-standard-native")
        .spec.output_products
    }

    class _Products:
        def read_json_many(self, requirement: Any, *, producer_node_ids: tuple[str, ...]):
            assert producer_node_ids == ("path-node",)
            return (upstream[requirement.kind],)

    projection_outputs = _OutputSink()
    result = (
        production_standard_native_evidence_registry()
        .get("path-alternate-tracks-native")
        .analyze(  # type: ignore[arg-type]
            AnalysisContext(
                session_id=binding.session_id,
                run_id="native-png-projection",
                pipeline_release="1" * 40,
                scope_key="path",
                scope=scope,
                dependency_node_ids=("path-node",),
                stage_config=configuration["path-alternate-tracks-native"],
            ),
            object(),
            _Products(),
            projection_outputs,
        )
    )

    assert result.outcome is StageOutcome.PARTIAL_COVERAGE
    assert len(result.products) == len(PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS) == 14
    accounting = StandardNativeTrajectoryConditionedAccountingV4.model_validate(
        projection_outputs.documents[("standard.trajectory-conditioned-accounting", 4)]
    )
    assert accounting.source.path_input_binding_digest == binding.binding_digest
    assert accounting.cross_segment_association_permitted is False
    assert len(projection_outputs.payloads) == 12
    assert set(STANDARD_NATIVE_PNG_PRODUCTS) <= {
        product for product in PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS
    }
    assert all(
        payload.startswith(b"\x89PNG\r\n\x1a\n") for payload in projection_outputs.payloads.values()
    )

    repeated_outputs = _OutputSink()
    repeated_result = (
        production_standard_native_evidence_registry()
        .get("path-alternate-tracks-native")
        .analyze(  # type: ignore[arg-type]
            AnalysisContext(
                session_id=binding.session_id,
                run_id="native-png-projection-repeat",
                pipeline_release="1" * 40,
                scope_key="path",
                scope=scope,
                dependency_node_ids=("path-node",),
                stage_config=configuration["path-alternate-tracks-native"],
            ),
            object(),
            _Products(),
            repeated_outputs,
        )
    )
    assert repeated_result.outcome is result.outcome
    assert repeated_outputs.documents == projection_outputs.documents
    assert repeated_outputs.payloads == projection_outputs.payloads


def test_native_accounting_uses_sealed_conditioned_presence_as_association_authority() -> None:
    trajectory_id = canonical_digest({"trajectory": 1})
    observation_id = canonical_digest({"observation": 1})
    trajectory = NativePolynomialTrajectoryV1(
        trajectory_id=trajectory_id,
        method="glrt64",
        polynomial_degree=1,
        reference_time_s=0.0,
        coefficients_hz=(0.0, 39_900.0),
        start_s=0.0,
        end_s=1.0,
        observation_ids=(observation_id,),
        point_count=1,
        residual_rms_hz=0.0,
        bic=0.0,
        high_gate=0.0,
        em_iterations=0,
    )

    def score(margin: float) -> NativePilotMethodScoreV1:
        return NativePilotMethodScoreV1(
            method="glrt64",
            exact_score=margin + 0.1,
            control_score=0.1,
            margin=margin,
            residual_cfo_hz=40_000.0,
            tracking_cfo_hz=40_000.0,
        )

    def detection(sample_start: int) -> NativePilotProbeDetectionV1:
        candidate = NativePilotCandidateV1(
            rank=0,
            local_epoch_sample=4,
            acquired_cfo_hz=40_000.0,
            scores=(score(0.1),),
        )
        return NativePilotProbeDetectionV1(
            status="complete",
            sample_start=sample_start,
            time_s=sample_start / 2_500_000,
            local_epoch_sample=4,
            acquired_cfo_hz=40_000.0,
            scores=(score(0.1),),
            reason="sealed association fixture",
            source_candidate_count=1,
            candidates=(candidate,),
        )

    def replay(
        sample_start: int,
        *,
        conditioned: bool,
    ) -> NativeConditionedHoughReplayRowV1:
        conditioned_values = (
            {
                "conditioned_corrected_margin": 0.15,
                "conditioned_tracking_cfo_hz": 10.0,
                "conditioned_epoch_sample": 4,
                "conditioned_seed_cfo_hz": 100.0,
            }
            if conditioned
            else {}
        )
        return NativeConditionedHoughReplayRowV1(
            family_id=canonical_digest({"family": 1}),
            trajectory_id=trajectory_id,
            trajectory_method="glrt64",
            polynomial_degree=1,
            sample_start=sample_start,
            time_s=sample_start / 2_500_000,
            detector_method="glrt64",
            baseline_margin=0.1,
            corrected_margin=0.2 if conditioned else 0.06,
            margin_delta=0.1 if conditioned else -0.04,
            corrected_residual_cfo_hz=10.0,
            **conditioned_values,
        )

    config = TrajectoryAccountingConfigV2()
    accounting = _accounting_from_sealed_replay(
        (detection(0), detection(25_000)),
        (trajectory,),
        (replay(0, conditioned=True), replay(25_000, conditioned=False)),
        pilot_scan_digest=canonical_digest({"pilot": 1}),
        trajectory_bank_digest=canonical_digest({"bank": 1}),
        trajectory_feedback_digest=canonical_digest({"feedback": 1}),
        alias_spacing_hz=250_000.0,
        config=config,
    )

    assert accounting.evaluation_count == 2
    assert accounting.associated_evaluation_count == 1
    assert accounting.unassociated_evaluation_count == 1
    assert accounting.evaluations[0].baseline_association_error_hz == 100.0
    assert accounting.evaluations[1].baseline_margin is None
    assert accounting.trajectories[0].unassociated_reacquired_positive_count == 1
    assert accounting.reacquired_associated_transitions.positive_to_positive == 1
    assert accounting.conditioned_associated_transitions.positive_to_positive == 1
    assert accounting.conditioned_unique_probe_transitions.positive_to_negative == 1

    invalid = replay(0, conditioned=True).model_copy(update={"conditioned_epoch_sample": 99})
    with pytest.raises(ValueError, match="does not name one persisted GLRT64 candidate"):
        _accounting_from_sealed_replay(
            (detection(0),),
            (trajectory,),
            (invalid,),
            pilot_scan_digest=canonical_digest({"pilot": 1}),
            trajectory_bank_digest=canonical_digest({"bank": 1}),
            trajectory_feedback_digest=canonical_digest({"feedback": 1}),
            alias_spacing_hz=250_000.0,
            config=config,
        )
