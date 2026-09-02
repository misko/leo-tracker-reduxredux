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
    ALTERNATE_CFO_TRACK_BANK_V5_PRODUCT,
    ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V2_PRODUCT,
    GLRT_EPOCH_RATE_PNG_V2_PRODUCT,
    GLRT_EPOCH_TIMING_PNG_V2_PRODUCT,
    GLRT_EPOCH_TRACKING_V2_PRODUCT,
    GLRT_FRACTIONAL_EPOCH_V1_PRODUCT,
    NUMERICAL_WATERFALL_V4_PRODUCT,
    PAIRED_PRESENTATION_NATIVE_OUTPUTS,
    PAIRED_PSS_GLRT_PRESENTATION_NATIVE_OUTPUTS,
    PAIRED_REPORT_V7_PRODUCT,
    PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
    PATH_INPUT_BIND_V4_PRODUCT,
    PATH_INPUT_BIND_V5_PRODUCT,
    PATH_PSS_NATIVE_OUTPUTS,
    PATH_REPORT_V4_PRODUCT,
    PATH_STANDARD_NATIVE_OUTPUTS,
    PILOT_DOPPLER_SEGMENTS_V4_PRODUCT,
    POWER_TIMELINE_V4_PRODUCT,
    PROBE_SCHEDULE_V4_PRODUCT,
    PSS_FRAME_TIMING_V1_PRODUCT,
    PSS_GLRT_FRAME_COMPARISON_PNG_V2_PRODUCT,
    QUALITY_V3_PRODUCT,
    RADIO_SCIENTIFIC_NATIVE_OUTPUTS,
    STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT,
    STATEFUL_PATH_V1_PRODUCT,
    STATEFUL_PATH_V3_PRODUCT,
)
from leo.analysis.standard.native_pss import (
    StandardNativePssConfig,
    standard_native_pss_configuration_digest,
)
from leo.analysis.standard.products import PATH_INPUT_BIND_PRODUCT
from leo.pipeline import StageOutcome


def test_native_product_inventory_is_additive_and_closed() -> None:
    assert PATH_INPUT_BIND_PRODUCT.schema_version == 3
    assert PATH_INPUT_BIND_V4_PRODUCT.schema_version == 4
    assert PATH_INPUT_BIND_V5_PRODUCT.schema_version == 5
    assert STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT == 42
    assert len(PATH_STANDARD_NATIVE_OUTPUTS) == 9
    assert len(PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS) == 17
    assert FULL_CAPTURE_GLRT20MS_V2_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS
    assert GLRT_FRACTIONAL_EPOCH_V1_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS
    assert STATEFUL_PATH_V1_PRODUCT.schema_version == 1
    assert STATEFUL_PATH_V1_PRODUCT not in PATH_STANDARD_NATIVE_OUTPUTS
    assert STATEFUL_PATH_V3_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS
    assert PILOT_DOPPLER_SEGMENTS_V4_PRODUCT in PATH_STANDARD_NATIVE_OUTPUTS
    assert PSS_FRAME_TIMING_V1_PRODUCT not in PATH_STANDARD_NATIVE_OUTPUTS
    assert PATH_PSS_NATIVE_OUTPUTS == (PSS_FRAME_TIMING_V1_PRODUCT,)
    assert GLRT_EPOCH_TRACKING_V2_PRODUCT in PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS
    assert GLRT_EPOCH_TIMING_PNG_V2_PRODUCT in PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS
    assert GLRT_EPOCH_RATE_PNG_V2_PRODUCT in PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS
    assert PSS_GLRT_FRAME_COMPARISON_PNG_V2_PRODUCT not in PAIRED_PRESENTATION_NATIVE_OUTPUTS
    assert PAIRED_PSS_GLRT_PRESENTATION_NATIVE_OUTPUTS == (
        PSS_GLRT_FRAME_COMPARISON_PNG_V2_PRODUCT,
    )

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
        "paired-pss-glrt-presentation-native",
        "paired-scientific-report-native",
        "path-alternate-tracks-native",
        "path-pss-native",
        "path-standard-native",
        "radio-scientific-report-native",
    )
    assert set(configuration) == set(registry.keys)
    path_configuration = configuration["path-standard-native"]
    assert "probes" not in path_configuration
    assert path_configuration["full_capture_glrt_configuration_digest"] == (
        native_full_capture_glrt_configuration_digest(production_receiver_standard_config())
    )
    assert configuration["path-pss-native"]["pss_configuration_digest"] == (
        standard_native_pss_configuration_digest(StandardNativePssConfig())
    )
    assert registry.get("path-standard-native").spec.output_products == (
        QUALITY_V3_PRODUCT,
        POWER_TIMELINE_V4_PRODUCT,
        NUMERICAL_WATERFALL_V4_PRODUCT,
        PROBE_SCHEDULE_V4_PRODUCT,
        STATEFUL_PATH_V3_PRODUCT,
        PILOT_DOPPLER_SEGMENTS_V4_PRODUCT,
        FULL_CAPTURE_GLRT20MS_V2_PRODUCT,
        GLRT_FRACTIONAL_EPOCH_V1_PRODUCT,
        PATH_REPORT_V4_PRODUCT,
    )
    assert registry.get("path-standard-native").spec.algorithm_version == (
        "standard-native-evidence-v14"
    )
    assert registry.get("path-standard-native").spec.configuration_schema == (
        "path-standard-native.evidence.v12"
    )
    assert registry.get("path-pss-native").spec.output_products == PATH_PSS_NATIVE_OUTPUTS
    assert registry.get("path-pss-native").spec.algorithm_version == ("standard-native-path-pss-v1")
    assert (
        registry.get("radio-scientific-report-native").spec.output_products
        == RADIO_SCIENTIFIC_NATIVE_OUTPUTS
    )
    assert registry.get("paired-scientific-report-native").spec.output_products == (
        PAIRED_REPORT_V7_PRODUCT,
    )
    assert (
        registry.get("paired-presentation-native").spec.output_products
        == PAIRED_PRESENTATION_NATIVE_OUTPUTS
    )
    assert (
        registry.get("paired-pss-glrt-presentation-native").spec.output_products
        == PAIRED_PSS_GLRT_PRESENTATION_NATIVE_OUTPUTS
    )
    alternate = registry.get("path-alternate-tracks-native").spec
    assert alternate.output_products == PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS
    assert ALTERNATE_CFO_TRACK_BANK_V5_PRODUCT in alternate.output_products
    assert ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT in alternate.output_products
    assert alternate.algorithm_version == "standard-native-path-projection-v7"
    assert alternate.configuration_schema == "path-alternate-tracks-native.projection.v7"
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
            NUMERICAL_WATERFALL_V4_PRODUCT,
            STATEFUL_PATH_V3_PRODUCT,
            PILOT_DOPPLER_SEGMENTS_V4_PRODUCT,
            FULL_CAPTURE_GLRT20MS_V2_PRODUCT,
            GLRT_FRACTIONAL_EPOCH_V1_PRODUCT,
            PATH_REPORT_V4_PRODUCT,
        )
    )
    assert sum(len(registry.get(key).spec.output_products) for key in registry.keys) == 42
    assert len(registry.get("path-standard-native").spec.output_products) == 9
