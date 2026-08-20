"""Stable wrappers that bind every Standard science product to exact path IQ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import (
    STANDARD_NUMERICAL_WATERFALL_KIND,
    STANDARD_PILOT_SOURCE_BIND_KIND,
    STANDARD_POWER_SOURCE_BIND_KIND,
    STANDARD_POWER_TIMELINE_KIND,
    STANDARD_PROBE_SCHEDULE_KIND,
    STANDARD_QUALITY_SOURCE_BIND_KIND,
    STANDARD_SCHEDULE_SOURCE_BIND_KIND,
    STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND,
    STANDARD_TRAJECTORY_FEEDBACK_SOURCE_BIND_KIND,
    STANDARD_TRAJECTORY_TABLE_SOURCE_BIND_KIND,
    STANDARD_WATERFALL_SOURCE_BIND_KIND,
    StandardBoundPredecessorV1,
    StandardPathInputBindV3,
    StandardSourceBindingV1,
)


@dataclass(frozen=True, slots=True)
class StandardSourceBindingSpec:
    wrapper_kind: str
    stage_key: str
    product_kind: str
    product_schema_version: int
    predecessor_wrapper_kinds: tuple[str, ...] = ()


STANDARD_SOURCE_BINDING_SPECS = (
    StandardSourceBindingSpec(
        STANDARD_QUALITY_SOURCE_BIND_KIND,
        "path-quality",
        "quality.summary",
        1,
    ),
    StandardSourceBindingSpec(
        STANDARD_POWER_SOURCE_BIND_KIND,
        "path-power",
        STANDARD_POWER_TIMELINE_KIND,
        2,
        (STANDARD_QUALITY_SOURCE_BIND_KIND,),
    ),
    StandardSourceBindingSpec(
        STANDARD_WATERFALL_SOURCE_BIND_KIND,
        "path-waterfall",
        STANDARD_NUMERICAL_WATERFALL_KIND,
        2,
        (STANDARD_POWER_SOURCE_BIND_KIND,),
    ),
    StandardSourceBindingSpec(
        STANDARD_SCHEDULE_SOURCE_BIND_KIND,
        "path-probe-schedule",
        STANDARD_PROBE_SCHEDULE_KIND,
        2,
    ),
    StandardSourceBindingSpec(
        STANDARD_PILOT_SOURCE_BIND_KIND,
        "path-pilot-scan",
        "standard.pilot-scan",
        3,
        (STANDARD_SCHEDULE_SOURCE_BIND_KIND,),
    ),
    StandardSourceBindingSpec(
        STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND,
        "path-trajectory-bank",
        "standard.trajectory-bank",
        2,
        (STANDARD_PILOT_SOURCE_BIND_KIND,),
    ),
    StandardSourceBindingSpec(
        STANDARD_TRAJECTORY_FEEDBACK_SOURCE_BIND_KIND,
        "path-trajectory-feedback",
        "standard.trajectory-feedback",
        2,
        (
            STANDARD_PILOT_SOURCE_BIND_KIND,
            STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND,
        ),
    ),
    StandardSourceBindingSpec(
        STANDARD_TRAJECTORY_TABLE_SOURCE_BIND_KIND,
        "path-trajectory-feedback",
        "standard.glrt64-trajectory-table",
        2,
        (
            STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND,
            STANDARD_TRAJECTORY_FEEDBACK_SOURCE_BIND_KIND,
        ),
    ),
)

STANDARD_CFO_ALIAS_MAP_SOURCE_BIND_KIND = "standard.cfo-alias-map-source-bind"
STANDARD_DEALIASED_BANK_SOURCE_BIND_KIND = "standard.dealiased-bank-source-bind"
STANDARD_CFO_LIFT_REPLAY_SOURCE_BIND_KIND = "standard.cfo-lift-replay-source-bind"
STANDARD_FINAL_BANK_SOURCE_BIND_KIND = "standard.final-bank-source-bind"
STANDARD_FINAL_TABLE_SOURCE_BIND_KIND = "standard.final-table-source-bind"

STANDARD_FINAL_SOURCE_BINDING_SPECS = (
    StandardSourceBindingSpec(
        STANDARD_CFO_ALIAS_MAP_SOURCE_BIND_KIND,
        "path-standard",
        "standard.cfo-alias-map",
        2,
        (STANDARD_PILOT_SOURCE_BIND_KIND, STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND),
    ),
    StandardSourceBindingSpec(
        STANDARD_DEALIASED_BANK_SOURCE_BIND_KIND,
        "path-standard",
        "standard.dealiased-trajectory-bank",
        1,
        (
            STANDARD_PILOT_SOURCE_BIND_KIND,
            STANDARD_TRAJECTORY_BANK_SOURCE_BIND_KIND,
            STANDARD_CFO_ALIAS_MAP_SOURCE_BIND_KIND,
        ),
    ),
    StandardSourceBindingSpec(
        STANDARD_CFO_LIFT_REPLAY_SOURCE_BIND_KIND,
        "path-standard",
        "standard.cfo-lift-replay",
        1,
        (STANDARD_PILOT_SOURCE_BIND_KIND, STANDARD_DEALIASED_BANK_SOURCE_BIND_KIND),
    ),
    StandardSourceBindingSpec(
        STANDARD_FINAL_BANK_SOURCE_BIND_KIND,
        "path-standard",
        "standard.final-trajectory-bank",
        1,
        (STANDARD_DEALIASED_BANK_SOURCE_BIND_KIND, STANDARD_CFO_LIFT_REPLAY_SOURCE_BIND_KIND),
    ),
    StandardSourceBindingSpec(
        STANDARD_FINAL_TABLE_SOURCE_BIND_KIND,
        "path-standard",
        "standard.glrt64-final-trajectory-table",
        1,
        (STANDARD_FINAL_BANK_SOURCE_BIND_KIND, STANDARD_CFO_LIFT_REPLAY_SOURCE_BIND_KIND),
    ),
)

_ALL_SOURCE_BINDING_SPECS = (
    *STANDARD_SOURCE_BINDING_SPECS,
    *STANDARD_FINAL_SOURCE_BINDING_SPECS,
)


def build_standard_source_bindings(
    input_bind: StandardPathInputBindV3,
    source_documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Assemble the deterministic runner from the same per-stage wrapper function."""

    expected_source_kinds = {item.product_kind for item in STANDARD_SOURCE_BINDING_SPECS}
    if set(source_documents) != expected_source_kinds:
        raise ValueError("source-binding input inventory is incomplete or contains extras")
    result: dict[str, dict[str, Any]] = {}
    for spec in STANDARD_SOURCE_BINDING_SPECS:
        result[spec.wrapper_kind] = build_standard_source_binding(
            spec,
            source_documents[spec.product_kind],
            input_bind=input_bind if not spec.predecessor_wrapper_kinds else None,
            predecessor_binding_documents={
                kind: result[kind] for kind in spec.predecessor_wrapper_kinds
            },
        )
    return result


def build_standard_final_source_bindings(
    input_bind: StandardPathInputBindV3,
    source_documents: dict[str, dict[str, Any]],
    raw_binding_documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Bind canonical/final products to the exact raw path chain."""

    if set(raw_binding_documents) != {item.wrapper_kind for item in STANDARD_SOURCE_BINDING_SPECS}:
        raise ValueError("final source binding requires the complete raw binding inventory")
    if set(source_documents) != {item.product_kind for item in STANDARD_FINAL_SOURCE_BINDING_SPECS}:
        raise ValueError("final source-binding document inventory is not exact")
    result = dict(raw_binding_documents)
    final: dict[str, dict[str, Any]] = {}
    for spec in STANDARD_FINAL_SOURCE_BINDING_SPECS:
        predecessors = {kind: result[kind] for kind in spec.predecessor_wrapper_kinds}
        document = build_standard_source_binding(
            spec,
            source_documents[spec.product_kind],
            input_bind=input_bind,
            predecessor_binding_documents=predecessors,
        )
        result[spec.wrapper_kind] = document
        final[spec.wrapper_kind] = document
    return final


def build_standard_source_binding(
    spec: StandardSourceBindingSpec,
    source_document: dict[str, Any],
    *,
    input_bind: StandardPathInputBindV3 | None = None,
    predecessor_binding_documents: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bind one stage using only its declared direct predecessor products."""

    predecessor_binding_documents = predecessor_binding_documents or {}
    if set(predecessor_binding_documents) != set(spec.predecessor_wrapper_kinds):
        raise ValueError(f"{spec.wrapper_kind} predecessor wrapper inventory is not exact")
    predecessors = tuple(
        StandardSourceBindingV1.model_validate(predecessor_binding_documents[kind])
        for kind in spec.predecessor_wrapper_kinds
    )
    for kind, predecessor in zip(
        spec.predecessor_wrapper_kinds,
        predecessors,
        strict=True,
    ):
        if kind != _wrapper_kind_for_product(predecessor.product_kind):
            raise ValueError(f"{spec.wrapper_kind} received a substituted predecessor wrapper")

    if predecessors:
        binding_identities = {
            (
                item.path_input_binding_digest,
                item.path_input_bind_content_digest,
            )
            for item in predecessors
        }
        if len(binding_identities) != 1:
            raise ValueError(f"{spec.wrapper_kind} predecessors bind different path inputs")
        binding_digest, bind_content_digest = next(iter(binding_identities))
        if input_bind is not None:
            expected = (
                input_bind.binding_digest,
                canonical_digest(input_bind.model_dump(mode="json")),
            )
            if (binding_digest, bind_content_digest) != expected:
                raise ValueError(f"{spec.wrapper_kind} predecessor path binding is foreign")
    elif input_bind is not None:
        binding_digest = input_bind.binding_digest
        bind_content_digest = canonical_digest(input_bind.model_dump(mode="json"))
    else:
        raise ValueError(f"{spec.wrapper_kind} requires exact path-binding authority")

    document = StandardSourceBindingV1(
        algorithm_version="standard-source-binding-v1",
        stage_key=spec.stage_key,
        product_kind=spec.product_kind,
        product_schema_version=spec.product_schema_version,
        product_content_digest=canonical_digest(source_document),
        path_input_binding_digest=binding_digest,
        path_input_bind_content_digest=bind_content_digest,
        predecessors=tuple(
            StandardBoundPredecessorV1(
                kind=kind,
                content_digest=canonical_digest(predecessor_binding_documents[kind]),
            )
            for kind in sorted(spec.predecessor_wrapper_kinds)
        ),
    )
    return document.model_dump(mode="json")


def _wrapper_kind_for_product(product_kind: str) -> str:
    matches = tuple(
        item.wrapper_kind for item in _ALL_SOURCE_BINDING_SPECS if item.product_kind == product_kind
    )
    if len(matches) != 1:
        raise ValueError(f"unknown source-bound predecessor product {product_kind!r}")
    return matches[0]


def verify_standard_source_bindings(
    input_bind: StandardPathInputBindV3,
    source_documents: dict[str, dict[str, Any]],
    binding_documents: dict[str, dict[str, Any]],
) -> None:
    """Reject coherent same-geometry products from any foreign path binding."""

    expected = build_standard_source_bindings(input_bind, source_documents)
    if set(binding_documents) != set(expected):
        raise ValueError("source-binding wrapper inventory is incomplete or contains extras")
    for kind, expected_document in expected.items():
        actual = StandardSourceBindingV1.model_validate(binding_documents[kind])
        if actual.model_dump(mode="json") != expected_document:
            raise ValueError(f"{kind} does not bind the exact Standard path source chain")
