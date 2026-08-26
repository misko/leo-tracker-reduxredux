from __future__ import annotations

from leo.analysis.standard.analyzers import production_standard_v2_registry
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.analysis.standard.native_products import (
    FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
    NUMERICAL_WATERFALL_V3_PRODUCT,
    PAIRED_REPORT_V3_PRODUCT,
    PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
    PATH_INPUT_BIND_V4_PRODUCT,
    PATH_STANDARD_NATIVE_OUTPUTS,
    POWER_TIMELINE_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    QUALITY_V2_PRODUCT,
    RADIO_REPORT_V3_PRODUCT,
    STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT,
    STATEFUL_PATH_V1_PRODUCT,
    WATERFALL_PNG_V2_PRODUCT,
)
from leo.analysis.standard.products import PATH_INPUT_BIND_PRODUCT


def test_native_product_inventory_is_additive_and_closed() -> None:
    assert PATH_INPUT_BIND_PRODUCT.schema_version == 3
    assert PATH_INPUT_BIND_V4_PRODUCT.schema_version == 4
    assert STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT == 44
    assert len(PATH_STANDARD_NATIVE_OUTPUTS) == 30
    assert len(PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS) == 2
    assert FULL_CAPTURE_GLRT20MS_V1_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS

    identities = tuple(
        (item.kind, item.schema_version, item.role.value, item.media_type)
        for item in PATH_STANDARD_NATIVE_OUTPUTS
    )
    assert len(set(identities)) == len(identities)


def test_frozen_standard_registry_identity_does_not_move() -> None:
    registry = production_standard_v2_registry()

    assert sum(len(registry.get(key).spec.output_products) for key in registry.keys) == 42
    assert registry.get("path-standard").spec.algorithm_version == "standard-v2-production-8"


def test_native_evidence_registry_declares_only_executable_products() -> None:
    registry = production_standard_native_evidence_registry()
    configuration = production_standard_native_evidence_configuration()

    assert registry.keys == (
        "paired-presentation-native",
        "paired-scientific-report-native",
        "path-alternate-tracks-native",
        "path-standard-native",
        "radio-scientific-report-native",
    )
    assert set(configuration) == set(registry.keys)
    assert registry.get("path-standard-native").spec.output_products == (
        QUALITY_V2_PRODUCT,
        POWER_TIMELINE_V3_PRODUCT,
        NUMERICAL_WATERFALL_V3_PRODUCT,
        PROBE_SCHEDULE_V3_PRODUCT,
        STATEFUL_PATH_V1_PRODUCT,
    )
    assert registry.get("radio-scientific-report-native").spec.output_products == (
        RADIO_REPORT_V3_PRODUCT,
    )
    assert registry.get("paired-scientific-report-native").spec.output_products == (
        PAIRED_REPORT_V3_PRODUCT,
    )
    assert registry.get("paired-presentation-native").spec.output_products == (
        WATERFALL_PNG_V2_PRODUCT,
    )
    assert registry.get("path-alternate-tracks-native").spec.output_products == ()
    assert sum(len(registry.get(key).spec.output_products) for key in registry.keys) == 8
    assert len(registry.get("path-standard-native").spec.output_products) == 5
