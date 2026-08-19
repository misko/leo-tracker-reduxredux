"""Infrastructure-blind complete receiver-path Standard science runner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast

import numpy as np
from pydantic import JsonValue

from leo.analysis.quality import QualityAnalyzer
from leo.analysis.standard.observability import measure_power_timeline
from leo.analysis.standard.probes import build_probe_schedule
from leo.analysis.standard.reports import (
    PathReportInputs,
    PathStandardProducts,
    build_path_standard_report,
    standard_v2_trajectory_documents,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_pilot_trajectories,
    replay_pilot_trajectories,
    scan_pilot_detections,
)
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.digests import canonical_json_bytes, sha256_digest
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


@dataclass(frozen=True, slots=True)
class ReceiverStandardResult:
    products: PathStandardProducts
    documents: dict[str, dict[str, Any]]


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
) -> ReceiverStandardResult:
    """Execute quality, power, waterfall, pilot, trajectory, replay and report."""

    resolved = config or ReceiverStandardConfig()
    iq = SingleReceiverIqReader(source, inputs.receiver_id)
    if (
        iq.sample_rate_hz != inputs.sample_rate_hz
        or iq.sample_count != inputs.declared_sample_count
    ):
        raise ValueError("receiver input contract disagrees with IQ reader geometry")
    schedule = build_probe_schedule(
        sample_rate_hz=iq.sample_rate_hz,
        sample_count=iq.sample_count,
        subwindow_ms=resolved.feedback.subwindow_ms,
        probe_ms=resolved.feedback.probe_ms,
        maximum_coarse_windows=resolved.feedback.maximum_outer_windows,
    )
    if schedule != inputs.schedule:
        raise ValueError("authoritative receiver schedule differs from report input")

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
    waterfall_document = cast(dict[str, Any], asdict(bounded_waterfall(iq, resolved.waterfall)))

    detections = scan_pilot_detections(iq, resolved.feedback)
    bank, representatives = fit_pilot_trajectories(detections, resolved.feedback)
    replay = replay_pilot_trajectories(
        iq,
        detections,
        representatives,
        resolved.feedback,
    )
    stable_feedback = standard_v2_trajectory_documents(
        detections=detections,
        bank=bank,
        representatives=representatives,
        replay=replay,
        coarse_window_samples=iq.sample_rate_hz,
        subwindow_samples=iq.sample_rate_hz * resolved.feedback.subwindow_ms // 1_000,
        probe_samples=iq.sample_rate_hz * resolved.feedback.probe_ms // 1_000,
        maximum_scored_candidates_per_probe=(
            resolved.feedback.maximum_scored_candidates_per_probe
        ),
    )
    documents: dict[str, dict[str, Any]] = {
        "quality.summary": quality_document,
        "power.summary": power_document,
        "waterfall.tiles": waterfall_document,
        **stable_feedback,
    }
    products = build_path_standard_report(
        inputs,
        quality_document=quality_document,
        power_document=power_document,
        waterfall_document=waterfall_document,
        pilot_document=documents["standard.pilot-scan"],
        trajectory_document=documents["standard.trajectory-bank"],
        feedback_document=documents["standard.trajectory-feedback"],
        trajectory_table_document=documents["standard.glrt64-trajectory-table"],
    )
    return ReceiverStandardResult(products=products, documents=documents)


class _NoProducts:
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
