"""Research product namespace around the shared Standard scientific implementation."""

from __future__ import annotations

from copy import deepcopy
from typing import cast

from pydantic import JsonValue

from leo.analysis.research.rate_baseline import RateContinuityBaselineAnalyzer
from leo.analysis.standard.alternate_tracks import default_alternate_cfo_config
from leo.analysis.standard.analyzers import (
    RankedPathAlternateTracksAnalyzer,
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.contracts.alternate_cfo_tracks import RankedCandidateResidualHoughConfigV3
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.research_pipeline import (
    ResearchProductEnvelopeV1,
    ResearchSourceBindingEnvelopeV1,
)
from leo.contracts.standard_pipeline import StandardSourceBindingV1
from leo.pipeline import (
    AnalysisContext,
    Analyzer,
    AnalyzerRegistry,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    StageResult,
    StageSpec,
    UpstreamJsonProduct,
    rate_analysis_configuration_v1,
)

_STANDARD_MEMBERSHIP_KEY = "standard_source_bindings"
_RESEARCH_MEMBERSHIP_KEY = "research_source_bindings"


def research_product_kind(standard_kind: str) -> str:
    if standard_kind.startswith("standard."):
        return "research." + standard_kind.removeprefix("standard.")
    return "research." + standard_kind


def _standard_product_kind(research_kind: str) -> str:
    if not research_kind.startswith("research."):
        raise ValueError("Research product kind lacks its lane namespace")
    remainder = research_kind.removeprefix("research.")
    if remainder in {"quality.summary"}:
        return remainder
    return "standard." + remainder


def _research_spec(product: ProductSpec) -> ProductSpec:
    return ProductSpec(
        kind=research_product_kind(product.kind),
        schema_version=1 if product.media_type == "application/json" else product.schema_version,
        role=product.role,
        media_type=product.media_type,
    )


def _research_requirement(requirement: ProductRequirement) -> ProductRequirement:
    return requirement.model_copy(
        update={
            "kind": research_product_kind(requirement.kind),
            "accepted_schema_versions": (1,),
        }
    )


class _ResearchOutputSink:
    def __init__(self, target: OutputSink, definition_id: Sha256Digest) -> None:
        self._target = target
        self._definition_id = definition_id

    def publish_json(
        self, product: ProductSpec, document: dict[str, JsonValue]
    ) -> PublishedProduct:
        envelope_values = {
            "pipeline_definition_id": self._definition_id,
            "payload_kind": product.kind,
            "payload_schema_version": product.schema_version,
            "payload_content_digest": canonical_digest(document),
            "payload": document,
        }
        envelope_values["content_digest"] = canonical_digest(
            {
                "schema_version": 1,
                "algorithm_version": "research-product-envelope-v1",
                "pipeline_lane": "research",
                **envelope_values,
            }
        )
        envelope = ResearchProductEnvelopeV1.model_validate(envelope_values)
        return self._target.publish_json(
            _research_spec(product),
            cast(dict[str, JsonValue], envelope.model_dump(mode="json")),
        )

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        return self._target.publish_bytes(_research_spec(product), payload)


class _ResearchProductReader:
    def __init__(self, target: ProductReader, definition_id: Sha256Digest) -> None:
        self._target = target
        self._definition_id = definition_id

    def read_subject_binding(self) -> dict[str, JsonValue]:
        return self._target.read_subject_binding()

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        value = self.read_json_bound(requirement)
        return None if value is None else value.document

    def read_json_bound(self, requirement: ProductRequirement) -> UpstreamJsonProduct | None:
        value = self._target.read_json_bound(_research_requirement(requirement))
        return None if value is None else self._unwrap(value, requirement)

    def read_json_many(
        self,
        requirement: ProductRequirement,
        *,
        producer_node_ids: tuple[str, ...],
    ) -> tuple[UpstreamJsonProduct, ...]:
        values = self._target.read_json_many(
            _research_requirement(requirement),
            producer_node_ids=producer_node_ids,
        )
        return tuple(self._unwrap(value, requirement) for value in values)

    def _unwrap(
        self,
        value: UpstreamJsonProduct,
        requirement: ProductRequirement,
    ) -> UpstreamJsonProduct:
        envelope = ResearchProductEnvelopeV1.model_validate(value.document)
        if (
            envelope.pipeline_definition_id != self._definition_id
            or envelope.payload_kind != requirement.kind
            or envelope.payload_schema_version not in requirement.accepted_schema_versions
        ):
            raise ValueError("Research predecessor envelope disagrees with lane requirement")
        return value.model_copy(
            update={
                "product_digest": envelope.payload_content_digest,
                "document": cast(dict[str, JsonValue], envelope.payload),
                "membership": _unwrap_membership(
                    value.membership,
                    definition_id=self._definition_id,
                    research_product_kind_value=research_product_kind(requirement.kind),
                    payload_digest=envelope.payload_content_digest,
                ),
            }
        )


class _ResearchAnalyzer:
    def __init__(self, inner: Analyzer, definition_id: Sha256Digest) -> None:
        self._inner = inner
        self._definition_id = definition_id
        self.spec = StageSpec(
            key=inner.spec.key,
            algorithm_version="research-" + inner.spec.algorithm_version,
            configuration_schema="research." + inner.spec.configuration_schema,
            dependencies=inner.spec.dependencies,
            input_products=tuple(_research_requirement(item) for item in inner.spec.input_products),
            output_products=tuple(_research_spec(item) for item in inner.spec.output_products),
            resource_class=inner.spec.resource_class,
            deterministic=inner.spec.deterministic,
            accepted_outcomes=inner.spec.accepted_outcomes,
        )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        result = self._inner.analyze(
            context,
            iq,
            _ResearchProductReader(products, self._definition_id),
            _ResearchOutputSink(outputs, self._definition_id),
        )
        return result.model_copy(
            update={
                "summary": _wrap_membership(
                    result.summary,
                    definition_id=self._definition_id,
                )
            }
        )


def _wrap_membership(
    summary: dict[str, JsonValue], *, definition_id: Sha256Digest
) -> dict[str, JsonValue]:
    raw = summary.get(_STANDARD_MEMBERSHIP_KEY)
    if not isinstance(raw, dict):
        return summary
    wrapped = {}
    for wrapper_kind, document in raw.items():
        if not isinstance(wrapper_kind, str) or not isinstance(document, dict):
            raise ValueError("Standard source-binding summary is malformed")
        binding = StandardSourceBindingV1.model_validate(document)
        research_wrapper = research_product_kind(wrapper_kind)
        research_kind = research_product_kind(binding.product_kind)
        values = {
            "pipeline_definition_id": definition_id,
            "research_wrapper_kind": research_wrapper,
            "research_product_kind": research_kind,
            "research_payload_digest": binding.product_content_digest,
            "standard_binding": binding.model_dump(mode="json"),
        }
        values["content_digest"] = canonical_digest(
            {
                "schema_version": 1,
                "algorithm_version": "research-source-binding-envelope-v1",
                "pipeline_lane": "research",
                **values,
            }
        )
        envelope = ResearchSourceBindingEnvelopeV1.model_validate(values)
        wrapped[research_wrapper] = envelope.model_dump(mode="json")
    return cast(dict[str, JsonValue], {_RESEARCH_MEMBERSHIP_KEY: wrapped})


def _unwrap_membership(
    membership: dict[str, JsonValue],
    *,
    definition_id: Sha256Digest,
    research_product_kind_value: str,
    payload_digest: Sha256Digest,
) -> dict[str, JsonValue]:
    raw = membership.get(_RESEARCH_MEMBERSHIP_KEY)
    if not isinstance(raw, dict):
        return membership
    result = {}
    matching = 0
    for wrapper_kind, document in raw.items():
        if not isinstance(wrapper_kind, str) or not isinstance(document, dict):
            raise ValueError("Research source-binding summary is malformed")
        envelope = ResearchSourceBindingEnvelopeV1.model_validate(document)
        if envelope.pipeline_definition_id != definition_id:
            raise ValueError("Research source binding belongs to another pipeline definition")
        if envelope.research_wrapper_kind != wrapper_kind:
            raise ValueError("Research wrapper identity disagrees with membership key")
        standard_wrapper = _standard_product_kind(wrapper_kind)
        result[standard_wrapper] = envelope.standard_binding.model_dump(mode="json")
        if envelope.research_product_kind == research_product_kind_value:
            matching += 1
            if envelope.research_payload_digest != payload_digest:
                raise ValueError("Research source membership binds different payload bytes")
    if matching > 1:
        raise ValueError("Research source membership duplicates the payload binding")
    return cast(dict[str, JsonValue], {_STANDARD_MEMBERSHIP_KEY: result})


def production_research_v1_registry(definition_id: Sha256Digest) -> AnalyzerRegistry:
    standard = production_standard_v2_registry()
    registry = AnalyzerRegistry(
        _ResearchAnalyzer(
            RankedPathAlternateTracksAnalyzer()
            if key == "path-alternate-tracks"
            else standard.get(key),
            definition_id,
        )
        for key in standard.keys
    )
    registry.register(_ResearchAnalyzer(RateContinuityBaselineAnalyzer(), definition_id))
    if sum(len(registry.get(key).spec.output_products) for key in registry.keys) != 43:
        raise RuntimeError("Research-v1 registry output inventory changed")
    return registry


def production_research_v1_configuration() -> dict[str, dict[str, JsonValue]]:
    configuration = deepcopy(production_standard_v2_configuration())
    path = cast(dict[str, object], configuration["path-standard"])
    feedback = cast(dict[str, object], path["feedback"])
    feedback["subwindow_ms"] = 50
    feedback["probe_ms"] = 20
    feedback["probe_offsets_ms"] = [0, 15, 30]
    feedback["maximum_workers"] = 2
    feedback["maximum_scored_candidates_per_probe"] = 32
    # Persist all 32 independently scored basins, but keep the immutable
    # residual-Hough input below its 25,000-point safety bound.  A complete
    # 60-second dwell has 3,600 probes, so six ranked candidates/probe yields
    # 21,600 fitting points while the pilot-scan product retains all evidence.
    feedback["maximum_segmentation_candidates_per_probe"] = 6
    feedback["coarse_cfo_step_hz"] = 10_000.0
    feedback["fine_cfo_radius_hz"] = 10_000.0
    feedback["fine_cfo_step_hz"] = 100.0
    feedback["conditioned_cfo_radius_hz"] = 1_000.0
    feedback["conditioned_cfo_step_hz"] = 25.0
    feedback["retained_candidate_count"] = 32
    feedback["candidate_epoch_separation_samples"] = 5
    feedback["candidate_cfo_separation_hz"] = 10_000.0
    feedback["glrt_size"] = 4_096
    full_capture = cast(dict[str, object], path["full_capture_glrt20ms"])
    full_capture["enabled"] = False
    configuration["path-alternate-tracks"] = cast(
        dict[str, JsonValue],
        RankedCandidateResidualHoughConfigV3(
            segmentation=default_alternate_cfo_config(),
            maximum_candidates_per_probe=6,
        ).model_dump(mode="json"),
    )
    configuration["rate-continuity-baseline"] = cast(
        dict[str, JsonValue], rate_analysis_configuration_v1()
    )
    return configuration


def research_pipeline_definition_id(
    *,
    pipeline_release_id: str,
    configuration: dict[str, dict[str, JsonValue]],
) -> Sha256Digest:
    provisional = production_research_v1_registry("sha256:" + "0" * 64)
    graph = {
        "stages": [
            provisional.get(stage.key).spec.model_dump(mode="json")
            for stage in provisional.graph().plan()
        ]
    }
    return canonical_digest(
        {
            "schema_version": 1,
            "lane": "research",
            "pipeline_release_id": pipeline_release_id,
            "configuration": configuration,
            "graph": graph,
        }
    )
