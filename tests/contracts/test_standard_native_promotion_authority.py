from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from leo.artifacts import (
    AnalysisJobReceiptV1,
    AnalysisProductReceiptV1,
    AnalysisRunManifestV1,
    AnalysisRunManifestV2,
    AnalysisRunManifestV3,
    StandardNativePromotionAuthorityV1,
    StandardNativeTerminalProductRefV1,
    parse_analysis_run_manifest,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineDefinitionV1, PipelineLane

_RELEASE = "a" * 40


def _digest(label: str) -> str:
    return canonical_digest({"fixture": label})


def _pipeline_definition(
    *,
    automatic_eligible: bool = True,
    promotion_allowed: bool = True,
) -> PipelineDefinitionV1:
    values = {
        "schema_version": 1,
        "lane": "standard",
        "executable_git_sha": _RELEASE,
        "graph_digest": _digest("graph"),
        "configuration_digest": _digest("configuration"),
        "product_namespace": "standard",
        "automatic_eligible": automatic_eligible,
        "promotion_allowed": promotion_allowed,
    }
    return PipelineDefinitionV1.model_validate(
        {**values, "definition_id": canonical_digest(values)}
    )


def _jobs() -> tuple[AnalysisJobReceiptV1, ...]:
    return (
        AnalysisJobReceiptV1(
            job_id=4,
            stage_key="native-paired",
            scope_key="session-a",
            outcome="complete",
        ),
        AnalysisJobReceiptV1(
            job_id=1,
            stage_key="native-path",
            scope_key="path-a",
            outcome="complete",
        ),
        AnalysisJobReceiptV1(
            job_id=2,
            stage_key="native-radio",
            scope_key="radio-a",
            outcome="complete",
        ),
        AnalysisJobReceiptV1(
            job_id=3,
            stage_key="native-radio",
            scope_key="radio-b",
            outcome="partial_coverage",
        ),
    )


def _product(
    product_id: int,
    *,
    stage_key: str,
    scope_key: str,
    kind: str,
    schema_version: int,
    status: str,
) -> AnalysisProductReceiptV1:
    return AnalysisProductReceiptV1(
        product_id=product_id,
        stage_key=stage_key,
        scope_key=scope_key,
        kind=kind,
        product_schema_version=schema_version,
        role="scientific",
        status=status,
        media_type="application/json",
        logical_uri=(
            f"bulk://analysis/session-a/run-a/scientific/{stage_key}/{scope_key}/"
            f"{kind}.v{schema_version}.json"
        ),
        digest=_digest(f"product-{product_id}"),
        byte_size=product_id * 100,
        coverage=1.0,
    )


def _products() -> tuple[AnalysisProductReceiptV1, ...]:
    return (
        _product(
            4,
            stage_key="native-paired",
            scope_key="session-a",
            kind="standard.native.paired.report",
            schema_version=5,
            status="complete",
        ),
        _product(
            1,
            stage_key="native-path",
            scope_key="path-a",
            kind="standard.native.path.intermediate",
            schema_version=4,
            status="complete",
        ),
        _product(
            2,
            stage_key="native-radio",
            scope_key="radio-a",
            kind="standard.native.radio.report",
            schema_version=5,
            status="complete",
        ),
        _product(
            3,
            stage_key="native-radio",
            scope_key="radio-b",
            kind="standard.native.radio.report",
            schema_version=5,
            status="partial_coverage",
        ),
    )


def _terminal_ref(product: AnalysisProductReceiptV1) -> StandardNativeTerminalProductRefV1:
    return StandardNativeTerminalProductRefV1(
        product_id=product.product_id,
        stage_key=product.stage_key,
        scope_key=product.scope_key,
        kind=product.kind,
        product_schema_version=product.product_schema_version,
        role="scientific",
        status=product.status,
        digest=product.digest,
    )


def _promotion_authority(
    *,
    definition: PipelineDefinitionV1 | None = None,
    run_id: str = "run-a",
) -> StandardNativePromotionAuthorityV1:
    pipeline_definition = definition or _pipeline_definition()
    products = _products()
    terminal_products = tuple(_terminal_ref(product) for product in (products[0], *products[2:]))
    values = {
        "schema_version": 1,
        "source_manifest_schema_version": 3,
        "source_manifest_digest": _digest("manifest"),
        "pipeline_definition": pipeline_definition.model_dump(mode="json"),
        "pipeline_definition_id": pipeline_definition.definition_id,
        "session_id": "session-a",
        "run_id": run_id,
        "input_manifest_digest": _digest("manifest"),
        "pipeline_release_id": _RELEASE,
        "expanded_plan_digest": _digest("expanded-plan"),
        "raw_integrity_attestation_digest": _digest("raw-integrity"),
        "release_authority_digest": _digest("release-authority"),
        "subject_binding_inventory_digest": _digest("subject-bindings"),
        "terminal_products": tuple(item.model_dump(mode="json") for item in terminal_products),
        "terminal_product_inventory_digest": canonical_digest(
            tuple(item.model_dump(mode="json") for item in terminal_products)
        ),
        "profile_revision_digest": _digest("profile-revision"),
        "sample_rate_hz": 5_000_000,
        "capture_plan_digest": _digest("capture-plan"),
        "capture_hardware_binding_digest": _digest("capture-hardware-binding"),
        "trigger": "new_capture",
        "promotion_policy": "current",
        "processing_status": "succeeded",
    }
    return StandardNativePromotionAuthorityV1.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )


def _manifest() -> AnalysisRunManifestV3:
    authority = _promotion_authority()
    values = {
        "schema_version": 3,
        "session_id": "session-a",
        "run_id": "run-a",
        "pipeline_release_id": _RELEASE,
        "input_manifest_digest": _digest("manifest"),
        "trigger": "new_capture",
        "pipeline_lane": "standard",
        "promotion_policy": "current",
        "processing_status": "succeeded",
        "jobs": tuple(item.model_dump(mode="json") for item in _jobs()),
        "products": tuple(item.model_dump(mode="json") for item in _products()),
        "promotion_authority": authority.model_dump(mode="json"),
    }
    return AnalysisRunManifestV3.model_validate(
        {**values, "content_digest": canonical_digest(values)}
    )


def _redigest(document: dict[str, object]) -> None:
    document["content_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "content_digest"}
    )


def test_promotion_manifest_round_trips_and_binds_only_terminal_subset() -> None:
    manifest = _manifest()
    parsed = parse_analysis_run_manifest(manifest.model_dump(mode="json"))

    assert parsed == manifest
    assert isinstance(parsed, AnalysisRunManifestV3)
    assert parsed.promotion_authority.pipeline_definition.lane is PipelineLane.STANDARD
    assert parsed.promotion_authority.sample_rate_hz == 5_000_000
    assert tuple(item.product_id for item in parsed.promotion_authority.terminal_products) == (
        4,
        2,
        3,
    )
    assert 1 not in {item.product_id for item in parsed.promotion_authority.terminal_products}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("source_manifest_schema_version", 2, "literal_error"),
        ("sample_rate_hz", 4_000_000, "literal_error"),
        ("trigger", "manual", "literal_error"),
        ("promotion_policy", "evidence_only", "literal_error"),
        ("processing_status", "failed", "literal_error"),
    ),
)
def test_promotion_authority_rejects_unreviewed_source_rate_or_policy(
    field: str,
    value: object,
    message: str,
) -> None:
    document = _promotion_authority().model_dump(mode="json")
    document[field] = value
    _redigest(document)

    with pytest.raises(ValueError, match=message):
        StandardNativePromotionAuthorityV1.model_validate(document)


@pytest.mark.parametrize("definition_field", ("automatic_eligible", "promotion_allowed"))
def test_promotion_authority_requires_a_promotable_automatic_standard_definition(
    definition_field: str,
) -> None:
    definition = _pipeline_definition(
        automatic_eligible=definition_field != "automatic_eligible",
        promotion_allowed=definition_field != "promotion_allowed",
    )

    with pytest.raises(ValueError, match="promotable Standard definition"):
        _promotion_authority(definition=definition)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("pipeline_definition_id", _digest("foreign-definition"), "exact promotable"),
        ("pipeline_release_id", "b" * 40, "release differs"),
        ("source_manifest_digest", _digest("foreign-manifest"), "source differs"),
        (
            "terminal_product_inventory_digest",
            _digest("foreign-terminal-inventory"),
            "inventory digest",
        ),
        ("content_digest", _digest("foreign-authority"), "content digest"),
    ),
)
def test_promotion_authority_rejects_changed_definition_source_or_digest(
    field: str,
    value: object,
    message: str,
) -> None:
    document = _promotion_authority().model_dump(mode="json")
    document[field] = value
    if field != "content_digest":
        _redigest(document)

    with pytest.raises(ValueError, match=message):
        StandardNativePromotionAuthorityV1.model_validate(document)


def test_promotion_authority_rejects_reordered_terminal_inventory() -> None:
    document = _promotion_authority().model_dump(mode="json")
    terminal_products = list(document["terminal_products"])
    terminal_products.reverse()
    document["terminal_products"] = terminal_products
    document["terminal_product_inventory_digest"] = canonical_digest(terminal_products)
    _redigest(document)

    with pytest.raises(ValueError, match="unique and ordered"):
        StandardNativePromotionAuthorityV1.model_validate(document)


def test_manifest_rejects_authority_for_another_run() -> None:
    document = _manifest().model_dump(mode="json")
    authority = _promotion_authority(run_id="run-b")
    document["promotion_authority"] = authority.model_dump(mode="json")
    _redigest(document)

    with pytest.raises(ValueError, match="another run"):
        AnalysisRunManifestV3.model_validate(document)


@pytest.mark.parametrize("changed_field", ("product_id", "digest", "status"))
def test_manifest_rejects_terminal_reference_not_in_exact_outer_inventory(
    changed_field: str,
) -> None:
    document = _manifest().model_dump(mode="json")
    authority = dict(document["promotion_authority"])
    terminal_products = [dict(item) for item in authority["terminal_products"]]
    changed = terminal_products[0]
    if changed_field == "product_id":
        changed[changed_field] = 99
    elif changed_field == "digest":
        changed[changed_field] = _digest("foreign-product")
    else:
        changed[changed_field] = "partial_coverage"
    authority["terminal_products"] = terminal_products
    authority["terminal_product_inventory_digest"] = canonical_digest(terminal_products)
    _redigest(authority)
    document["promotion_authority"] = authority
    _redigest(document)

    with pytest.raises(ValueError, match="sealed run inventory"):
        AnalysisRunManifestV3.model_validate(document)


def test_manifest_rejects_duplicate_product_ids_and_changed_content_digest() -> None:
    duplicate_id = _manifest().model_dump(mode="json")
    products = [dict(item) for item in duplicate_id["products"]]
    products[1]["product_id"] = products[0]["product_id"]
    duplicate_id["products"] = products
    _redigest(duplicate_id)
    with pytest.raises(ValueError, match="product IDs must be unique"):
        AnalysisRunManifestV3.model_validate(duplicate_id)

    changed_digest = _manifest().model_dump(mode="json")
    changed_digest["content_digest"] = _digest("foreign-manifest-content")
    with pytest.raises(ValueError, match="manifest content digest"):
        AnalysisRunManifestV3.model_validate(changed_digest)


def test_v1_v2_manifest_ast_and_serialization_remain_frozen() -> None:
    source = Path(__file__).parents[2] / "src" / "leo" / "artifacts" / "models.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    expected_ast_digests = {
        "AnalysisRunManifestV1": (
            "sha256:738c3e9eb22b0116b05cc7524a693016d3b138ca326ddd27b7648f703a43c764"
        ),
        "AnalysisRunManifestV2": (
            "sha256:81eb58304caa141c418241fad388159be1646f4c0b4a495ecb6712a18760ede3"
        ),
    }
    for name, expected in expected_ast_digests.items():
        node = next(
            item for item in module.body if isinstance(item, ast.ClassDef) and item.name == name
        )
        payload = ast.dump(node, annotate_fields=True, include_attributes=False).encode()
        assert f"sha256:{hashlib.sha256(payload).hexdigest()}" == expected

    job = AnalysisJobReceiptV1(
        job_id=1,
        stage_key="quality",
        scope_key="path-a",
        outcome="complete",
    )
    product = _product(
        1,
        stage_key="quality",
        scope_key="path-a",
        kind="quality.summary",
        schema_version=1,
        status="complete",
    )
    common = {
        "session_id": "session-a",
        "run_id": "run-a",
        "pipeline_release_id": _RELEASE,
        "input_manifest_digest": _digest("manifest"),
        "trigger": "new_capture",
        "jobs": [job.model_dump(mode="json")],
        "products": [product.model_dump(mode="json")],
    }
    v1_document = {"schema_version": 1, **common}
    v2_document = {
        "schema_version": 2,
        **{key: value for key, value in common.items() if key not in {"jobs", "products"}},
        "pipeline_lane": "standard",
        "jobs": common["jobs"],
        "products": common["products"],
    }

    v1 = AnalysisRunManifestV1.model_validate(v1_document)
    v2 = AnalysisRunManifestV2.model_validate(v2_document)
    assert v1.model_dump(mode="json") == v1_document
    assert v2.model_dump(mode="json") == v2_document
    assert parse_analysis_run_manifest(v1_document) == v1
    assert parse_analysis_run_manifest(v2_document) == v2
