"""Executable evidence-only analyzers for the Standard-native vertical."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from leo.analysis.standard.native_products import (
    NUMERICAL_WATERFALL_V3_PRODUCT,
    PAIRED_REPORT_V3_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    QUALITY_V2_PRODUCT,
    RADIO_REPORT_V3_PRODUCT,
    STATEFUL_PATH_V1_PRODUCT,
    WATERFALL_PNG_V2_PRODUCT,
)
from leo.analysis.standard.native_reducers import (
    native_paired_waterfall_source,
    reduce_native_paired_evidence,
    reduce_native_radio_evidence,
)
from leo.analysis.standard.native_runner import run_standard_native_observability
from leo.analysis.standard.native_stateful import (
    StandardNativeStatefulRunner,
    build_standard_native_stateful_path,
    build_unavailable_standard_native_stateful_path,
    stateful_global_schedule_is_publishable,
)
from leo.analysis.standard.runner import (
    ReceiverStandardConfig,
    receiver_standard_configuration_digest,
)
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import Sha256Digest
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
    STATEFUL_PATH_V1_PRODUCT,
)
_NATIVE_OUTCOMES = (
    StageOutcome.COMPLETE,
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


class _ProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subwindow_ms: int = Field(default=50, ge=1, le=1_000)
    probe_ms: int = Field(default=20, ge=1, le=1_000)
    probe_offsets_ms: tuple[int, ...] = (0, 25)
    maximum_coarse_windows: int = Field(default=120, ge=1, le=86_400)


class _NativeEvidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quality: _QualityConfig = _QualityConfig()
    power: _PowerConfig = _PowerConfig()
    waterfall: _WaterfallConfig = _WaterfallConfig()
    probes: _ProbeConfig = _ProbeConfig()
    stateful_configuration_digest: Sha256Digest = receiver_standard_configuration_digest(
        ReceiverStandardConfig()
    )


class PathStandardNativeEvidenceAnalyzer:
    """Publish the bounded native products whose gap semantics are reviewed."""

    spec = StageSpec(
        key="path-standard-native",
        algorithm_version="standard-native-evidence-v2",
        configuration_schema="path-standard-native.evidence.v2",
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
    ) -> None:
        self._stateful_runner_factory = stateful_runner_factory

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
        stateful_config = ReceiverStandardConfig()
        if (
            receiver_standard_configuration_digest(stateful_config)
            != config.stateful_configuration_digest
        ):
            raise ValueError("native stateful configuration digest does not match implementation")
        power_window_numerator = binding.sample_rate_hz * config.power.window_ms
        if power_window_numerator % 1_000:
            raise ValueError("native power window does not map to integral samples")
        native_iq = cast(ValidityAwareIqReader, iq)
        if stateful_global_schedule_is_publishable(binding):
            stateful_result = self._stateful_runner_factory(stateful_config).run(
                native_iq,
                binding,
                edge=binding.starlink_edge,
            )
            stateful = build_standard_native_stateful_path(
                stateful_result,
                binding,
                stateful_config,
                edge=binding.starlink_edge,
            )
        else:
            stateful = build_unavailable_standard_native_stateful_path(
                binding,
                stateful_config,
                edge=binding.starlink_edge,
            )
        result = run_standard_native_observability(
            native_iq,
            binding,
            quality_block_samples=config.quality.block_samples,
            clipping_abs_threshold=config.quality.clipping_abs_threshold,
            power_block_samples=config.power.block_samples,
            power_window_samples=power_window_numerator // 1_000,
            waterfall_config=config.waterfall.value(),
            subwindow_ms=config.probes.subwindow_ms,
            probe_ms=config.probes.probe_ms,
            probe_offsets_ms=config.probes.probe_offsets_ms,
            maximum_coarse_windows=config.probes.maximum_coarse_windows,
        )
        documents: tuple[tuple[Any, dict[str, JsonValue]], ...] = (
            (
                QUALITY_V2_PRODUCT,
                cast(dict[str, JsonValue], result.quality.model_dump(mode="json")),
            ),
            (
                POWER_TIMELINE_V3_PRODUCT,
                cast(dict[str, JsonValue], result.power.model_dump(mode="json")),
            ),
            (
                NUMERICAL_WATERFALL_V3_PRODUCT,
                cast(dict[str, JsonValue], result.waterfall.model_dump(mode="json")),
            ),
            (
                PROBE_SCHEDULE_V3_PRODUCT,
                cast(dict[str, JsonValue], result.schedule.model_dump(mode="json")),
            ),
            (
                STATEFUL_PATH_V1_PRODUCT,
                cast(dict[str, JsonValue], stateful.model_dump(mode="json")),
            ),
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
                "native_evidence_only": True,
            },
            message=(
                "Validity-aware native observability completed; stateful pilot/trajectory/"
                "Doppler evidence was published on the canonical global schedule."
                if stateful.stateful_science_status == "complete"
                else "Validity-aware native observability completed; gapped stateful science "
                "is explicitly unavailable until kernels consume the canonical global schedule."
            ),
        )


class _UnavailableNativeAnalyzer:
    """Explicit terminal for a native stage whose numerical contract is not reviewed."""

    def __init__(
        self,
        key: str,
        *,
        dependencies: tuple[str, ...],
        resource_class: ResourceClass,
    ) -> None:
        self.spec = StageSpec(
            key=key,
            algorithm_version="standard-native-unavailable-v1",
            configuration_schema=f"{key}.unavailable.v1",
            dependencies=dependencies,
            output_products=(),
            resource_class=resource_class,
            accepted_outcomes=(StageOutcome.INSUFFICIENT_DATA,),
        )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        del context, iq, products, outputs
        return StageResult(
            outcome=StageOutcome.INSUFFICIENT_DATA,
            summary={"native_stage_available": False, "native_evidence_only": True},
            message="This native scientific stage is not yet generalized and publishes no product.",
        )


class RadioStandardNativeEvidenceAnalyzer:
    """Reduce the exact five-product evidence from both paths of one radio."""

    spec = StageSpec(
        key="radio-scientific-report-native",
        algorithm_version="standard-native-radio-report-v3",
        configuration_schema="radio-scientific-report-native.evidence.v1",
        dependencies=("path-standard-native",),
        input_products=(
            _require_native_product(QUALITY_V2_PRODUCT, "path-standard-native"),
            _require_native_product(POWER_TIMELINE_V3_PRODUCT, "path-standard-native"),
            _require_native_product(NUMERICAL_WATERFALL_V3_PRODUCT, "path-standard-native"),
            _require_native_product(PROBE_SCHEDULE_V3_PRODUCT, "path-standard-native"),
            _require_native_product(STATEFUL_PATH_V1_PRODUCT, "path-standard-native"),
        ),
        output_products=(RADIO_REPORT_V3_PRODUCT,),
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
        report = reduce_native_radio_evidence(
            context,
            quality_products=upstream[0],
            power_products=upstream[1],
            waterfall_products=upstream[2],
            schedule_products=upstream[3],
            stateful_products=upstream[4],
        )
        published = outputs.publish_json(
            RADIO_REPORT_V3_PRODUCT,
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
        algorithm_version="standard-native-paired-report-v3",
        configuration_schema="paired-scientific-report-native.evidence.v1",
        dependencies=("radio-scientific-report-native",),
        input_products=(
            _require_native_product(RADIO_REPORT_V3_PRODUCT, "radio-scientific-report-native"),
        ),
        output_products=(PAIRED_REPORT_V3_PRODUCT,),
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
        report = reduce_native_paired_evidence(
            context,
            pair_binding=binding,
            radio_products=upstream,
        )
        published = outputs.publish_json(
            PAIRED_REPORT_V3_PRODUCT,
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
        _UnavailableNativeAnalyzer(
            "path-alternate-tracks-native",
            dependencies=("path-standard-native",),
            resource_class=ResourceClass.CPU,
        ),
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
