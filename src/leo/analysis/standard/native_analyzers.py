"""Executable evidence-only analyzers for the Standard-native vertical."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from leo.analysis.qam.pilot_phase_locklet import PilotPhaseLockletConfig
from leo.analysis.standard.configuration import (
    production_receiver_standard_config,
    require_receiver_standard_sample_rate,
)
from leo.analysis.standard.native_accounting import (
    build_standard_native_trajectory_accounting_v3,
    render_standard_native_trajectory_accounting_png,
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
from leo.analysis.standard.native_pilot_doppler import (
    build_standard_native_pilot_doppler_segments_v3,
)
from leo.analysis.standard.native_pngs import (
    native_standard_png_source,
    render_standard_native_common_pngs,
    render_standard_native_full_capture_glrt_png,
    render_standard_native_pilot_diagnostics_pngs,
)
from leo.analysis.standard.native_products import (
    ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT,
    ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
    FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
    NUMERICAL_WATERFALL_V3_PRODUCT,
    PAIRED_PRESENTATION_NATIVE_OUTPUTS,
    PAIRED_REPORT_V6_PRODUCT,
    PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
    PATH_REPORT_V3_PRODUCT,
    PATH_STANDARD_NATIVE_OUTPUTS,
    PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT,
    PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT,
    PILOT_DOPPLER_SEGMENTS_V3_PRODUCT,
    PILOT_SEGMENT_RATES_PNG_V4_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    QUALITY_V2_PRODUCT,
    RADIO_REPORT_V5_PRODUCT,
    RADIO_SCIENTIFIC_NATIVE_OUTPUTS,
    STATEFUL_PATH_V2_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_V3_PRODUCT,
)
from leo.analysis.standard.native_reducers import (
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
from leo.contracts.pilot_doppler_segments import (
    PilotPhaseLockletConfigV1,
    StandardPilotDopplerSegmentsV3,
)
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV1
from leo.contracts.standard_native_path_report import StandardNativePathReportV3
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.contracts.standard_native_terminal import StandardNativePairedReportV6
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

_NATIVE_EVIDENCE_PRODUCTS = PATH_STANDARD_NATIVE_OUTPUTS
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
    pilot_phase_locklet_configuration_digest: Sha256Digest = (
        PilotPhaseLockletConfigV1.model_validate(asdict(PilotPhaseLockletConfig())).digest
    )


class _AlternateProjectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathStandardNativeEvidenceAnalyzer:
    """Publish the bounded native products whose gap semantics are reviewed."""

    spec = StageSpec(
        key="path-standard-native",
        algorithm_version="standard-native-evidence-v9",
        configuration_schema="path-standard-native.evidence.v7",
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
        if PilotPhaseLockletConfigV1.model_validate(asdict(PilotPhaseLockletConfig())).digest != (
            config.pilot_phase_locklet_configuration_digest
        ):
            raise ValueError(
                "native pilot phase-locklet policy digest does not match implementation"
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
        stateful_product_digest = canonical_digest(stateful_document)
        pilot_doppler_v3 = build_standard_native_pilot_doppler_segments_v3(
            stateful_result,
            binding,
            stateful,
            stateful_path_product_digest=stateful_product_digest,
            config=stateful_config,
            edge=binding.starlink_edge,
        )
        if pilot_doppler_v3.phase_config_digest != config.pilot_phase_locklet_configuration_digest:
            raise ValueError(
                "native pilot phase-locklet product used an unpinned implementation policy"
            )
        pilot_doppler_v3_document = cast(
            dict[str, JsonValue],
            pilot_doppler_v3.model_dump(mode="json"),
        )
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
            stateful_path_product_digest=stateful_product_digest,
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
                PILOT_DOPPLER_SEGMENTS_V3_PRODUCT,
                pilot_doppler_v3_document,
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
                "pilot_doppler_v3_phase_trackability_count": (
                    pilot_doppler_v3.corrected_phase_trackability_count
                ),
                "pilot_doppler_v3_qualified_segment_count": (
                    pilot_doppler_v3.qualified_segment_count
                ),
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
        algorithm_version="standard-native-path-projection-v4",
        configuration_schema="path-alternate-tracks-native.projection.v4",
        dependencies=("path-standard-native",),
        input_products=(
            _require_native_product(NUMERICAL_WATERFALL_V3_PRODUCT, "path-standard-native"),
            _require_native_product(STATEFUL_PATH_V2_PRODUCT, "path-standard-native"),
            _require_native_product(PILOT_DOPPLER_SEGMENTS_V3_PRODUCT, "path-standard-native"),
            _require_native_product(FULL_CAPTURE_GLRT20MS_V1_PRODUCT, "path-standard-native"),
            _require_native_product(PATH_REPORT_V3_PRODUCT, "path-standard-native"),
        ),
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
        inventories = tuple(
            products.read_json_many(
                requirement,
                producer_node_ids=context.dependency_node_ids,
            )
            for requirement in self.spec.input_products
        )
        if any(len(items) != 1 for items in inventories):
            raise ValueError("native path projection requires one exact product inventory")
        waterfall_item, predecessor, pilot_v3_item, glrt_item, report_item = (
            items[0] for items in inventories
        )
        if (
            context.dependency_node_ids != (predecessor.producer_node_id,)
            or context.scope is None
            or predecessor.producer_scope != context.scope
            or any(
                item.producer_node_id != predecessor.producer_node_id
                or item.producer_scope != context.scope
                for item in (waterfall_item, pilot_v3_item, glrt_item, report_item)
            )
        ):
            raise ValueError("native projection predecessor does not match the exact path node")
        stateful = StandardNativeStatefulPathV2.model_validate(predecessor.document)
        pilot_v3 = StandardPilotDopplerSegmentsV3.model_validate(pilot_v3_item.document)
        if (
            pilot_v3.source != stateful.source
            or pilot_v3.stateful_path_product_digest != predecessor.product_digest
            or pilot_v3.stateful_path_digest != stateful.stateful_path_digest
            or pilot_v3.starlink_edge != stateful.starlink_edge
        ):
            raise ValueError("native pilot Doppler V3 lineage does not close")
        _require_native_pilot_v3_v2_lineage(stateful, pilot_v3)
        _require_native_source_context(context, stateful)
        config = require_receiver_standard_sample_rate(
            production_receiver_standard_config(sample_rate_hz=stateful.source.sample_rate_hz),
            sample_rate_hz=stateful.source.sample_rate_hz,
        )
        if pilot_v3.science_configuration_digest != receiver_standard_configuration_digest(config):
            raise ValueError("native pilot Doppler V3 science policy does not close")
        bank = build_standard_native_alternate_cfo_track_bank(
            stateful,
            stateful_product_digest=predecessor.product_digest,
        )
        accounting = build_standard_native_trajectory_accounting_v3(
            stateful,
            configuration=config.trajectory_accounting,
        )
        source = native_standard_png_source(
            context,
            waterfall_products=(waterfall_item,),
            stateful_products=(predecessor,),
            path_report_products=(report_item,),
            config=config,
        )
        common_pngs = render_standard_native_common_pngs(source)
        path_label = source.paths[0].label
        pilot_pngs = render_standard_native_pilot_diagnostics_pngs(
            stateful,
            pilot_v3=pilot_v3,
            config=config,
            path_label=path_label,
        )
        glrt = StandardNativeFullCaptureGlrt20msV1.model_validate(glrt_item.document)
        if (
            glrt.source != stateful.source
            or glrt_item.product_digest
            != StandardNativePathReportV3.model_validate(
                report_item.document
            ).products.full_capture_glrt20ms_product_digest
        ):
            raise ValueError("native GLRT projection lineage does not close")
        documents = (
            (
                ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT,
                cast(dict[str, JsonValue], bank.model_dump(mode="json")),
            ),
            (
                TRAJECTORY_CONDITIONED_ACCOUNTING_V3_PRODUCT,
                cast(dict[str, JsonValue], accounting.model_dump(mode="json")),
            ),
        )
        payloads = (
            *common_pngs,
            (
                ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
                render_standard_native_alternate_cfo_tracks_png(bank),
            ),
            (
                TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT,
                render_standard_native_trajectory_accounting_png(
                    accounting,
                    path_label=path_label,
                ),
            ),
            (
                FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT,
                render_standard_native_full_capture_glrt_png(
                    glrt,
                    config=config,
                    path_label=path_label,
                ),
            ),
            (PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT, pilot_pngs[0]),
            (PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT, pilot_pngs[1]),
            (PILOT_SEGMENT_RATES_PNG_V4_PRODUCT, pilot_pngs[2]),
        )
        published = tuple(
            outputs.publish_json(product, document) for product, document in documents
        ) + tuple(outputs.publish_bytes(product, payload) for product, payload in payloads)
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
        algorithm_version="standard-native-radio-report-presentation-v8",
        configuration_schema="radio-scientific-report-native.evidence.v5",
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
        output_products=RADIO_SCIENTIFIC_NATIVE_OUTPUTS,
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
        if not upstream[4]:
            raise ValueError("native radio presentation has no stateful path source")
        stateful = StandardNativeStatefulPathV2.model_validate(upstream[4][0].document)
        config = require_receiver_standard_sample_rate(
            production_receiver_standard_config(sample_rate_hz=stateful.source.sample_rate_hz),
            sample_rate_hz=stateful.source.sample_rate_hz,
        )
        source = native_standard_png_source(
            context,
            waterfall_products=upstream[2],
            stateful_products=upstream[4],
            path_report_products=upstream[6],
            config=config,
        )
        payloads = render_standard_native_common_pngs(source)
        report_document = cast(dict[str, JsonValue], report.model_dump(mode="json"))
        published = (
            outputs.publish_json(RADIO_REPORT_V5_PRODUCT, report_document),
            *(outputs.publish_bytes(product, payload) for product, payload in payloads),
        )
        return StageResult(
            outcome=StageOutcome(report.status),
            products=published,
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
        algorithm_version="standard-native-paired-report-v7",
        configuration_schema="paired-scientific-report-native.evidence.v5",
        dependencies=("radio-scientific-report-native",),
        input_products=(
            _require_native_product(RADIO_REPORT_V5_PRODUCT, "radio-scientific-report-native"),
        ),
        output_products=(PAIRED_REPORT_V6_PRODUCT,),
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
            PAIRED_REPORT_V6_PRODUCT,
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
    """Render all five common native views over exact paired path evidence."""

    spec = StageSpec(
        key="paired-presentation-native",
        algorithm_version="standard-native-paired-presentation-v6",
        configuration_schema="paired-presentation-native.evidence.v5",
        dependencies=("path-standard-native", "paired-scientific-report-native"),
        input_products=(
            _require_native_product(NUMERICAL_WATERFALL_V3_PRODUCT, "path-standard-native"),
            _require_native_product(STATEFUL_PATH_V2_PRODUCT, "path-standard-native"),
            _require_native_product(PATH_REPORT_V3_PRODUCT, "path-standard-native"),
            _require_native_product(
                PAIRED_REPORT_V6_PRODUCT,
                "paired-scientific-report-native",
            ),
        ),
        output_products=PAIRED_PRESENTATION_NATIVE_OUTPUTS,
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
        if len(upstream[3]) != 1:
            raise ValueError("native paired presentation requires one exact paired report")
        paired_item = upstream[3][0]
        paired = StandardNativePairedReportV6.model_validate(paired_item.document)
        if (
            context.scope is None
            or context.scope.kind is not ScopeKind.PAIRED
            or paired_item.producer_scope != context.scope
            or paired.session_id != context.session_id
            or paired.synchronization_inventory_digest
            != context.scope.synchronization_inventory_digest
        ):
            raise ValueError("native paired presentation report authority does not close")
        if not upstream[1]:
            raise ValueError("native paired presentation has no stateful path source")
        stateful_documents = tuple(
            StandardNativeStatefulPathV2.model_validate(item.document) for item in upstream[1]
        )
        stateful = stateful_documents[0]
        configurations = {
            item.source.sample_rate_hz: require_receiver_standard_sample_rate(
                production_receiver_standard_config(sample_rate_hz=item.source.sample_rate_hz),
                sample_rate_hz=item.source.sample_rate_hz,
            )
            for item in stateful_documents
        }
        config = require_receiver_standard_sample_rate(
            production_receiver_standard_config(sample_rate_hz=stateful.source.sample_rate_hz),
            sample_rate_hz=stateful.source.sample_rate_hz,
        )
        source = native_standard_png_source(
            context,
            waterfall_products=upstream[0],
            stateful_products=upstream[1],
            path_report_products=upstream[2],
            config=config,
            configs_by_sample_rate_hz=configurations,
            valid_utc_intervals=tuple(
                (item.start_utc_ns, item.stop_utc_ns) for item in paired.valid_utc_intervals
            ),
            preserve_per_path_waterfall=True,
        )
        payloads = render_standard_native_common_pngs(source)
        published = tuple(outputs.publish_bytes(product, payload) for product, payload in payloads)
        outcome = (
            StageOutcome.COMPLETE if paired.status == "complete" else StageOutcome.PARTIAL_COVERAGE
        )
        return StageResult(
            outcome=outcome,
            products=published,
            summary={
                "receiver_path_count": len(source.paths),
                "native_evidence_only": True,
                "current_eligible": False,
                "available_native_views": [
                    "waterfall",
                    "pilot_methods",
                    "cfo_trajectories",
                    "dealiased_cfo_trajectories",
                    "final_cfo_trajectories",
                ],
            },
            message=(
                "Five common native views were projected from sealed path evidence under "
                "the paired terminal support authority."
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


def _require_native_pilot_v3_v2_lineage(
    stateful: StandardNativeStatefulPathV2,
    pilot_v3: StandardPilotDopplerSegmentsV3,
) -> None:
    """Prove the sibling has exactly one unmodified binding for every nested V2 locklet."""

    local_science = tuple(
        item.local_science for item in stateful.segments if item.local_science is not None
    )
    expected_truncation = any(
        item.pilot_doppler_segments.truncated_track_count for item in local_science
    )
    if (
        pilot_v3.source_stateful_science_status != stateful.stateful_science_status
        or pilot_v3.bounded_local_track_truncation_present != expected_truncation
        or pilot_v3.analyzed_continuity_segment_count != len(local_science)
    ):
        raise ValueError("native pilot Doppler V3 stateful coverage lineage does not close")
    expected: dict[tuple[int, str, int], tuple[Any, Any]] = {}
    for persisted in stateful.segments:
        if persisted.local_science is None:
            continue
        source_v2 = persisted.local_science.pilot_doppler_segments
        for source_segment in source_v2.segments:
            key = (
                persisted.continuity_segment_index,
                source_v2.content_digest,
                source_segment.segment_index,
            )
            expected[key] = (persisted, source_segment)
    actual = {
        (
            item.continuity_segment_index,
            item.source_v2_pilot_doppler_content_digest,
            item.source_v2_segment_index,
        ): item
        for item in pilot_v3.segments
    }
    if len(actual) != len(pilot_v3.segments) or set(actual) != set(expected):
        raise ValueError("native pilot Doppler V3 omitted or duplicated source V2 locklets")

    for key, item in actual.items():
        persisted, source = expected[key]
        global_offset_s = persisted.global_device_sample_start / stateful.source.sample_rate_hz
        legacy_nonphase_failures = tuple(
            failure
            for failure in source.qualification_failures
            if failure != "modulo-pi phase lock did not qualify"
        )
        v3_nonphase_failures = tuple(
            failure
            for failure in item.qualification_failures
            if failure != "held-out modulo-pi phase trackability did not qualify"
        )
        exact_pairs = (
            (item.source_trajectory_id, source.source_trajectory_id),
            (item.source_branch_id, source.source_branch_id),
            (item.lattice_frame_count, source.lattice_frame_count),
            (item.complete_frame_count, source.lattice_frame_count),
            (item.supported_frame_count, source.supported_frame_count),
            (item.legacy_v2_phase_lock_qualified, source.phase_lock_qualified),
            (item.legacy_v2_qualified, source.qualified),
            (item.legacy_v2_phase_update_count, source.phase_update_count),
            (item.legacy_v2_reacquisition_count, source.reacquisition_count),
            (item.legacy_v2_filter_version, source.filter_version),
            (v3_nonphase_failures, legacy_nonphase_failures),
        )
        optional_float_pairs = (
            (item.supported_frame_fraction, source.supported_frame_fraction),
            (item.maximum_supported_frame_gap_s, source.maximum_supported_frame_gap_s),
            (item.median_exact_coherence, source.median_exact_coherence),
            (item.median_control_coherence, source.median_control_coherence),
            (item.median_coherence_margin, source.median_coherence_margin),
            (item.local_cfo_at_reference_hz, source.local_cfo_at_reference_hz),
            (item.local_doppler_rate_hz_s, source.local_doppler_rate_hz_s),
            (item.local_doppler_rate_sigma_hz_s, source.local_doppler_rate_sigma_hz_s),
            (item.frequency_line_rms_hz, source.frequency_line_rms_hz),
            (item.held_out_frequency_rms_hz, source.held_out_frequency_rms_hz),
            (item.frozen_cfo_at_reference_hz, source.frozen_cfo_at_reference_hz),
            (item.frozen_doppler_rate_hz_s, source.frozen_doppler_rate_hz_s),
            (item.local_minus_frozen_rate_hz_s, source.local_minus_frozen_rate_hz_s),
            (
                item.legacy_v2_phase_innovation_rms_rad,
                source.phase_innovation_rms_rad,
            ),
            (
                item.legacy_v2_kalman_doppler_rate_hz_s,
                source.kalman_doppler_rate_hz_s,
            ),
            (item.global_start_time_s, global_offset_s + source.start_time_s),
            (item.global_end_time_s, global_offset_s + source.end_time_s),
            (item.global_reference_time_s, global_offset_s + source.reference_time_s),
        )
        if (
            any(left != right for left, right in exact_pairs)
            or item.global_source_probe_sample_start
            != persisted.global_device_sample_start + source.source_probe_sample_start
            or any(
                not _same_optional_measurement(left, right) for left, right in optional_float_pairs
            )
        ):
            raise ValueError("native pilot Doppler V3 changed its source V2 segment")


def _same_optional_measurement(left: float | None, right: float | None) -> bool:
    return (left is None) == (right is None) and (
        left is None or right is None or math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-6)
    )
