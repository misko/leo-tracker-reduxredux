from __future__ import annotations

from typing import cast

import pytest
from pydantic import JsonValue

from leo.analysis.research.analyzers import (
    _ResearchOutputSink,
    _unwrap_membership,
    _wrap_membership,
    production_research_v1_configuration,
    production_research_v1_registry,
    research_product_kind,
)
from leo.analysis.standard.analyzers import (
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.research_pipeline import ResearchProductEnvelopeV1
from leo.contracts.standard_pipeline import StandardSourceBindingV1
from leo.pipeline import ProductSpec, PublishedProduct


class _Sink:
    def __init__(self) -> None:
        self.product: ProductSpec | None = None
        self.document: dict[str, JsonValue] | None = None

    def publish_json(
        self, product: ProductSpec, document: dict[str, JsonValue]
    ) -> PublishedProduct:
        self.product = product
        self.document = document
        return PublishedProduct(
            product=product,
            logical_uri="local://research/product.json",
            digest=canonical_digest(document),
            byte_size=1,
        )

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        self.product = product
        return PublishedProduct(
            product=product,
            logical_uri="local://research/product.png",
            digest="sha256:" + "a" * 64,
            byte_size=len(payload),
        )


def test_research_registry_has_disjoint_product_namespace_and_exact_inventory() -> None:
    definition = canonical_digest({"pipeline": "research"})
    standard = production_standard_v2_registry()
    research = production_research_v1_registry(definition)
    standard_kinds = {
        product.kind for key in standard.keys for product in standard.get(key).spec.output_products
    }
    research_kinds = {
        product.kind for key in research.keys for product in research.get(key).spec.output_products
    }
    assert standard.keys == research.keys
    assert sum(len(research.get(key).spec.output_products) for key in research.keys) == 36
    assert not standard_kinds & research_kinds
    assert all(kind.startswith("research.") for kind in research_kinds)
    assert (
        research.get("path-alternate-tracks").spec.algorithm_version
        == "research-alternate-cfo-residual-hough-v3"
    )
    assert research.get("path-standard").spec.algorithm_version == (
        "research-standard-v2-production-4"
    )


def test_research_configuration_is_dense_without_mutating_standard() -> None:
    research = production_research_v1_configuration()
    standard = production_standard_v2_configuration()
    research_feedback = research["path-standard"]["feedback"]
    standard_feedback = standard["path-standard"]["feedback"]

    assert research_feedback["probe_offsets_ms"] == [0, 15, 30]
    assert research_feedback["probe_ms"] == 20
    assert research_feedback["subwindow_ms"] == 50
    assert research_feedback["maximum_scored_candidates_per_probe"] == 32
    assert research_feedback["maximum_segmentation_candidates_per_probe"] == 6
    assert research_feedback["retained_candidate_count"] == 32
    assert research_feedback["coarse_cfo_step_hz"] == 10_000.0
    assert research_feedback["fine_cfo_step_hz"] == 100.0
    assert research_feedback["conditioned_cfo_step_hz"] == 25.0
    assert research_feedback["candidate_cfo_separation_hz"] == 10_000.0
    assert research_feedback["candidate_epoch_separation_samples"] == 5
    assert research_feedback["glrt_size"] == 4_096
    research_segmentation = research["path-alternate-tracks"]
    assert research_segmentation["schema_version"] == 3
    assert research_segmentation["maximum_candidates_per_probe"] == 6
    assert standard_feedback["probe_offsets_ms"] == [0, 25]
    assert standard_feedback["maximum_scored_candidates_per_probe"] == 10
    assert standard_feedback["retained_candidate_count"] == 10
    assert standard_feedback["glrt_size"] == 512


def test_research_json_publication_is_definition_bound_envelope() -> None:
    definition = canonical_digest({"pipeline": "research"})
    target = _Sink()
    sink = _ResearchOutputSink(target, definition)
    payload = cast(dict[str, JsonValue], {"schema_version": 3, "value": 4})
    published = sink.publish_json(
        ProductSpec(kind="standard.pilot-scan", schema_version=3), payload
    )
    assert published.product.kind == "research.pilot-scan"
    assert published.product.schema_version == 1
    assert target.document is not None
    envelope = ResearchProductEnvelopeV1.model_validate(target.document)
    assert envelope.pipeline_definition_id == definition
    assert envelope.payload_kind == "standard.pilot-scan"
    assert envelope.payload_schema_version == 3
    assert envelope.payload == payload


def test_research_source_membership_round_trips_only_for_exact_definition() -> None:
    definition = canonical_digest({"pipeline": "research"})
    payload_digest = canonical_digest({"payload": 1})
    binding = StandardSourceBindingV1(
        algorithm_version="standard-source-binding-v1",
        stage_key="path-quality",
        product_kind="quality.summary",
        product_schema_version=1,
        product_content_digest=payload_digest,
        path_input_binding_digest="sha256:" + "1" * 64,
        path_input_bind_content_digest="sha256:" + "2" * 64,
    )
    standard_membership = cast(
        dict[str, JsonValue],
        {
            "standard_source_bindings": {
                "standard.quality-source-bind": binding.model_dump(mode="json")
            }
        },
    )
    wrapped = _wrap_membership(standard_membership, definition_id=definition)
    restored = _unwrap_membership(
        wrapped,
        definition_id=definition,
        research_product_kind_value=research_product_kind("quality.summary"),
        payload_digest=payload_digest,
    )
    assert restored == standard_membership

    membership_free_product = _unwrap_membership(
        wrapped,
        definition_id=definition,
        research_product_kind_value="research.path-presentation",
        payload_digest=canonical_digest({"presentation": 1}),
    )
    assert membership_free_product == standard_membership

    with pytest.raises(ValueError, match="different payload bytes"):
        _unwrap_membership(
            wrapped,
            definition_id=definition,
            research_product_kind_value=research_product_kind("quality.summary"),
            payload_digest=canonical_digest({"payload": 2}),
        )
