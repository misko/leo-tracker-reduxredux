"""Production analyzers for the frozen Standard-v2 expanded DAG."""

from __future__ import annotations

from dataclasses import fields
from typing import Any, cast

from pydantic import JsonValue

from leo.analysis.quality import QualityAnalyzer, QualityConfig
from leo.analysis.standard.alternate_tracks import (
    build_alternate_cfo_tracks,
    default_alternate_cfo_config,
    render_alternate_cfo_tracks_png,
)
from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.final_reports import reduce_paired_radios_v2, reduce_radio_v2
from leo.analysis.standard.observability import measure_power_timeline, numerical_waterfall_document
from leo.analysis.standard.probes import build_probe_schedule
from leo.analysis.standard.products import (
    ALTERNATE_CFO_TRACK_BANK_PRODUCT,
    ALTERNATE_CFO_TRACK_INPUT,
    ALTERNATE_CFO_TRACKS_PNG_PRODUCT,
    CFO_ALIAS_MAP_PRODUCT,
    CFO_LIFT_REPLAY_PRODUCT,
    CFO_TRAJECTORIES_PNG_PRODUCT,
    DEALIASED_CFO_TRAJECTORIES_PNG_PRODUCT,
    DEALIASED_TRAJECTORY_BANK_PRODUCT,
    FINAL_CFO_TRAJECTORIES_PNG_PRODUCT,
    FINAL_TRAJECTORY_BANK_PRODUCT,
    GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT,
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PAIRED_REPORT_INPUT,
    PAIRED_REPORT_PRODUCT,
    PATH_INPUT_BIND_PRODUCT,
    PATH_PRESENTATION_INPUTS,
    PATH_PRESENTATION_PRODUCT,
    PATH_REPORT_INPUTS,
    PATH_REPORT_PRODUCT,
    PILOT_METHODS_PNG_PRODUCT,
    PILOT_SCAN_PRODUCT,
    POWER_TIMELINE_PRODUCT,
    PROBE_SCHEDULE_PRODUCT,
    QUALITY_PRODUCT,
    RADIO_REPORT_PRODUCT,
    STANDARD_PNG_PRODUCTS,
    TRAJECTORY_BANK_PRODUCT,
    TRAJECTORY_FEEDBACK_PRODUCT,
    WATERFALL_PNG_PRODUCT,
)
from leo.analysis.standard.reports import (
    PathReportInputs,
    build_path_standard_report,
    standard_v2_trajectory_documents,
)
from leo.analysis.standard.runner import ReceiverStandardConfig, run_receiver_standard
from leo.analysis.standard.source_bindings import (
    STANDARD_FINAL_SOURCE_BINDING_SPECS,
    STANDARD_SOURCE_BINDING_SPECS,
    build_standard_source_binding,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.cfo_dealias import default_cfo_dealias_config, default_replay_gate_v3
from leo.analysis.starlink.multi_target import default_multi_target_association_config
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryFamily,
    default_trajectory_bank_config,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_pilot_trajectories,
    replay_pilot_trajectories,
    scan_pilot_detections,
    validate_trajectory_feedback_config,
)
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.alternate_cfo_tracks import AlternateCfoLineFinderConfigV1
from leo.contracts.cfo_dealias import CfoDealiasConfigV1, ReplayGateConfigV3
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.final_trajectory_reports import (
    PathStandardReportV2,
    RadioStandardReportV2,
)
from leo.contracts.multi_target import MultiTargetAssociationConfigV1
from leo.contracts.standard_pipeline import (
    ProbeScheduleV2,
    StandardPairInputBindV2,
    StandardPathInputBindV3,
    StandardSourceBindingV1,
)
from leo.pipeline import (
    AnalysisContext,
    AnalyzerRegistry,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductRole,
    ProductSpec,
    PublishedProduct,
    ResourceClass,
    ScopeKind,
    StageOutcome,
    StageResult,
    StageSpec,
    UpstreamJsonProduct,
)
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import (
    StandardPngPathSource,
    StandardPngSource,
    render_full_cfo_stage_png,
    render_full_standard_plot_png,
)

_MEMBERSHIP_KEY = "standard_source_bindings"
_COMMON_OUTCOMES = (
    StageOutcome.COMPLETE,
    StageOutcome.NO_RESULT,
    StageOutcome.PARTIAL_COVERAGE,
    StageOutcome.INSUFFICIENT_DATA,
)


def _spec(
    key: str,
    *,
    algorithm_version: str = "standard-v2-production-1",
    dependencies: tuple[str, ...] = (),
    inputs: tuple[ProductRequirement, ...] = (),
    outputs: tuple[ProductSpec, ...],
    resource: ResourceClass,
) -> StageSpec:
    return StageSpec(
        key=key,
        algorithm_version=algorithm_version,
        configuration_schema=f"{key}.v1",
        dependencies=dependencies,
        input_products=inputs,
        output_products=outputs,
        resource_class=resource,
        accepted_outcomes=_COMMON_OUTCOMES,
    )


class PathInputBindAnalyzer:
    spec = _spec(
        "path-input-bind", outputs=(PATH_INPUT_BIND_PRODUCT,), resource=ResourceClass.STREAMING
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        _require_path_context(context, binding)
        return _publish(outputs, PATH_INPUT_BIND_PRODUCT, binding.model_dump(mode="json"))


class PathQualityAnalyzer:
    spec = _spec(
        "path-quality",
        dependencies=("path-input-bind",),
        inputs=(
            ProductRequirement(
                kind=PATH_INPUT_BIND_PRODUCT.kind,
                accepted_schema_versions=(PATH_INPUT_BIND_PRODUCT.schema_version,),
                producer_stage_key="path-input-bind",
                require_available=True,
            ),
        ),
        outputs=(QUALITY_PRODUCT,),
        resource=ResourceClass.STREAMING,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        binding = _path_binding(products, self.spec.input_products[0], context)
        _require_iq(binding, iq)
        sink = _DocumentSink()
        result = QualityAnalyzer().analyze(
            context.model_copy(
                update={
                    "stage_config": QualityConfig.model_validate(context.stage_config).model_dump(
                        mode="json"
                    )
                }
            ),
            iq,
            products,
            sink,
        )
        document = decode_standard_product(QUALITY_PRODUCT, sink.document(QUALITY_PRODUCT))
        wrapper = _root_binding(QUALITY_PRODUCT, document, binding)
        published = outputs.publish_json(QUALITY_PRODUCT, cast(dict[str, JsonValue], document))
        return result.model_copy(update={"products": (published,), "summary": _membership(wrapper)})


class PathPowerAnalyzer:
    spec = _spec(
        "path-power",
        dependencies=("path-quality",),
        inputs=(
            ProductRequirement(
                kind=QUALITY_PRODUCT.kind, producer_stage_key="path-quality", require_available=True
            ),
        ),
        outputs=(POWER_TIMELINE_PRODUCT,),
        resource=ResourceClass.STREAMING,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        quality = _bound(products, self.spec.input_products[0])
        _require_same_path_iq(context, quality, iq)
        if (
            quality.document["sample_rate_hz"] != iq.sample_rate_hz
            or quality.document["expected_sample_count"] != iq.sample_count
            or [
                item["receiver_id"]
                for item in cast(list[dict[str, Any]], quality.document["receivers"])
            ]
            != list(iq.receiver_ids)
        ):
            raise ValueError("quality predecessor geometry disagrees with IQ")
        window = _positive_int(context.stage_config, "window_samples", iq.sample_rate_hz)
        block = _positive_int(context.stage_config, "block_samples", 262_144)
        maximum = _positive_int(context.stage_config, "maximum_windows", 3_600)
        document = decode_standard_product(
            POWER_TIMELINE_PRODUCT,
            measure_power_timeline(
                iq, window_samples=window, block_samples=block, maximum_windows=maximum
            ),
        )
        wrapper = _derived_binding(POWER_TIMELINE_PRODUCT, document, quality)
        outcome = _coverage_outcome(
            document["observed_sample_count"], document["expected_sample_count"]
        )
        return _publish(
            outputs, POWER_TIMELINE_PRODUCT, document, outcome=outcome, summary=_membership(wrapper)
        )


class PathWaterfallAnalyzer:
    spec = _spec(
        "path-waterfall",
        dependencies=("path-power",),
        inputs=(
            ProductRequirement(
                kind=POWER_TIMELINE_PRODUCT.kind,
                accepted_schema_versions=(POWER_TIMELINE_PRODUCT.schema_version,),
                producer_stage_key="path-power",
                require_available=True,
            ),
        ),
        outputs=(NUMERICAL_WATERFALL_PRODUCT,),
        resource=ResourceClass.HEAVY,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        power = _bound(products, self.spec.input_products[0])
        _require_same_path_iq(context, power, iq)
        if (
            power.document["sample_rate_hz"] != iq.sample_rate_hz
            or power.document["expected_sample_count"] != iq.sample_count
            or tuple(cast(list[int], power.document["receiver_ids"])) != iq.receiver_ids
        ):
            raise ValueError("power predecessor geometry disagrees with IQ")
        config = _dataclass_config(WaterfallConfig, context.stage_config)
        document = decode_standard_product(
            NUMERICAL_WATERFALL_PRODUCT,
            numerical_waterfall_document(bounded_waterfall(iq, config), config),
        )
        wrapper = _derived_binding(NUMERICAL_WATERFALL_PRODUCT, document, power)
        coverage = cast(dict[str, Any], document["coverage"])
        outcome = _coverage_outcome(coverage["observed_samples"], coverage["expected_samples"])
        return _publish(
            outputs,
            NUMERICAL_WATERFALL_PRODUCT,
            document,
            outcome=outcome,
            summary=_membership(wrapper),
        )


class PathProbeScheduleAnalyzer:
    spec = _spec(
        "path-probe-schedule",
        dependencies=("path-input-bind",),
        inputs=(
            ProductRequirement(
                kind=PATH_INPUT_BIND_PRODUCT.kind,
                accepted_schema_versions=(2,),
                producer_stage_key="path-input-bind",
                require_available=True,
            ),
        ),
        outputs=(PROBE_SCHEDULE_PRODUCT,),
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        binding = _path_binding(products, self.spec.input_products[0], context)
        document = build_probe_schedule(
            sample_rate_hz=binding.sample_rate_hz,
            sample_count=binding.declared_sample_count,
            subwindow_ms=_positive_int(context.stage_config, "subwindow_ms", 50),
            probe_ms=_positive_int(context.stage_config, "probe_ms", 20),
            probe_offsets_ms=_probe_offsets(context.stage_config),
            maximum_coarse_windows=_positive_int(
                context.stage_config, "maximum_coarse_windows", 120
            ),
        ).model_dump(mode="json")
        document = decode_standard_product(PROBE_SCHEDULE_PRODUCT, document)
        wrapper = _root_binding(PROBE_SCHEDULE_PRODUCT, document, binding)
        outcome = (
            StageOutcome.INSUFFICIENT_DATA
            if not document["returned_probe_count"]
            else StageOutcome.PARTIAL_COVERAGE
            if document["truncated_probe_count"]
            else StageOutcome.COMPLETE
        )
        return _publish(
            outputs, PROBE_SCHEDULE_PRODUCT, document, outcome=outcome, summary=_membership(wrapper)
        )


class PathPilotScanAnalyzer:
    spec = _spec(
        "path-pilot-scan",
        dependencies=("path-probe-schedule",),
        inputs=(
            ProductRequirement(
                kind=PROBE_SCHEDULE_PRODUCT.kind,
                accepted_schema_versions=(2,),
                producer_stage_key="path-probe-schedule",
                require_available=True,
            ),
        ),
        outputs=(PILOT_SCAN_PRODUCT,),
        resource=ResourceClass.HEAVY,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        scheduled = _bound(products, self.spec.input_products[0])
        schedule = ProbeScheduleV2.model_validate(scheduled.document)
        _require_same_path_iq(context, scheduled, iq)
        if (
            schedule.sample_rate_hz != iq.sample_rate_hz
            or schedule.declared_sample_count != iq.sample_count
        ):
            raise ValueError("probe schedule geometry disagrees with IQ")
        config = _feedback_config(context.stage_config, schedule=schedule)
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        _require_path_context(context, binding)
        detections = scan_pilot_detections(iq, config, edge=binding.starlink_edge)
        empty = TrajectoryBankResult(default_trajectory_bank_config().digest, (), (), 0, 0)
        document = standard_v2_trajectory_documents(
            detections=detections,
            bank=empty,
            representatives=(),
            replay=(),
            coarse_window_samples=iq.sample_rate_hz,
            subwindow_samples=iq.sample_rate_hz * config.subwindow_ms // 1_000,
            probe_samples=iq.sample_rate_hz * config.probe_ms // 1_000,
            maximum_scored_candidates_per_probe=config.maximum_scored_candidates_per_probe,
            probe_schedule_digest=schedule.schedule_digest,
        )[PILOT_SCAN_PRODUCT.kind]
        if tuple(item.sample_start for item in detections) != tuple(
            item.sample_start for item in schedule.probes
        ):
            raise ValueError("pilot scan did not consume the exact probe schedule")
        document = decode_standard_product(PILOT_SCAN_PRODUCT, document)
        wrapper = _derived_binding(PILOT_SCAN_PRODUCT, document, scheduled)
        outcome = _derived_science_outcome(
            (scheduled.outcome,),
            has_result=any(item.status is NumericalStatus.COMPLETE for item in detections),
            truncated=bool(schedule.truncated_probe_count)
            or any(item.truncated_candidate_count for item in detections),
            observations=tuple(item.status for item in detections),
        )
        return _publish(
            outputs,
            PILOT_SCAN_PRODUCT,
            document,
            outcome=outcome,
            summary=_membership(wrapper),
        )


class PathTrajectoryBankAnalyzer:
    spec = _spec(
        "path-trajectory-bank",
        dependencies=("path-pilot-scan",),
        inputs=(
            ProductRequirement(
                kind=PILOT_SCAN_PRODUCT.kind,
                accepted_schema_versions=(PILOT_SCAN_PRODUCT.schema_version,),
                producer_stage_key="path-pilot-scan",
                require_available=True,
            ),
        ),
        outputs=(TRAJECTORY_BANK_PRODUCT,),
        resource=ResourceClass.MEMORY,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        pilot = _bound(products, self.spec.input_products[0])
        _require_same_path_product(context, pilot)
        detections = _pilot_detections(pilot.document)
        config = _feedback_config(context.stage_config)
        bank, representatives = fit_pilot_trajectories(detections, config)
        document = standard_v2_trajectory_documents(
            detections=detections,
            bank=bank,
            representatives=representatives,
            replay=(),
            coarse_window_samples=_as_int(pilot.document["coarse_window_samples"]),
            subwindow_samples=_as_int(pilot.document["subwindow_samples"]),
            probe_samples=_as_int(pilot.document["probe_samples"]),
            maximum_scored_candidates_per_probe=_as_int(
                pilot.document["maximum_scored_candidates_per_probe"]
            ),
            probe_schedule_digest=str(pilot.document["probe_schedule_digest"]),
        )[TRAJECTORY_BANK_PRODUCT.kind]
        document = decode_standard_product(TRAJECTORY_BANK_PRODUCT, document)
        wrapper = _derived_binding(TRAJECTORY_BANK_PRODUCT, document, pilot)
        outcome = _derived_science_outcome(
            (pilot.outcome,),
            has_result=bool(bank.trajectories),
            truncated=bool(bank.truncated_trajectory_count)
            or any(item.truncated_candidate_count for item in detections),
        )
        return _publish(
            outputs,
            TRAJECTORY_BANK_PRODUCT,
            document,
            outcome=outcome,
            summary=_membership(wrapper),
        )


class PathTrajectoryFeedbackAnalyzer:
    spec = _spec(
        "path-trajectory-feedback",
        dependencies=("path-pilot-scan", "path-trajectory-bank"),
        inputs=(
            ProductRequirement(
                kind=PILOT_SCAN_PRODUCT.kind,
                accepted_schema_versions=(PILOT_SCAN_PRODUCT.schema_version,),
                producer_stage_key="path-pilot-scan",
                require_available=True,
            ),
            ProductRequirement(
                kind=TRAJECTORY_BANK_PRODUCT.kind,
                accepted_schema_versions=(2,),
                producer_stage_key="path-trajectory-bank",
                require_available=True,
            ),
        ),
        outputs=(TRAJECTORY_FEEDBACK_PRODUCT, GLRT64_TRAJECTORY_TABLE_PRODUCT),
        resource=ResourceClass.HEAVY,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        pilot = _bound(products, self.spec.input_products[0])
        bank_source = _bound(products, self.spec.input_products[1])
        _require_same_path_iq(context, pilot, iq)
        _require_same_path_iq(context, bank_source, iq)
        if pilot.document["coarse_window_samples"] != iq.sample_rate_hz:
            raise ValueError("pilot predecessor sample rate disagrees with IQ")
        if bank_source.document["pilot_scan_digest"] != canonical_digest(pilot.document):
            raise ValueError("trajectory bank does not consume the exact pilot scan")
        detections = _pilot_detections(pilot.document)
        bank, representatives = _trajectory_bank(bank_source.document)
        config = _feedback_config(context.stage_config)
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        _require_path_context(context, binding)
        replay = replay_pilot_trajectories(
            iq, detections, representatives, config, edge=binding.starlink_edge
        )
        documents = standard_v2_trajectory_documents(
            detections=detections,
            bank=bank,
            representatives=representatives,
            replay=replay,
            coarse_window_samples=_as_int(pilot.document["coarse_window_samples"]),
            subwindow_samples=_as_int(pilot.document["subwindow_samples"]),
            probe_samples=_as_int(pilot.document["probe_samples"]),
            maximum_scored_candidates_per_probe=_as_int(
                pilot.document["maximum_scored_candidates_per_probe"]
            ),
            probe_schedule_digest=str(pilot.document["probe_schedule_digest"]),
        )
        feedback = decode_standard_product(
            TRAJECTORY_FEEDBACK_PRODUCT, documents[TRAJECTORY_FEEDBACK_PRODUCT.kind]
        )
        table = decode_standard_product(
            GLRT64_TRAJECTORY_TABLE_PRODUCT, documents[GLRT64_TRAJECTORY_TABLE_PRODUCT.kind]
        )
        feedback_wrapper = _derived_binding(
            TRAJECTORY_FEEDBACK_PRODUCT, feedback, pilot, bank_source
        )
        outcome = _derived_science_outcome(
            (pilot.outcome, bank_source.outcome),
            has_result=bool(replay),
            truncated=bool(bank.truncated_trajectory_count)
            or any(item.truncated_candidate_count for item in detections),
        )
        synthetic_feedback = UpstreamJsonProduct(
            producer_node_id=context.job_node_id or "path-trajectory-feedback",
            producer_scope=pilot.producer_scope,
            outcome=outcome,
            product_digest=canonical_digest(feedback),
            document=cast(dict[str, JsonValue], feedback),
            membership=_membership(feedback_wrapper),
        )
        table_wrapper = _derived_binding(
            GLRT64_TRAJECTORY_TABLE_PRODUCT, table, bank_source, synthetic_feedback
        )
        published = (
            outputs.publish_json(TRAJECTORY_FEEDBACK_PRODUCT, cast(dict[str, JsonValue], feedback)),
            outputs.publish_json(
                GLRT64_TRAJECTORY_TABLE_PRODUCT, cast(dict[str, JsonValue], table)
            ),
        )
        return StageResult(
            outcome=outcome,
            products=published,
            summary=_membership(feedback_wrapper, table_wrapper),
        )


class PathScientificReportAnalyzer:
    spec = _spec(
        "path-scientific-report",
        dependencies=(
            "path-input-bind",
            "path-quality",
            "path-power",
            "path-waterfall",
            "path-probe-schedule",
            "path-pilot-scan",
            "path-trajectory-bank",
            "path-trajectory-feedback",
        ),
        inputs=PATH_REPORT_INPUTS,
        outputs=(PATH_REPORT_PRODUCT,),
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        by_kind = {
            requirement.kind: _bound(
                products, requirement, membership=requirement.kind != PATH_INPUT_BIND_PRODUCT.kind
            )
            for requirement in self.spec.input_products
        }
        for item in by_kind.values():
            _require_same_path_product(context, item)
        binding = StandardPathInputBindV3.model_validate(
            by_kind[PATH_INPUT_BIND_PRODUCT.kind].document
        )
        _require_path_context(context, binding)
        schedule = ProbeScheduleV2.model_validate(by_kind[PROBE_SCHEDULE_PRODUCT.kind].document)
        source_bindings = {}
        for kind, item in by_kind.items():
            if kind != PATH_INPUT_BIND_PRODUCT.kind:
                source_bindings.update(_binding_documents(item))
        report_inputs = PathReportInputs(
            input_bind=binding,
            schedule=schedule,
            quality_clipping_abs_threshold=_as_int(
                by_kind[QUALITY_PRODUCT.kind].document["clipping_abs_threshold"]
            ),
            power_window_samples=_as_int(
                by_kind[POWER_TIMELINE_PRODUCT.kind].document["window_samples"]
            ),
            waterfall_config_digest=str(
                by_kind[NUMERICAL_WATERFALL_PRODUCT.kind].document["config_digest"]
            ),
            maximum_scored_candidates_per_probe=_as_int(
                by_kind[PILOT_SCAN_PRODUCT.kind].document["maximum_scored_candidates_per_probe"]
            ),
            maximum_replayed_families=_positive_int(
                context.stage_config, "maximum_replayed_families", 16
            ),
        )
        result = build_path_standard_report(
            report_inputs,
            quality_document=by_kind[QUALITY_PRODUCT.kind].document,
            power_document=by_kind[POWER_TIMELINE_PRODUCT.kind].document,
            waterfall_document=by_kind[NUMERICAL_WATERFALL_PRODUCT.kind].document,
            pilot_document=by_kind[PILOT_SCAN_PRODUCT.kind].document,
            trajectory_document=by_kind[TRAJECTORY_BANK_PRODUCT.kind].document,
            feedback_document=by_kind[TRAJECTORY_FEEDBACK_PRODUCT.kind].document,
            trajectory_table_document=by_kind[GLRT64_TRAJECTORY_TABLE_PRODUCT.kind].document,
            source_binding_documents=source_bindings,
        )
        document = decode_standard_product(
            PATH_REPORT_PRODUCT, result.report.model_dump(mode="json")
        )
        return _publish(
            outputs, PATH_REPORT_PRODUCT, document, outcome=_report_outcome(result.report.status)
        )


def _path_presentation_document(
    binding: StandardPathInputBindV3,
    report: PathStandardReportV2,
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "algorithm_version": "standard-path-presentation-v3",
        "session_id": binding.session_id,
        "stream_id": binding.stream_id,
        "radio_id": binding.radio_id,
        "receiver_id": binding.receiver_id,
        "tuned_center_frequency_hz": binding.tuned_center_frequency_hz,
        "first_sample_utc_ns": binding.timing.first_estimate_utc_ns,
        "last_sample_utc_ns": binding.timing.last_estimate_utc_ns,
        "path_report_digest": report.report_digest,
        "sample_rate_hz": report.raw_report.sample_rate_hz,
        "declared_sample_count": report.raw_report.declared_sample_count,
        "power_timeline": values[POWER_TIMELINE_PRODUCT.kind],
        "waterfall": values[NUMERICAL_WATERFALL_PRODUCT.kind],
        "pilot_scan": values[PILOT_SCAN_PRODUCT.kind],
        "trajectory_bank": values[TRAJECTORY_BANK_PRODUCT.kind],
        "trajectory_feedback": values[TRAJECTORY_FEEDBACK_PRODUCT.kind],
        "trajectory_table": values[GLRT64_TRAJECTORY_TABLE_PRODUCT.kind],
        "cfo_alias_map": values[CFO_ALIAS_MAP_PRODUCT.kind],
        "dealiased_trajectory_bank": values[DEALIASED_TRAJECTORY_BANK_PRODUCT.kind],
        "cfo_lift_replay": values[CFO_LIFT_REPLAY_PRODUCT.kind],
        "final_trajectory_bank": values[FINAL_TRAJECTORY_BANK_PRODUCT.kind],
        "final_trajectory_table": values[GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT.kind],
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }


def _png_source(
    session_id: str,
    subject_id: str,
    documents: tuple[dict[str, Any], ...],
) -> StandardPngSource:
    if not documents or len(documents) > 4:
        raise ValueError("Standard PNG source requires one to four path presentations")
    ordered = tuple(sorted(documents, key=lambda item: (item["stream_id"], item["receiver_id"])))
    starts = tuple(int(item["first_sample_utc_ns"]) for item in ordered)
    origin = min(starts)
    end_ns = max(int(item["last_sample_utc_ns"]) for item in ordered)
    return StandardPngSource(
        session_id=session_id,
        subject_id=subject_id,
        elapsed_start_s=0.0,
        elapsed_end_s=(end_ns - origin) / 1_000_000_000,
        paths=tuple(
            StandardPngPathSource(
                path_id=f"{item['radio_id']}:rx{item['receiver_id']}",
                label=f"{item['stream_id']} · {item['radio_id']} · RX{item['receiver_id']}",
                time_offset_s=(int(item["first_sample_utc_ns"]) - origin) / 1_000_000_000,
                tuned_center_frequency_hz=int(item["tuned_center_frequency_hz"]),
                sample_rate_hz=int(item["sample_rate_hz"]),
                receiver_id=int(item["receiver_id"]),
                waterfall=cast(dict[str, Any], item["waterfall"]),
                pilot_scan=cast(dict[str, Any], item["pilot_scan"]),
                trajectory_feedback=cast(dict[str, Any], item["trajectory_feedback"]),
                trajectory_table=cast(dict[str, Any], item["trajectory_table"]),
                cfo_alias_map=cast(dict[str, Any], item["cfo_alias_map"]),
                dealiased_trajectory_bank=cast(dict[str, Any], item["dealiased_trajectory_bank"]),
                cfo_lift_replay=cast(dict[str, Any], item["cfo_lift_replay"]),
                final_trajectory_bank=cast(dict[str, Any], item["final_trajectory_bank"]),
                final_trajectory_table=cast(dict[str, Any], item["final_trajectory_table"]),
            )
            for item in ordered
        ),
    )


def _publish_pngs(outputs: OutputSink, source: StandardPngSource) -> tuple[PublishedProduct, ...]:
    kinds = (
        (WATERFALL_PNG_PRODUCT, StandardViewKindV2.WATERFALL),
        (PILOT_METHODS_PNG_PRODUCT, StandardViewKindV2.GLRT64),
        (CFO_TRAJECTORIES_PNG_PRODUCT, StandardViewKindV2.CFO_TRAJECTORY),
    )
    standard = tuple(
        outputs.publish_bytes(product, render_full_standard_plot_png(source, view_kind))
        for product, view_kind in kinds
    )
    return (
        *standard,
        outputs.publish_bytes(
            DEALIASED_CFO_TRAJECTORIES_PNG_PRODUCT,
            render_full_cfo_stage_png(source, stage="dealiased"),
        ),
        outputs.publish_bytes(
            FINAL_CFO_TRAJECTORIES_PNG_PRODUCT,
            render_full_cfo_stage_png(source, stage="final"),
        ),
    )


class PathPresentationAnalyzer:
    spec = _spec(
        "path-presentation",
        dependencies=(
            "path-power",
            "path-waterfall",
            "path-pilot-scan",
            "path-trajectory-bank",
            "path-trajectory-feedback",
            "path-scientific-report",
        ),
        inputs=PATH_PRESENTATION_INPUTS,
        outputs=(PATH_PRESENTATION_PRODUCT,),
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        sources = {
            requirement.kind: _bound(
                products,
                requirement,
                membership=requirement.kind != PATH_REPORT_PRODUCT.kind,
            )
            for requirement in self.spec.input_products
        }
        for source in sources.values():
            _require_same_path_product(context, source)
        values = {kind: source.document for kind, source in sources.items()}
        report = PathStandardReportV2.model_validate(values[PATH_REPORT_PRODUCT.kind])
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        document = _path_presentation_document(binding, report, values)
        return _publish(
            outputs,
            PATH_PRESENTATION_PRODUCT,
            decode_standard_product(PATH_PRESENTATION_PRODUCT, document),
            outcome=_report_outcome(report.status),
        )


class RadioScientificReportAnalyzer:
    spec = _spec(
        "radio-scientific-report",
        dependencies=("path-standard",),
        inputs=(
            ProductRequirement(
                kind=PATH_REPORT_PRODUCT.kind,
                accepted_schema_versions=(PATH_REPORT_PRODUCT.schema_version,),
                producer_stage_key="path-standard",
                require_available=True,
            ),
            ProductRequirement(
                kind=PATH_PRESENTATION_PRODUCT.kind,
                accepted_schema_versions=(PATH_PRESENTATION_PRODUCT.schema_version,),
                producer_stage_key="path-standard",
                require_available=True,
            ),
        ),
        outputs=(RADIO_REPORT_PRODUCT, *STANDARD_PNG_PRODUCTS),
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        if context.scope is None or context.scope.kind is not ScopeKind.RADIO:
            raise ValueError("radio reducer requires an exact radio scope")
        upstream = products.read_json_many(
            self.spec.input_products[0], producer_node_ids=context.dependency_node_ids
        )
        presentations = products.read_json_many(
            self.spec.input_products[1], producer_node_ids=context.dependency_node_ids
        )
        reports = tuple(PathStandardReportV2.model_validate(item.document) for item in upstream)
        declared = tuple(item.producer_scope.receiver_id for item in upstream)
        if any(
            item.producer_scope.stream_id != context.scope.stream_id for item in upstream
        ) or any(item is None for item in declared):
            raise ValueError("radio reducer received foreign receiver-path membership")
        report = reduce_radio_v2(reports, declared_receiver_ids=cast(tuple[int, ...], declared))
        published_report = outputs.publish_json(
            RADIO_REPORT_PRODUCT,
            cast(
                dict[str, JsonValue],
                decode_standard_product(RADIO_REPORT_PRODUCT, report.model_dump(mode="json")),
            ),
        )
        source = _png_source(
            context.session_id,
            f"radio:{context.scope.radio_id}",
            tuple(cast(dict[str, Any], item.document) for item in presentations),
        )
        return StageResult(
            outcome=_report_outcome(report.status),
            products=(published_report, *_publish_pngs(outputs, source)),
        )


class PairedScientificReportAnalyzer:
    spec = _spec(
        "paired-scientific-report",
        dependencies=("radio-scientific-report",),
        inputs=(PAIRED_REPORT_INPUT,),
        outputs=(PAIRED_REPORT_PRODUCT,),
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        if context.scope is None or context.scope.kind is not ScopeKind.PAIRED:
            raise ValueError("paired reducer requires an exact paired scope")
        binding = StandardPairInputBindV2.model_validate(products.read_subject_binding())
        upstream = products.read_json_many(
            PAIRED_REPORT_INPUT, producer_node_ids=context.dependency_node_ids
        )
        if any(item.producer_scope.kind is not ScopeKind.RADIO for item in upstream):
            raise ValueError("paired reducer received non-radio membership")
        radio_reports = tuple(
            RadioStandardReportV2.model_validate(item.document) for item in upstream
        )
        if len(radio_reports) != 2:
            raise ValueError("paired reducer requires exactly two radio reports")
        report = reduce_paired_radios_v2(
            cast(tuple[RadioStandardReportV2, RadioStandardReportV2], radio_reports),
            binding=binding,
        )
        return _publish(
            outputs,
            PAIRED_REPORT_PRODUCT,
            decode_standard_product(PAIRED_REPORT_PRODUCT, report.model_dump(mode="json")),
            outcome=_report_outcome(report.status),
        )


class PairedPresentationAnalyzer:
    spec = _spec(
        "paired-presentation",
        dependencies=("path-standard",),
        inputs=(
            ProductRequirement(
                kind=PATH_PRESENTATION_PRODUCT.kind,
                accepted_schema_versions=(PATH_PRESENTATION_PRODUCT.schema_version,),
                producer_stage_key="path-standard",
                require_available=True,
            ),
        ),
        outputs=STANDARD_PNG_PRODUCTS,
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        if context.scope is None or context.scope.kind is not ScopeKind.PAIRED:
            raise ValueError("paired presentation requires an exact paired scope")
        presentations = products.read_json_many(
            self.spec.input_products[0], producer_node_ids=context.dependency_node_ids
        )
        source = _png_source(
            context.session_id,
            "paired",
            tuple(cast(dict[str, Any], item.document) for item in presentations),
        )
        return StageResult(
            outcome=_aggregate_outcome(tuple(item.outcome for item in presentations)),
            products=_publish_pngs(outputs, source),
        )


class PathAlternateTracksAnalyzer:
    """Derive bounded research-only geometry from the exact persisted pilot product."""

    spec = _spec(
        "path-alternate-tracks",
        algorithm_version="alternate-cfo-hough-v1",
        dependencies=("path-standard",),
        inputs=(ALTERNATE_CFO_TRACK_INPUT,),
        outputs=(ALTERNATE_CFO_TRACK_BANK_PRODUCT, ALTERNATE_CFO_TRACKS_PNG_PRODUCT),
        resource=ResourceClass.CPU,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        del iq
        source = _bound(products, ALTERNATE_CFO_TRACK_INPUT)
        _require_same_path_product(context, source)
        configured = context.stage_config or default_alternate_cfo_config().model_dump(mode="json")
        config = AlternateCfoLineFinderConfigV1.model_validate(configured)
        bank = build_alternate_cfo_tracks(
            cast(dict[str, Any], source.document),
            pilot_digest=source.product_digest,
            config=config,
        )
        document = decode_standard_product(
            ALTERNATE_CFO_TRACK_BANK_PRODUCT, bank.model_dump(mode="json")
        )
        published_json = outputs.publish_json(
            ALTERNATE_CFO_TRACK_BANK_PRODUCT, cast(dict[str, JsonValue], document)
        )
        published_png = outputs.publish_bytes(
            ALTERNATE_CFO_TRACKS_PNG_PRODUCT,
            render_alternate_cfo_tracks_png(cast(dict[str, Any], source.document), bank),
        )
        return StageResult(
            outcome=StageOutcome.COMPLETE if bank.tracks else StageOutcome.NO_RESULT,
            products=(published_json, published_png),
            summary={
                "candidate_only": True,
                "source_point_count": bank.source_point_count,
                "alternate_track_count": bank.returned_track_count,
            },
        )


_FUSED_PATH_PRODUCTS = (
    QUALITY_PRODUCT,
    POWER_TIMELINE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PROBE_SCHEDULE_PRODUCT,
    PILOT_SCAN_PRODUCT,
    TRAJECTORY_BANK_PRODUCT,
    TRAJECTORY_FEEDBACK_PRODUCT,
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    CFO_ALIAS_MAP_PRODUCT,
    DEALIASED_TRAJECTORY_BANK_PRODUCT,
    CFO_LIFT_REPLAY_PRODUCT,
    FINAL_TRAJECTORY_BANK_PRODUCT,
    GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT,
    PATH_REPORT_PRODUCT,
    PATH_PRESENTATION_PRODUCT,
    *STANDARD_PNG_PRODUCTS,
)


class PathStandardAnalyzer:
    """Execute and atomically publish one complete receiver-path analysis."""

    spec = _spec(
        "path-standard",
        outputs=_FUSED_PATH_PRODUCTS,
        resource=ResourceClass.HEAVY,
    )

    def analyze(
        self, context: AnalysisContext, iq: IqReader, products: ProductReader, outputs: OutputSink
    ) -> StageResult:
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        _require_path_context(context, binding)
        _require_iq(binding, iq)
        config = _receiver_standard_config(context.stage_config)
        schedule = build_probe_schedule(
            sample_rate_hz=binding.sample_rate_hz,
            sample_count=binding.declared_sample_count,
            subwindow_ms=config.feedback.subwindow_ms,
            probe_ms=config.feedback.probe_ms,
            probe_offsets_ms=config.feedback.probe_offsets_ms,
            maximum_coarse_windows=config.feedback.maximum_outer_windows,
        )
        report_inputs = PathReportInputs(
            input_bind=binding,
            schedule=schedule,
            quality_clipping_abs_threshold=32_767,
            power_window_samples=config.power_window_samples or binding.sample_rate_hz,
            waterfall_config_digest=config.waterfall.digest,
            maximum_scored_candidates_per_probe=(
                config.feedback.maximum_scored_candidates_per_probe
            ),
            maximum_replayed_families=config.feedback.maximum_replayed_families,
        )
        result = run_receiver_standard(
            iq,
            report_inputs,
            config=config,
            trusted_release_identity=(
                binding.science_configuration_digest,
                binding.science_implementation_digest,
            ),
        )
        documents = {
            **result.documents,
            PROBE_SCHEDULE_PRODUCT.kind: schedule.model_dump(mode="json"),
            PATH_REPORT_PRODUCT.kind: result.final_report.model_dump(mode="json"),
        }
        report = result.final_report
        documents[PATH_PRESENTATION_PRODUCT.kind] = _path_presentation_document(
            binding, report, documents
        )
        published = tuple(
            outputs.publish_json(
                product,
                cast(
                    dict[str, JsonValue],
                    decode_standard_product(product, documents[product.kind]),
                ),
            )
            for product in self.spec.output_products
            if product.media_type == "application/json"
        )
        source = _png_source(
            context.session_id,
            f"path:{binding.radio_id}:rx{binding.receiver_id}",
            (cast(dict[str, Any], documents[PATH_PRESENTATION_PRODUCT.kind]),),
        )
        wrappers = tuple(
            {"kind": kind, "document": document}
            for kind, document in result.source_bindings.items()
        )
        return StageResult(
            outcome=_report_outcome(report.status),
            products=(*published, *_publish_pngs(outputs, source)),
            summary=_membership(*wrappers),
        )


STANDARD_V2_ANALYZERS = (
    PathStandardAnalyzer,
    PathAlternateTracksAnalyzer,
    RadioScientificReportAnalyzer,
    PairedScientificReportAnalyzer,
    PairedPresentationAnalyzer,
)


def production_standard_v2_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry(analyzer() for analyzer in STANDARD_V2_ANALYZERS)
    if sum(len(registry.get(key).spec.output_products) for key in registry.keys) != 34:
        raise RuntimeError("Standard-v2 registry output inventory changed")
    return registry


def production_standard_v2_configuration() -> dict[str, dict[str, JsonValue]]:
    configuration: dict[str, dict[str, JsonValue]] = {
        key: {} for key in production_standard_v2_registry().keys
    }
    # Preserve the reviewed full-dwell visual/scientific resolution. The browser
    # renders these persisted cells directly; it must never invent resolution by
    # upscaling a smaller product.
    configuration["path-standard"] = {
        "waterfall": {
            "fft_samples": 1024,
            "frequency_bins": 256,
            "maximum_time_bins": 512,
        },
        # Retain the complete eight-candidate detector inventory per probe. The
        # former top-four cap made every otherwise successful 60-second run
        # report partial coverage solely because ranked evidence was omitted.
        "feedback": {
            "maximum_workers": 4,
            "maximum_scored_candidates_per_probe": 8,
            "probe_offsets_ms": [0, 25],
            "cfo_acquisition_mode": "independent_wide_per_probe",
            "cfo_search_min_hz": -400_000.0,
            "cfo_search_max_hz": 400_000.0,
        },
        "dealias": default_cfo_dealias_config().model_dump(mode="json"),
        "replay_gate": default_replay_gate_v3().model_dump(mode="json"),
    }
    configuration["path-alternate-tracks"] = cast(
        dict[str, JsonValue], default_alternate_cfo_config().model_dump(mode="json")
    )
    # The database scheduler runs all four receiver paths concurrently. Four
    # bounded coarse-window threads per path remain the production setting:
    # although six threads improved an isolated 10-second path, two complete
    # 2x2 LIVE runs showed no end-to-end or path-level gain under contention.
    # Avoid the extra threads and memory when the real workload does not benefit.
    return configuration


def _publish(
    outputs: OutputSink,
    product: ProductSpec,
    document: dict[str, Any],
    *,
    outcome: StageOutcome = StageOutcome.COMPLETE,
    summary: dict[str, JsonValue] | None = None,
) -> StageResult:
    normalized = decode_standard_product(product, document)
    published = outputs.publish_json(product, cast(dict[str, JsonValue], normalized))
    return StageResult(outcome=outcome, products=(published,), summary=summary or {})


class _DocumentSink:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, int], dict[str, JsonValue]] = {}

    def document(self, product: ProductSpec) -> dict[str, JsonValue]:
        return self.documents[(product.kind, product.schema_version)]

    def publish_json(
        self, product: ProductSpec, document: dict[str, JsonValue]
    ) -> PublishedProduct:
        self.documents[(product.kind, product.schema_version)] = document
        payload = canonical_json_bytes(document)
        return PublishedProduct(
            product=product,
            logical_uri="memory://standard-stage",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        raise ValueError("Standard-v2 products are JSON")


def _path_binding(
    products: ProductReader, requirement: ProductRequirement, context: AnalysisContext
) -> StandardPathInputBindV3:
    document = products.read_json(requirement)
    if document is None:
        raise KeyError(requirement.kind)
    binding = StandardPathInputBindV3.model_validate(document)
    _require_path_context(context, binding)
    return binding


def _require_path_context(context: AnalysisContext, binding: StandardPathInputBindV3) -> None:
    scope = context.scope
    if (
        scope is None
        or scope.kind is not ScopeKind.RECEIVER_PATH
        or (scope.session_id, scope.stream_id, scope.receiver_id)
        != (binding.session_id, binding.stream_id, binding.receiver_id)
    ):
        raise ValueError("path input binding does not match the exact analyzer scope")


def _require_iq(binding: StandardPathInputBindV3, iq: IqReader) -> None:
    if (iq.receiver_ids, iq.sample_rate_hz, iq.sample_count, iq.center_frequency_hz) != (
        (binding.receiver_id,),
        binding.sample_rate_hz,
        binding.declared_sample_count,
        binding.tuned_center_frequency_hz,
    ):
        raise ValueError("IQ reader does not match the exact path input binding")


def _require_same_path_iq(
    context: AnalysisContext,
    source: UpstreamJsonProduct,
    iq: IqReader,
) -> None:
    if (
        not _is_same_path_product(context, source)
        or source.producer_scope.receiver_id is None
        or iq.receiver_ids != (source.producer_scope.receiver_id,)
    ):
        raise ValueError("IQ reader and predecessor product are from different receiver paths")


def _is_same_path_product(context: AnalysisContext, source: UpstreamJsonProduct) -> bool:
    return (
        context.scope is not None
        and context.scope.kind is ScopeKind.RECEIVER_PATH
        and source.producer_scope == context.scope
    )


def _require_same_path_product(
    context: AnalysisContext,
    source: UpstreamJsonProduct,
) -> None:
    if not _is_same_path_product(context, source):
        raise ValueError("predecessor product is from a different receiver path")


def _bound(
    products: ProductReader, requirement: ProductRequirement, *, membership: bool = True
) -> UpstreamJsonProduct:
    result = products.read_json_bound(requirement)
    if result is None:
        raise KeyError(requirement.kind)
    decode_standard_product(
        ProductSpec(
            kind=requirement.kind,
            schema_version=requirement.accepted_schema_versions[0],
            role=requirement.required_role or ProductRole.SCIENTIFIC,
        ),
        cast(dict[str, Any], result.document),
    )
    if membership:
        _binding_documents(result)
    return result


def _binding_documents(source: UpstreamJsonProduct) -> dict[str, dict[str, Any]]:
    raw = source.membership.get(_MEMBERSHIP_KEY)
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Standard predecessor lacks source-binding membership")
    result = {}
    for kind, value in raw.items():
        if not isinstance(kind, str) or not isinstance(value, dict):
            raise ValueError("source-binding membership is malformed")
        binding = StandardSourceBindingV1.model_validate(value)
        try:
            expected = next(
                item
                for item in (
                    *STANDARD_SOURCE_BINDING_SPECS,
                    *STANDARD_FINAL_SOURCE_BINDING_SPECS,
                )
                if item.wrapper_kind == kind
            )
        except StopIteration as error:
            raise ValueError("source-binding membership kind is undeclared") from error
        if (
            binding.stage_key != expected.stage_key
            or binding.product_kind != expected.product_kind
            or binding.product_schema_version != expected.product_schema_version
        ):
            raise ValueError("source-binding membership identity is inconsistent")
        result[kind] = binding.model_dump(mode="json")
    matching = [
        item
        for item in result.values()
        if item["product_content_digest"] == canonical_digest(source.document)
    ]
    if len(matching) != 1:
        raise ValueError("source-binding membership does not bind the exact product bytes")
    return result


def _membership(*bindings: dict[str, Any]) -> dict[str, JsonValue]:
    values = {str(binding["kind"]): binding["document"] for binding in bindings}
    return cast(dict[str, JsonValue], {_MEMBERSHIP_KEY: values})


def _spec_for(product: ProductSpec):
    return next(item for item in STANDARD_SOURCE_BINDING_SPECS if item.product_kind == product.kind)


def _root_binding(
    product: ProductSpec, document: dict[str, Any], input_bind: StandardPathInputBindV3
) -> dict[str, Any]:
    spec = _spec_for(product)
    return {
        "kind": spec.wrapper_kind,
        "document": build_standard_source_binding(spec, document, input_bind=input_bind),
    }


def _derived_binding(
    product: ProductSpec, document: dict[str, Any], *sources: UpstreamJsonProduct
) -> dict[str, Any]:
    spec = _spec_for(product)
    available = {}
    for source in sources:
        available.update(_binding_documents(source))
    predecessors = {kind: available[kind] for kind in spec.predecessor_wrapper_kinds}
    return {
        "kind": spec.wrapper_kind,
        "document": build_standard_source_binding(
            spec, document, predecessor_binding_documents=predecessors
        ),
    }


def _positive_int(values: dict[str, JsonValue], key: str, default: int) -> int:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _probe_offsets(values: dict[str, Any]) -> tuple[int, ...]:
    raw = values.get("probe_offsets_ms", [0, 25])
    if not isinstance(raw, (list, tuple)) or any(
        isinstance(value, bool) or not isinstance(value, int) for value in raw
    ):
        raise ValueError("probe_offsets_ms must be an array of integers")
    return tuple(cast(list[int] | tuple[int, ...], raw))


def _dataclass_config(cls, values: dict[str, JsonValue]):
    allowed = {item.name for item in fields(cls)}
    if set(values) - allowed:
        raise ValueError(f"unknown {cls.__name__} configuration fields")
    return cls(**values)


def _feedback_config(
    values: dict[str, JsonValue], *, schedule: ProbeScheduleV2 | None = None
) -> TrajectoryFeedbackConfig:
    allowed = {item.name for item in fields(TrajectoryFeedbackConfig)}
    if set(values) - allowed:
        raise ValueError("unknown trajectory feedback configuration fields")
    config_values: dict[str, Any] = dict(values)
    config_values["probe_offsets_ms"] = _probe_offsets(config_values)
    if schedule is not None:
        expected: dict[str, Any] = {
            "subwindow_ms": schedule.subwindow_ms,
            "probe_ms": schedule.probe_ms,
            "probe_offsets_ms": schedule.probe_offsets_ms,
            "maximum_outer_windows": schedule.maximum_coarse_windows,
        }
        for key, value in expected.items():
            if key in config_values and config_values[key] != value:
                raise ValueError("pilot configuration disagrees with exact probe schedule")
            config_values[key] = value
    config = TrajectoryFeedbackConfig(**cast(dict[str, Any], config_values))
    validate_trajectory_feedback_config(config)
    return config


def _receiver_standard_config(values: dict[str, JsonValue]) -> ReceiverStandardConfig:
    allowed = {item.name for item in fields(ReceiverStandardConfig)}
    if set(values) - allowed:
        raise ValueError("unknown fused receiver Standard configuration fields")
    scalar_values = {
        key: value
        for key, value in values.items()
        if key not in {"waterfall", "feedback", "dealias", "replay_gate", "association"}
    }
    waterfall_values = values.get("waterfall", {})
    feedback_values = values.get("feedback", {})
    dealias_values = values.get("dealias")
    replay_gate_values = values.get("replay_gate")
    association_values = values.get("association", {})
    if (
        not isinstance(waterfall_values, dict)
        or not isinstance(feedback_values, dict)
        or not isinstance(dealias_values, dict)
        or not isinstance(replay_gate_values, dict)
        or not isinstance(association_values, dict)
    ):
        raise ValueError("fused receiver nested configuration must be objects")
    return ReceiverStandardConfig(
        **cast(dict[str, Any], scalar_values),
        waterfall=_dataclass_config(WaterfallConfig, cast(dict[str, JsonValue], waterfall_values)),
        feedback=_feedback_config(cast(dict[str, JsonValue], feedback_values)),
        dealias=CfoDealiasConfigV1.model_validate(dealias_values),
        replay_gate=ReplayGateConfigV3.model_validate(replay_gate_values),
        association=MultiTargetAssociationConfigV1.model_validate(association_values)
        if association_values
        else default_multi_target_association_config(),
    )


def _pilot_detections(document: dict[str, JsonValue]) -> tuple[PilotProbeDetection, ...]:
    decode_standard_product(PILOT_SCAN_PRODUCT, cast(dict[str, Any], document))
    return tuple(
        _pilot_detection(cast(dict[str, Any], item))
        for item in cast(list[Any], document["detections"])
    )


def _score(value: dict[str, Any]) -> PilotMethodScore:
    return PilotMethodScore(
        PilotMethod(value["method"]),
        float(value["exact_score"]),
        None if value["control_score"] is None else float(value["control_score"]),
        float(value["margin"]),
        float(value["residual_cfo_hz"]),
        float(value["tracking_cfo_hz"]),
    )


def _candidate(value: dict[str, Any]) -> PilotMethodCandidate:
    return PilotMethodCandidate(
        int(value["rank"]),
        int(value["local_epoch_sample"]),
        float(value["acquired_cfo_hz"]),
        tuple(_score(item) for item in value["scores"]),
        value["qam_accuracy"],
        value["qam_evm"],
    )


def _pilot_detection(value: dict[str, Any]) -> PilotProbeDetection:
    return PilotProbeDetection(
        NumericalStatus(value["status"]),
        int(value["sample_start"]),
        float(value["time_s"]),
        value["local_epoch_sample"],
        value["acquired_cfo_hz"],
        tuple(_score(item) for item in value["scores"]),
        value["qam_accuracy"],
        value["qam_evm"],
        str(value["reason"]),
        int(value["source_candidate_count"]),
        int(value["truncated_candidate_count"]),
        tuple(_candidate(item) for item in value["candidates"]),
    )


def _polynomial(value: dict[str, Any]) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        str(value["trajectory_id"]),
        PilotMethod(value["method"]),
        int(value["polynomial_degree"]),
        float(value["reference_time_s"]),
        tuple(float(item) for item in value["coefficients_hz"]),
        float(value["start_s"]),
        float(value["end_s"]),
        tuple(str(item) for item in value["observation_ids"]),
        int(value["point_count"]),
        float(value["residual_rms_hz"]),
        float(value["bic"]),
        float(value["high_gate"]),
        int(value["em_iterations"]),
        bool(value["candidate_only"]),
    )


def _trajectory_bank(
    document: dict[str, JsonValue],
) -> tuple[TrajectoryBankResult, tuple[tuple[str, PolynomialTrajectory], ...]]:
    decode_standard_product(TRAJECTORY_BANK_PRODUCT, cast(dict[str, Any], document))
    trajectories = tuple(
        _polynomial(cast(dict[str, Any], item))
        for item in cast(list[Any], document["trajectories"])
    )
    families = tuple(
        TrajectoryFamily(
            str(item["family_id"]),
            str(item["representative_trajectory_id"]),
            tuple(str(value) for value in item["member_trajectory_ids"]),
            float(item["start_s"]),
            float(item["end_s"]),
        )
        for item in cast(list[dict[str, Any]], document["families"])
    )
    bank = TrajectoryBankResult(
        str(document["config_digest"]),
        trajectories,
        families,
        _as_int(document["observation_count"]),
        _as_int(document["truncated_trajectory_count"]),
        True,
    )
    representatives = tuple(
        (
            str(item["family_id"]),
            _polynomial(
                cast(
                    dict[str, Any],
                    {key: value for key, value in item.items() if key != "family_id"},
                )
            ),
        )
        for item in cast(list[dict[str, Any]], document["replayed_representatives"])
    )
    return bank, representatives


def _coverage_outcome(observed: Any, expected: Any) -> StageOutcome:
    if int(observed) == 0:
        return StageOutcome.INSUFFICIENT_DATA
    return (
        StageOutcome.COMPLETE if int(observed) == int(expected) else StageOutcome.PARTIAL_COVERAGE
    )


def _derived_science_outcome(
    predecessors: tuple[StageOutcome, ...],
    *,
    has_result: bool,
    truncated: bool,
    observations: tuple[NumericalStatus, ...] = (),
) -> StageOutcome:
    if any(item is StageOutcome.INSUFFICIENT_DATA for item in predecessors):
        return StageOutcome.INSUFFICIENT_DATA
    if any(item is StageOutcome.PARTIAL_COVERAGE for item in predecessors):
        return StageOutcome.PARTIAL_COVERAGE
    if observations:
        insufficient = sum(item is NumericalStatus.INSUFFICIENT for item in observations)
        if insufficient == len(observations):
            return StageOutcome.INSUFFICIENT_DATA
        if insufficient:
            return StageOutcome.PARTIAL_COVERAGE
    if truncated:
        return StageOutcome.PARTIAL_COVERAGE
    if observations and all(item is NumericalStatus.NO_RESULT for item in observations):
        return StageOutcome.NO_RESULT
    if any(item is StageOutcome.NO_RESULT for item in predecessors):
        return StageOutcome.NO_RESULT
    return StageOutcome.COMPLETE if has_result else StageOutcome.NO_RESULT


def _as_int(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Standard integer field is invalid")
    return value


def _report_outcome(status) -> StageOutcome:
    return {
        "complete": StageOutcome.COMPLETE,
        "partial": StageOutcome.PARTIAL_COVERAGE,
        "no_result": StageOutcome.NO_RESULT,
        "insufficient_data": StageOutcome.INSUFFICIENT_DATA,
    }[status.value]


def _aggregate_outcome(outcomes: tuple[StageOutcome, ...]) -> StageOutcome:
    if any(item is StageOutcome.INSUFFICIENT_DATA for item in outcomes):
        return StageOutcome.INSUFFICIENT_DATA
    if any(item is StageOutcome.PARTIAL_COVERAGE for item in outcomes):
        return StageOutcome.PARTIAL_COVERAGE
    if outcomes and all(item is StageOutcome.NO_RESULT for item in outcomes):
        return StageOutcome.NO_RESULT
    # A complete search that finds nothing on one path does not make the
    # successfully rendered paired presentation incomplete.  Preserve
    # NO_RESULT only when every path found nothing; mixed COMPLETE/NO_RESULT
    # inputs still represent complete coverage of the paired subject.
    return StageOutcome.COMPLETE
