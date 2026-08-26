"""Executable evidence-only analyzers for the Standard-native vertical."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from leo.analysis.standard.configuration import (
    production_receiver_standard_config,
    require_receiver_standard_sample_rate,
)
from leo.analysis.standard.native_alternate_tracks import (
    build_standard_native_alternate_cfo_track_bank,
    render_standard_native_alternate_cfo_tracks_png,
)
from leo.analysis.standard.native_full_capture_glrt import (
    StandardNativeFullCaptureGlrtRunner,
    native_full_capture_glrt_configuration_digest,
)
from leo.analysis.standard.native_path_report import build_standard_native_path_report
from leo.analysis.standard.native_products import (
    ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT,
    ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
    NUMERICAL_WATERFALL_V3_PRODUCT,
    PAIRED_REPORT_V4_PRODUCT,
    PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
    PATH_REPORT_V3_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    QUALITY_V2_PRODUCT,
    RADIO_REPORT_V4_PRODUCT,
    STATEFUL_PATH_V2_PRODUCT,
    WATERFALL_PNG_V2_PRODUCT,
)
from leo.analysis.standard.native_reducers import (
    native_paired_waterfall_source,
    reduce_native_paired_terminal_evidence,
    reduce_native_radio_terminal_evidence,
)
from leo.analysis.standard.native_runner import run_standard_native_observability
from leo.analysis.standard.native_stateful import (
    StandardNativeStatefulRunner,
    build_standard_native_stateful_path_v2,
    stateful_global_schedule_is_publishable,
)
from leo.analysis.standard.runner import (
    ReceiverStandardConfig,
    receiver_standard_configuration_digest,
)
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.contracts.standard_pipeline import StandardPairInputBindV2, StandardPathInputBindV4
from leo.pipeline import (
    AnalysisContext,
    AnalyzerRegistry,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductSpec,
    ResourceClass,
    ScopeKind,
    StageOutcome,
    StageResult,
    StageSpec,
    ValidityAwareIqReader,
)
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import render_full_standard_plot_png

_NATIVE_EVIDENCE_PRODUCTS = (
    QUALITY_V2_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    NUMERICAL_WATERFALL_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    STATEFUL_PATH_V2_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
    PATH_REPORT_V3_PRODUCT,
)
_NATIVE_OUTCOMES = (
    StageOutcome.COMPLETE,
    StageOutcome.PARTIAL_COVERAGE,
    StageOutcome.INSUFFICIENT_DATA,
)
_ALTERNATE_NATIVE_OUTCOMES = (
    StageOutcome.COMPLETE,
    StageOutcome.NO_RESULT,
    StageOutcome.PARTIAL_COVERAGE,
    StageOutcome.INSUFFICIENT_DATA,
)


def _require_native_product(product: ProductSpec, producer_stage_key: str) -> ProductRequirement:
    return ProductRequirement(
        kind=product.kind,
        accepted_schema_versions=(product.schema_version,),
        producer_stage_key=producer_stage_key,
        require_available=True,
    )


class _QualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    block_samples: int = Field(default=262_144, ge=1, le=1_048_576)
    clipping_abs_threshold: int = Field(default=32_767, ge=1, le=32_768)


class _PowerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    block_samples: int = Field(default=262_144, ge=1, le=1_048_576)
    window_ms: int = Field(default=1_000, ge=1, le=60_000)


class _WaterfallConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fft_samples: int = 1024
    frequency_bins: int = 256
    maximum_time_bins: int = 512
    block_samples: int = 262_144
    floor_dbfs: float = -160.0

    def value(self) -> WaterfallConfig:
        return WaterfallConfig(**self.model_dump())


class _NativeEvidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quality: _QualityConfig = _QualityConfig()
    power: _PowerConfig = _PowerConfig()
    waterfall: _WaterfallConfig = _WaterfallConfig()
    stateful_configuration_digest: Sha256Digest = receiver_standard_configuration_digest(
        production_receiver_standard_config()
    )
    full_capture_glrt_configuration_digest: Sha256Digest = (
        native_full_capture_glrt_configuration_digest(production_receiver_standard_config())
    )


class _AlternateProjectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathStandardNativeEvidenceAnalyzer:
    """Publish the bounded native products whose gap semantics are reviewed."""

    spec = StageSpec(
        key="path-standard-native",
        algorithm_version="standard-native-evidence-v7",
        configuration_schema="path-standard-native.evidence.v6",
        output_products=_NATIVE_EVIDENCE_PRODUCTS,
        resource_class=ResourceClass.HEAVY,
        accepted_outcomes=_NATIVE_OUTCOMES,
    )

    def __init__(
        self,
        *,
        stateful_runner_factory: Callable[
            [ReceiverStandardConfig], StandardNativeStatefulRunner
        ] = StandardNativeStatefulRunner,
        full_capture_glrt_runner_factory: Callable[
            [ReceiverStandardConfig], StandardNativeFullCaptureGlrtRunner
        ] = StandardNativeFullCaptureGlrtRunner,
    ) -> None:
        self._stateful_runner_factory = stateful_runner_factory
        self._full_capture_glrt_runner_factory = full_capture_glrt_runner_factory

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        binding = StandardPathInputBindV4.model_validate(products.read_subject_binding())
        _require_native_path_context(context, binding)
        config = _NativeEvidenceConfig.model_validate(context.stage_config)
        base_config = production_receiver_standard_config()
        if (
            receiver_standard_configuration_digest(base_config)
            != config.stateful_configuration_digest
        ):
            raise ValueError("native stateful policy digest does not match implementation")
        if (
            native_full_capture_glrt_configuration_digest(base_config)
            != config.full_capture_glrt_configuration_digest
        ):
            raise ValueError(
                "native full-capture GLRT configuration digest does not match implementation"
            )
        stateful_config = require_receiver_standard_sample_rate(
            production_receiver_standard_config(sample_rate_hz=binding.sample_rate_hz),
            sample_rate_hz=binding.sample_rate_hz,
        )
        power_window_numerator = binding.sample_rate_hz * config.power.window_ms
        if power_window_numerator % 1_000:
            raise ValueError("native power window does not map to integral samples")
        native_iq = cast(ValidityAwareIqReader, iq)
        result = run_standard_native_observability(
            native_iq,
            binding,
            quality_block_samples=config.quality.block_samples,
            clipping_abs_threshold=config.quality.clipping_abs_threshold,
            power_block_samples=config.power.block_samples,
            power_window_samples=power_window_numerator // 1_000,
            waterfall_config=config.waterfall.value(),
            subwindow_ms=stateful_config.feedback.subwindow_ms,
            probe_ms=stateful_config.feedback.probe_ms,
            probe_offsets_ms=stateful_config.feedback.probe_offsets_ms,
            maximum_coarse_windows=stateful_config.feedback.maximum_outer_windows,
        )
        stateful_runner = self._stateful_runner_factory(stateful_config)
        if stateful_global_schedule_is_publishable(binding):
            stateful_result = stateful_runner.run(
                native_iq,
                binding,
                edge=binding.starlink_edge,
                qam_schedule=result.schedule,
            )
            stateful_schedule = None
        else:
            stateful_result = stateful_runner.run_global_probe_schedule(
                native_iq,
                binding,
                result.schedule,
                edge=binding.starlink_edge,
                capture_qam=True,
            )
            stateful_schedule = result.schedule
        stateful = build_standard_native_stateful_path_v2(
            stateful_result,
            binding,
            stateful_config,
            edge=binding.starlink_edge,
            schedule=stateful_schedule,
        )
        full_capture_glrt = self._full_capture_glrt_runner_factory(stateful_config).run(
            native_iq,
            binding,
            edge=binding.starlink_edge,
        )
        quality_document = cast(dict[str, JsonValue], result.quality.model_dump(mode="json"))
        power_document = cast(dict[str, JsonValue], result.power.model_dump(mode="json"))
        waterfall_document = cast(dict[str, JsonValue], result.waterfall.model_dump(mode="json"))
        schedule_document = cast(dict[str, JsonValue], result.schedule.model_dump(mode="json"))
        stateful_document = cast(dict[str, JsonValue], stateful.model_dump(mode="json"))
        glrt_document = cast(dict[str, JsonValue], full_capture_glrt.model_dump(mode="json"))
        path_report = build_standard_native_path_report(
            binding,
            quality=result.quality,
            quality_product_digest=canonical_digest(quality_document),
            power_timeline=result.power,
            power_timeline_product_digest=canonical_digest(power_document),
            numerical_waterfall=result.waterfall,
            numerical_waterfall_product_digest=canonical_digest(waterfall_document),
            probe_schedule=result.schedule,
            probe_schedule_product_digest=canonical_digest(schedule_document),
            stateful_path=stateful,
            stateful_path_product_digest=canonical_digest(stateful_document),
            full_capture_glrt20ms=full_capture_glrt,
            full_capture_glrt20ms_product_digest=canonical_digest(glrt_document),
            qam_probe_evidence=stateful_result.qam_probe_evidence,
        )
        path_report_document = cast(
            dict[str, JsonValue],
            path_report.model_dump(mode="json"),
        )
        documents: tuple[tuple[Any, dict[str, JsonValue]], ...] = (
            (
                QUALITY_V2_PRODUCT,
                quality_document,
            ),
            (
                POWER_TIMELINE_V3_PRODUCT,
                power_document,
            ),
            (
                NUMERICAL_WATERFALL_V3_PRODUCT,
                waterfall_document,
            ),
            (
                PROBE_SCHEDULE_V3_PRODUCT,
                schedule_document,
            ),
            (
                STATEFUL_PATH_V2_PRODUCT,
                stateful_document,
            ),
            (
                FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
                glrt_document,
            ),
            (PATH_REPORT_V3_PRODUCT, path_report_document),
        )
        published = tuple(
            outputs.publish_json(product, document) for product, document in documents
        )
        accounting = result.schedule.accounting
        boundary_count = len(binding.validity_inventory.segments) - 1
        outcome = (
            StageOutcome.COMPLETE
            if binding.missing_sample_count == 0 and boundary_count == 0
            else StageOutcome.PARTIAL_COVERAGE
        )
        return StageResult(
            outcome=outcome,
            products=published,
            summary={
                "coverage_fraction": (binding.observed_sample_count / binding.logical_sample_count),
                "observed_sample_count": binding.observed_sample_count,
                "missing_sample_count": binding.missing_sample_count,
                "continuity_boundary_count": boundary_count,
                "scheduled_probe_count": accounting.scheduled_count,
                "valid_probe_count": accounting.valid_count,
                "excluded_probe_count": accounting.scheduled_count - accounting.valid_count,
                "stateful_science_status": stateful.stateful_science_status,
                "stateful_analyzed_outer_window_count": (stateful.analyzed_outer_window_count),
                "full_capture_glrt_scheduled_window_count": (
                    full_capture_glrt.accounting.scheduled_count
                ),
                "full_capture_glrt_valid_window_count": (full_capture_glrt.accounting.valid_count),
                "full_capture_glrt_excluded_window_count": (
                    full_capture_glrt.accounting.scheduled_count
                    - full_capture_glrt.accounting.valid_count
                ),
                "full_capture_glrt_passing_window_count": (
                    full_capture_glrt.accounting.passing_count
                ),
                "terminal_probe_analyzed_count": (
                    path_report.schedule_execution.accounting.analyzed_count
                ),
                "native_qam_result_count": path_report.qam_statistics.qam_result_count,
                "scientific_disposition": path_report.scientific_disposition.value,
                "native_evidence_only": True,
            },
            message=(
                "Validity-aware native observability completed; stateful pilot/trajectory/"
                "Doppler and full-capture GLRT evidence were published on canonical "
                "global schedules and closed by the terminal path report."
                if stateful.stateful_science_status in {"complete", "partial_coverage"}
                else "Validity-aware native observability completed without stateful science."
            ),
        )


class PathAlternateTracksNativeAnalyzer:
    """Project sealed segment-local residual-Hough tracks without IQ access."""

    spec = StageSpec(
        key="path-alternate-tracks-native",
        algorithm_version="standard-native-alternate-cfo-projection-v2",
        configuration_schema="path-alternate-tracks-native.projection.v2",
        dependencies=("path-standard-native",),
        input_products=(_require_native_product(STATEFUL_PATH_V2_PRODUCT, "path-standard-native"),),
        output_products=PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
        resource_class=ResourceClass.CPU,
        accepted_outcomes=_ALTERNATE_NATIVE_OUTCOMES,
    )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        del iq
        _AlternateProjectionConfig.model_validate(context.stage_config)
        upstream = products.read_json_many(
            self.spec.input_products[0],
            producer_node_ids=context.dependency_node_ids,
        )
        if len(upstream) != 1:
            raise ValueError("native alternate projection requires one exact stateful predecessor")
        predecessor = upstream[0]
        if (
            context.dependency_node_ids != (predecessor.producer_node_id,)
            or context.scope is None
            or predecessor.producer_scope != context.scope
        ):
            raise ValueError("native alternate predecessor does not match the exact path node")
        stateful = StandardNativeStatefulPathV2.model_validate(predecessor.document)
        _require_native_source_context(context, stateful)
        bank = build_standard_native_alternate_cfo_track_bank(
            stateful,
            stateful_product_digest=predecessor.product_digest,
        )
        png = render_standard_native_alternate_cfo_tracks_png(bank)
        published = (
            outputs.publish_json(
                ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT,
                cast(dict[str, JsonValue], bank.model_dump(mode="json")),
            ),
            outputs.publish_bytes(ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT, png),
        )
        return StageResult(
            outcome=StageOutcome(bank.projection_status),
            products=published,
            summary={
                "coverage_fraction": (
                    stateful.source.observed_sample_count / stateful.source.logical_sample_count
                ),
                "continuity_segment_count": len(bank.segments),
                "source_observation_count": bank.source_observation_count,
                "detected_track_count": bank.detected_track_count,
                "returned_track_count": bank.returned_track_count,
                "truncated_track_count": bank.truncated_track_count,
                "stateful_science_status": bank.stateful_science_status,
                "native_evidence_only": True,
                "current_eligible": False,
                "cross_segment_association_permitted": False,
            },
            message=(
                "Projected exact segment-local residual-Hough candidates from sealed "
                "stateful evidence without IQ access or cross-segment association."
            ),
        )


class RadioStandardNativeEvidenceAnalyzer:
    """Reduce the exact processing-complete evidence from both paths of one radio."""

    spec = StageSpec(
        key="radio-scientific-report-native",
        algorithm_version="standard-native-radio-report-v6",
        configuration_schema="radio-scientific-report-native.evidence.v3",
        dependencies=("path-standard-native",),
        input_products=(
            _require_native_product(QUALITY_V2_PRODUCT, "path-standard-native"),
            _require_native_product(POWER_TIMELINE_V3_PRODUCT, "path-standard-native"),
            _require_native_product(NUMERICAL_WATERFALL_V3_PRODUCT, "path-standard-native"),
            _require_native_product(PROBE_SCHEDULE_V3_PRODUCT, "path-standard-native"),
            _require_native_product(STATEFUL_PATH_V2_PRODUCT, "path-standard-native"),
            _require_native_product(FULL_CAPTURE_GLRT20MS_V1_PRODUCT, "path-standard-native"),
            _require_native_product(PATH_REPORT_V3_PRODUCT, "path-standard-native"),
        ),
        output_products=(RADIO_REPORT_V4_PRODUCT,),
        resource_class=ResourceClass.CPU,
        accepted_outcomes=_NATIVE_OUTCOMES,
    )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        del iq
        upstream = tuple(
            products.read_json_many(
                requirement,
                producer_node_ids=context.dependency_node_ids,
            )
            for requirement in self.spec.input_products
        )
        report = reduce_native_radio_terminal_evidence(
            context,
            quality_products=upstream[0],
            power_products=upstream[1],
            waterfall_products=upstream[2],
            schedule_products=upstream[3],
            stateful_products=upstream[4],
            glrt_products=upstream[5],
            path_report_products=upstream[6],
        )
        published = outputs.publish_json(
            RADIO_REPORT_V4_PRODUCT,
            cast(dict[str, JsonValue], report.model_dump(mode="json")),
        )
        return StageResult(
            outcome=StageOutcome(report.status),
            products=(published,),
            summary={
                "receiver_path_count": len(report.paths),
                "valid_complex_sample_count": (
                    report.aggregate_statistics.valid_complex_sample_count
                ),
                "terminal_probe_analyzed_count": (
                    report.aggregate_terminal_opportunities.analyzed_count
                ),
                "qam_result_count": report.aggregate_qam_statistics.qam_result_count,
                "final_trajectory_count": (
                    report.aggregate_terminal_tracks.returned_trajectory_count
                ),
                "scientific_disposition": report.scientific_disposition.value,
                "valid_utc_interval_count": len(report.valid_utc_intervals),
                "native_evidence_only": True,
                "current_eligible": False,
            },
            message=report.reason,
        )


class PairedStandardNativeEvidenceAnalyzer:
    """Reduce two native radio reports over their exact common valid UTC support."""

    spec = StageSpec(
        key="paired-scientific-report-native",
        algorithm_version="standard-native-paired-report-v5",
        configuration_schema="paired-scientific-report-native.evidence.v3",
        dependencies=("radio-scientific-report-native",),
        input_products=(
            _require_native_product(RADIO_REPORT_V4_PRODUCT, "radio-scientific-report-native"),
        ),
        output_products=(PAIRED_REPORT_V4_PRODUCT,),
        resource_class=ResourceClass.CPU,
        accepted_outcomes=_NATIVE_OUTCOMES,
    )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        del iq
        binding = StandardPairInputBindV2.model_validate(products.read_subject_binding())
        upstream = products.read_json_many(
            self.spec.input_products[0],
            producer_node_ids=context.dependency_node_ids,
        )
        report = reduce_native_paired_terminal_evidence(
            context,
            pair_binding=binding,
            radio_products=upstream,
        )
        published = outputs.publish_json(
            PAIRED_REPORT_V4_PRODUCT,
            cast(dict[str, JsonValue], report.model_dump(mode="json")),
        )
        return StageResult(
            outcome=StageOutcome(report.status),
            products=(published,),
            summary={
                "radio_count": len(report.radios),
                "receiver_path_count": (report.aggregate_statistics.receiver_path_count),
                "valid_complex_sample_count": (
                    report.aggregate_statistics.valid_complex_sample_count
                ),
                "terminal_probe_analyzed_count": (
                    report.aggregate_terminal_opportunities.analyzed_count
                ),
                "qam_result_count": report.aggregate_qam_statistics.qam_result_count,
                "final_trajectory_count": (
                    report.aggregate_terminal_tracks.returned_trajectory_count
                ),
                "scientific_disposition": report.scientific_disposition.value,
                "common_valid_utc_interval_count": len(report.valid_utc_intervals),
                "common_valid_utc_ns": sum(
                    item.stop_utc_ns - item.start_utc_ns for item in report.valid_utc_intervals
                ),
                "native_evidence_only": True,
                "current_eligible": False,
            },
            message=report.reason,
        )


class PairedStandardNativeWaterfallAnalyzer:
    """Render the one currently truthful paired native presentation."""

    spec = StageSpec(
        key="paired-presentation-native",
        algorithm_version="standard-native-paired-waterfall-v2",
        configuration_schema="paired-presentation-native.evidence.v1",
        dependencies=("path-standard-native",),
        input_products=(
            _require_native_product(NUMERICAL_WATERFALL_V3_PRODUCT, "path-standard-native"),
        ),
        output_products=(WATERFALL_PNG_V2_PRODUCT,),
        resource_class=ResourceClass.CPU,
        accepted_outcomes=_NATIVE_OUTCOMES,
    )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        del iq
        upstream = products.read_json_many(
            self.spec.input_products[0],
            producer_node_ids=context.dependency_node_ids,
        )
        source = native_paired_waterfall_source(context, upstream)
        payload = render_full_standard_plot_png(source, StandardViewKindV2.WATERFALL)
        published = outputs.publish_bytes(WATERFALL_PNG_V2_PRODUCT, payload)
        outcome = (
            StageOutcome.COMPLETE
            if all(item.outcome is StageOutcome.COMPLETE for item in upstream)
            else StageOutcome.PARTIAL_COVERAGE
        )
        return StageResult(
            outcome=outcome,
            products=(published,),
            summary={
                "receiver_path_count": len(source.paths),
                "native_evidence_only": True,
                "current_eligible": False,
                "available_native_views": ["waterfall"],
                "unavailable_native_views": [
                    "pilot_methods",
                    "cfo_trajectories",
                    "dealiased_cfo_trajectories",
                    "final_cfo_trajectories",
                ],
            },
            message=(
                "Native waterfall presentation is evidence-only; pilot and trajectory "
                "views remain unavailable."
            ),
        )


def production_standard_native_evidence_registry() -> AnalyzerRegistry:
    """Build the non-promotable native vertical without changing Standard-v2."""

    analyzers = (
        PathStandardNativeEvidenceAnalyzer(),
        PathAlternateTracksNativeAnalyzer(),
        RadioStandardNativeEvidenceAnalyzer(),
        PairedStandardNativeEvidenceAnalyzer(),
        PairedStandardNativeWaterfallAnalyzer(),
    )
    return AnalyzerRegistry(analyzers)


def production_standard_native_evidence_configuration() -> dict[str, dict[str, JsonValue]]:
    """Return the closed native stage configuration embedded in release authority."""

    registry = production_standard_native_evidence_registry()
    configuration: dict[str, dict[str, JsonValue]] = {key: {} for key in registry.keys}
    configuration["path-standard-native"] = cast(
        dict[str, JsonValue], _NativeEvidenceConfig().model_dump(mode="json")
    )
    return configuration


def _require_native_path_context(
    context: AnalysisContext,
    binding: StandardPathInputBindV4,
) -> None:
    scope = context.scope
    if (
        scope is None
        or scope.kind is not ScopeKind.RECEIVER_PATH
        or (scope.session_id, scope.stream_id, scope.receiver_id)
        != (binding.session_id, binding.stream_id, binding.receiver_id)
    ):
        raise ValueError("native path input binding does not match the exact analyzer scope")


def _require_native_source_context(
    context: AnalysisContext,
    stateful: StandardNativeStatefulPathV2,
) -> None:
    source = stateful.source
    scope = context.scope
    if (
        scope is None
        or scope.kind is not ScopeKind.RECEIVER_PATH
        or (scope.session_id, scope.stream_id, scope.receiver_id)
        != (source.session_id, source.stream_id, source.receiver_id)
    ):
        raise ValueError("native alternate stateful source does not match the analyzer scope")
