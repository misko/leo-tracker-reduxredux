"""Infrastructure-blind complete receiver-path Standard science runner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast

import numpy as np
from pydantic import JsonValue

from leo.analysis.quality import QualityAnalyzer
from leo.analysis.standard.alternate_tracks import default_alternate_cfo_config
from leo.analysis.standard.final_reports import build_path_standard_report_v2
from leo.analysis.standard.observability import (
    measure_power_timeline,
    numerical_waterfall_document,
)
from leo.analysis.standard.probes import build_probe_schedule
from leo.analysis.standard.reports import (
    PathReportInputs,
    PathStandardProducts,
    build_path_standard_report,
    standard_v3_trajectory_documents,
)
from leo.analysis.standard.source_bindings import (
    build_standard_final_source_bindings,
    build_standard_source_bindings,
)
from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    build_final_trajectory_table_v3,
    default_cfo_dealias_config,
    default_replay_gate_v4,
    fit_seed_preserving_dealiased_trajectories,
    replay_observed_cfo_lifts_v4,
    select_final_trajectories_v3,
)
from leo.analysis.starlink.multi_target import default_multi_target_association_config
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_residual_hough_pilot_trajectories,
    replay_pilot_trajectories,
    scan_pilot_detections,
    trajectory_observations,
)
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.alternate_cfo_tracks import ResidualHoughSegmentationConfigV2
from leo.contracts.cfo_dealias import (
    CfoDealiasConfigV1,
    ReplayGateConfigV4,
    SeededAliasEmConfigV1,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.final_trajectory_reports import PathStandardReportV2
from leo.contracts.multi_target import MultiTargetAssociationConfigV1
from leo.contracts.standard_pipeline import (
    STANDARD_NUMERICAL_WATERFALL_KIND,
    STANDARD_POWER_TIMELINE_KIND,
)
from leo.domain.iq import IqBlock
from leo.pipeline import (
    AnalysisContext,
    IqReader,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    UpstreamJsonProduct,
)


@dataclass(frozen=True, slots=True)
class ReceiverStandardConfig:
    quality_block_samples: int = 262_144
    power_block_samples: int = 262_144
    power_window_samples: int | None = None
    waterfall: WaterfallConfig = WaterfallConfig()
    feedback: TrajectoryFeedbackConfig = TrajectoryFeedbackConfig()
    segmentation: ResidualHoughSegmentationConfigV2 = default_alternate_cfo_config()
    dealias: CfoDealiasConfigV1 = default_cfo_dealias_config()
    seeded_alias_em: SeededAliasEmConfigV1 = SeededAliasEmConfigV1()
    replay_gate: ReplayGateConfigV4 = default_replay_gate_v4()
    association: MultiTargetAssociationConfigV1 = default_multi_target_association_config()


@dataclass(frozen=True, slots=True)
class ReceiverStandardResult:
    products: PathStandardProducts
    final_report: PathStandardReportV2
    documents: dict[str, dict[str, Any]]
    source_bindings: dict[str, dict[str, Any]]


def receiver_standard_configuration_digest(config: ReceiverStandardConfig) -> str:
    """Stable semantic identity for every numerical receiver configuration."""

    document = asdict(config)
    document["dealias"] = config.dealias.model_dump(mode="json")
    document["segmentation"] = config.segmentation.model_dump(mode="json")
    document["seeded_alias_em"] = config.seeded_alias_em.model_dump(mode="json")
    document["replay_gate"] = config.replay_gate.model_dump(mode="json")
    document["association"] = config.association.model_dump(mode="json")
    return canonical_digest(document)


def receiver_standard_implementation_digest() -> str:
    """Stable implementation bundle identity for reusable Standard-v2 bytes."""

    return canonical_digest(
        {
            "pipeline_family": "standard-glrt64-v2",
            "quality": "quality.v1",
            "power": "bounded-power-timeline-v2",
            "waterfall": "standard-numerical-waterfall-v2/bounded-waterfall-v1",
            "probe_schedule": "standard-probe-schedule-v1",
            "pilot_scan": "standard-pilot-scan-v3",
            "trajectory_bank": "standard-trajectory-bank-v3/residual-hough",
            "trajectory_feedback": "standard-trajectory-feedback-v3",
            "trajectory_table": "standard-glrt64-trajectory-table-v3",
            "cfo_alias_map": "cfo-alias-map-v2",
            "dealiased_trajectory_bank": "seed-preserving-dealiased-trajectory-bank-v3",
            "cfo_lift_replay": "cfo-lift-replay-v4",
            "final_trajectory_bank": "final-trajectory-bank-v3",
            "final_trajectory_table": "glrt64-final-trajectory-table-v3",
        }
    )


class SingleReceiverIqReader:
    """Expose one immutable receiver column while retaining sample coordinates."""

    def __init__(self, source: IqReader, receiver_id: int) -> None:
        try:
            self._receiver_index = source.receiver_ids.index(receiver_id)
        except ValueError as error:
            raise ValueError("selected receiver is absent from the IQ source") from error
        self._source = source
        self._receiver_id = receiver_id

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._source.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (self._receiver_id,)

    def iter_blocks(self, *, block_samples: int):
        for block in self._source.iter_blocks(block_samples=block_samples):
            values = np.ascontiguousarray(
                block.samples[:, self._receiver_index : self._receiver_index + 1, :]
            )
            yield IqBlock(
                samples=values,
                metadata=block.metadata.model_copy(update={"receiver_ids": (self._receiver_id,)}),
            )


def run_receiver_standard(
    source: IqReader,
    inputs: PathReportInputs,
    *,
    config: ReceiverStandardConfig | None = None,
    trusted_release_identity: tuple[str, str] | None = None,
) -> ReceiverStandardResult:
    """Execute quality, power, waterfall, pilot, trajectory, replay and report."""

    resolved = config or ReceiverStandardConfig()
    iq = SingleReceiverIqReader(source, inputs.receiver_id)
    expected_configuration_digest, expected_implementation_digest = (
        (
            receiver_standard_configuration_digest(resolved),
            receiver_standard_implementation_digest(),
        )
        if trusted_release_identity is None
        else trusted_release_identity
    )
    if (
        iq.sample_rate_hz != inputs.sample_rate_hz
        or iq.sample_count != inputs.declared_sample_count
        or iq.center_frequency_hz != inputs.input_bind.tuned_center_frequency_hz
    ):
        raise ValueError("receiver input contract disagrees with IQ reader geometry")
    schedule = build_probe_schedule(
        sample_rate_hz=iq.sample_rate_hz,
        sample_count=iq.sample_count,
        subwindow_ms=resolved.feedback.subwindow_ms,
        probe_ms=resolved.feedback.probe_ms,
        probe_offsets_ms=resolved.feedback.probe_offsets_ms,
        maximum_coarse_windows=resolved.feedback.maximum_outer_windows,
    )
    if schedule != inputs.schedule:
        raise ValueError("authoritative receiver schedule differs from report input")
    expected_power_window = resolved.power_window_samples or iq.sample_rate_hz
    if (
        inputs.quality_clipping_abs_threshold != 32_767
        or inputs.power_window_samples != expected_power_window
        or inputs.waterfall_config_digest != resolved.waterfall.digest
        or inputs.maximum_scored_candidates_per_probe
        != resolved.feedback.maximum_scored_candidates_per_probe
        or inputs.maximum_replayed_families != resolved.feedback.maximum_replayed_families
        or inputs.input_bind.science_configuration_digest != expected_configuration_digest
        or inputs.input_bind.science_implementation_digest != expected_implementation_digest
    ):
        raise ValueError("receiver analysis configuration disagrees with report input")

    context = AnalysisContext(
        session_id=inputs.session_id,
        run_id=f"science-{inputs.stream_id}-rx-{inputs.receiver_id}",
        pipeline_release="standard-science-inner-v2",
        scope_key=f"{inputs.stream_id}.rx-{inputs.receiver_id}",
    )
    quality_sink = _MemorySink()
    quality_context = context.model_copy(
        update={"stage_config": {"block_samples": resolved.quality_block_samples}}
    )
    QualityAnalyzer().analyze(quality_context, iq, _NoProducts(), quality_sink)
    quality_document = quality_sink.documents["quality.summary"]
    power_document = measure_power_timeline(
        iq,
        window_samples=resolved.power_window_samples,
        block_samples=resolved.power_block_samples,
    )
    waterfall_document = numerical_waterfall_document(
        bounded_waterfall(iq, resolved.waterfall),
        resolved.waterfall,
    )

    detections = scan_pilot_detections(iq, resolved.feedback, edge=inputs.input_bind.starlink_edge)
    bank, representatives = fit_residual_hough_pilot_trajectories(
        detections, resolved.feedback, resolved.segmentation
    )
    replay = replay_pilot_trajectories(
        iq,
        detections,
        representatives,
        resolved.feedback,
        edge=inputs.input_bind.starlink_edge,
    )
    stable_feedback = standard_v3_trajectory_documents(
        detections=detections,
        bank=bank,
        representatives=representatives,
        replay=replay,
        coarse_window_samples=iq.sample_rate_hz,
        subwindow_samples=iq.sample_rate_hz * resolved.feedback.subwindow_ms // 1_000,
        probe_samples=iq.sample_rate_hz * resolved.feedback.probe_ms // 1_000,
        maximum_scored_candidates_per_probe=(resolved.feedback.maximum_scored_candidates_per_probe),
        probe_schedule_digest=inputs.schedule.schedule_digest,
    )
    pilot_digest = canonical_digest(stable_feedback["standard.pilot-scan"])
    raw_bank_digest = canonical_digest(stable_feedback["standard.trajectory-bank"])
    alias_map = build_cfo_alias_map(
        bank,
        representatives,
        pilot_scan_digest=pilot_digest,
        raw_bank_digest=raw_bank_digest,
        config=resolved.dealias,
    )
    canonical_bank = fit_seed_preserving_dealiased_trajectories(
        trajectory_observations(detections),
        representatives,
        alias_map,
        raw_bank_digest=raw_bank_digest,
        config=resolved.dealias,
        seeded_em_config=resolved.seeded_alias_em,
    )
    replay_gate = (
        resolved.replay_gate
        if resolved.replay_gate.sample_rate_hz == iq.sample_rate_hz
        else resolved.replay_gate.model_copy(update={"sample_rate_hz": iq.sample_rate_hz})
    )
    lift_replay = replay_observed_cfo_lifts_v4(
        iq,
        detections,
        canonical_bank,
        resolved.feedback,
        edge=inputs.input_bind.starlink_edge,
        path_input_binding_digest=inputs.input_bind.binding_digest,
        pilot_scan_digest=pilot_digest,
        dealias_config=resolved.dealias,
        gate_config=replay_gate,
    )
    final_bank = select_final_trajectories_v3(
        canonical_bank,
        lift_replay,
        config=resolved.dealias,
    )
    final_table = build_final_trajectory_table_v3(final_bank)
    bound_source_documents: dict[str, dict[str, Any]] = {
        "quality.summary": quality_document,
        STANDARD_POWER_TIMELINE_KIND: power_document,
        STANDARD_NUMERICAL_WATERFALL_KIND: waterfall_document,
        "standard.probe-schedule": inputs.schedule.model_dump(mode="json"),
        **stable_feedback,
    }
    raw_source_bindings = build_standard_source_bindings(
        inputs.input_bind,
        bound_source_documents,
    )
    documents = {
        key: value
        for key, value in bound_source_documents.items()
        if key != "standard.probe-schedule"
    }
    documents.update(
        {
            "standard.cfo-alias-map": alias_map.model_dump(mode="json"),
            "standard.dealiased-trajectory-bank": canonical_bank.model_dump(mode="json"),
            "standard.cfo-lift-replay": lift_replay.model_dump(mode="json"),
            "standard.final-trajectory-bank": final_bank.model_dump(mode="json"),
            "standard.glrt64-final-trajectory-table": final_table.model_dump(mode="json"),
        }
    )
    final_source_bindings = build_standard_final_source_bindings(
        inputs.input_bind,
        {
            kind: documents[kind]
            for kind in (
                "standard.cfo-alias-map",
                "standard.dealiased-trajectory-bank",
                "standard.cfo-lift-replay",
                "standard.final-trajectory-bank",
                "standard.glrt64-final-trajectory-table",
            )
        },
        raw_source_bindings,
    )
    products = build_path_standard_report(
        inputs,
        quality_document=quality_document,
        power_document=power_document,
        waterfall_document=waterfall_document,
        pilot_document=documents["standard.pilot-scan"],
        trajectory_document=documents["standard.trajectory-bank"],
        feedback_document=documents["standard.trajectory-feedback"],
        trajectory_table_document=documents["standard.glrt64-trajectory-table"],
        source_binding_documents=raw_source_bindings,
    )
    final_report = build_path_standard_report_v2(
        products.report,
        alias_map=alias_map,
        dealiased_bank=canonical_bank,
        lift_replay=lift_replay,
        final_bank=final_bank,
        final_table=final_table,
    )
    return ReceiverStandardResult(
        products=products,
        final_report=final_report,
        documents=documents,
        source_bindings={**raw_source_bindings, **final_source_bindings},
    )


class _NoProducts:
    def read_subject_binding(self) -> dict[str, JsonValue]:
        raise KeyError("subject binding is unavailable")

    def read_json(self, _requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        return None

    def read_json_many(
        self,
        _requirement: ProductRequirement,
        *,
        producer_node_ids: tuple[str, ...],
    ) -> tuple[UpstreamJsonProduct, ...]:
        del producer_node_ids
        return ()

    def read_json_bound(
        self,
        _requirement: ProductRequirement,
    ) -> UpstreamJsonProduct | None:
        return None


class _MemorySink:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        copied = cast(dict[str, Any], document)
        self.documents[product.kind] = copied
        payload = canonical_json_bytes(copied)
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )
