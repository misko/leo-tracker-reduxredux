from __future__ import annotations

from leo.analysis.standard.analyzers import production_standard_v2_registry
from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.analysis.standard.native_full_capture_glrt import (
    native_full_capture_glrt_configuration_digest,
)
from leo.analysis.standard.native_products import (
    ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT,
    ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
    NUMERICAL_WATERFALL_V3_PRODUCT,
    PAIRED_PRESENTATION_NATIVE_OUTPUTS,
    PAIRED_REPORT_V6_PRODUCT,
    PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
    PATH_INPUT_BIND_V4_PRODUCT,
    PATH_REPORT_V3_PRODUCT,
    PATH_STANDARD_NATIVE_OUTPUTS,
    PILOT_DOPPLER_SEGMENTS_V3_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    QUALITY_V2_PRODUCT,
    RADIO_SCIENTIFIC_NATIVE_OUTPUTS,
    STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT,
    STATEFUL_PATH_V1_PRODUCT,
    STATEFUL_PATH_V2_PRODUCT,
)
from leo.analysis.standard.products import PATH_INPUT_BIND_PRODUCT
from leo.pipeline import StageOutcome


def test_native_product_inventory_is_additive_and_closed() -> None:
    assert PATH_INPUT_BIND_PRODUCT.schema_version == 3
    assert PATH_INPUT_BIND_V4_PRODUCT.schema_version == 4
    assert STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT == 36
    assert len(PATH_STANDARD_NATIVE_OUTPUTS) == 8
    assert len(PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS) == 14
    assert FULL_CAPTURE_GLRT20MS_V1_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS
    assert STATEFUL_PATH_V1_PRODUCT.schema_version == 1
    assert STATEFUL_PATH_V1_PRODUCT not in PATH_STANDARD_NATIVE_OUTPUTS
    assert STATEFUL_PATH_V2_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS
    assert PILOT_DOPPLER_SEGMENTS_V3_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS

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
    path_configuration = configuration["path-standard-native"]
    assert "probes" not in path_configuration
    assert path_configuration["full_capture_glrt_configuration_digest"] == (
        native_full_capture_glrt_configuration_digest(production_receiver_standard_config())
    )
    assert registry.get("path-standard-native").spec.output_products == (
        QUALITY_V2_PRODUCT,
        POWER_TIMELINE_V3_PRODUCT,
        NUMERICAL_WATERFALL_V3_PRODUCT,
        PROBE_SCHEDULE_V3_PRODUCT,
        STATEFUL_PATH_V2_PRODUCT,
        PILOT_DOPPLER_SEGMENTS_V3_PRODUCT,
        FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
        PATH_REPORT_V3_PRODUCT,
    )
    assert registry.get("path-standard-native").spec.algorithm_version == (
        "standard-native-evidence-v10"
    )
    assert registry.get("path-standard-native").spec.configuration_schema == (
        "path-standard-native.evidence.v8"
    )
    assert (
        registry.get("radio-scientific-report-native").spec.output_products
        == RADIO_SCIENTIFIC_NATIVE_OUTPUTS
    )
    assert registry.get("paired-scientific-report-native").spec.output_products == (
        PAIRED_REPORT_V6_PRODUCT,
    )
    assert (
        registry.get("paired-presentation-native").spec.output_products
        == PAIRED_PRESENTATION_NATIVE_OUTPUTS
    )
    alternate = registry.get("path-alternate-tracks-native").spec
    assert alternate.output_products == PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS
    assert ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT in alternate.output_products
    assert ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT in alternate.output_products
    assert alternate.algorithm_version == "standard-native-path-projection-v5"
    assert alternate.configuration_schema == "path-alternate-tracks-native.projection.v5"
    assert alternate.accepted_outcomes == (
        StageOutcome.COMPLETE,
        StageOutcome.NO_RESULT,
        StageOutcome.PARTIAL_COVERAGE,
        StageOutcome.INSUFFICIENT_DATA,
    )
    assert configuration["path-alternate-tracks-native"] == {}
    assert registry.get("radio-scientific-report-native").spec.algorithm_version == (
        "standard-native-radio-report-presentation-v9"
    )
    assert tuple(
        (item.kind, item.accepted_schema_versions, item.producer_stage_key)
        for item in alternate.input_products
    ) == tuple(
        (item.kind, (item.schema_version,), "path-standard-native")
        for item in (
            NUMERICAL_WATERFALL_V3_PRODUCT,
            STATEFUL_PATH_V2_PRODUCT,
            PILOT_DOPPLER_SEGMENTS_V3_PRODUCT,
            FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
            PATH_REPORT_V3_PRODUCT,
        )
    )
    assert sum(len(registry.get(key).spec.output_products) for key in registry.keys) == 36
    assert len(registry.get("path-standard-native").spec.output_products) == 8
