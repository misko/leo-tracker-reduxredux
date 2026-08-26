from __future__ import annotations

from typing import Any

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
    StandardNativeTrajectoryConditionedAccountingV3,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV4
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


def test_native_path_projection_publishes_accounting_and_all_eleven_pngs() -> None:
    inventory = _inventory()
    values = _values(2_500_000)
    values.update(
        observed_sample_count=2_500_000 - 10_000,
        missing_sample_count=10_000,
        timeline_sha256=inventory.timeline_sha256,
        gap_map_content_digest=inventory.gap_map_content_digest,
        validity_inventory_sha256=inventory.inventory_digest,
        validity_inventory=inventory.model_dump(mode="json"),
    )
    binding = StandardPathInputBindV4.model_validate(
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
    assert len(result.products) == len(PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS) == 13
    accounting = StandardNativeTrajectoryConditionedAccountingV3.model_validate(
        projection_outputs.documents[("standard.trajectory-conditioned-accounting", 3)]
    )
    assert accounting.source.path_input_binding_digest == binding.binding_digest
    assert accounting.cross_segment_association_permitted is False
    assert len(projection_outputs.payloads) == 11
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
