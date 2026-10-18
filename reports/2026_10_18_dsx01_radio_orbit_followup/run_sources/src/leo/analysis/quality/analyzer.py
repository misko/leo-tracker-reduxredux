"""Deterministic bounded-memory quality metrics for native CI16 IQ."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from leo.analysis._streaming import validated_blocks
from leo.pipeline.contracts import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRole,
    ProductSpec,
    ResourceClass,
    StageOutcome,
    StageResult,
    StageSpec,
)


class QualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QualityConfig(QualityModel):
    schema_version: Literal[1] = 1
    block_samples: Annotated[int, Field(ge=1, le=1_000_000)] = 262_144
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)] = 32_767


class QualityReceiverV1(QualityModel):
    schema_version: Literal[1] = 1
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    clipped_component_count: Annotated[int, Field(ge=0)]
    clipped_complex_sample_count: Annotated[int, Field(ge=0)]
    clipped_complex_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    constant_iq: bool
    minimum_i: int | None
    maximum_i: int | None
    minimum_q: int | None
    maximum_q: int | None


class QualityReportV1(QualityModel):
    schema_version: Literal[1] = 1
    sample_rate_hz: Annotated[int, Field(gt=0)]
    expected_sample_count: Annotated[int, Field(ge=0)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    coverage_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    uncovered_region_count: Annotated[int, Field(ge=0)]
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)]
    receivers: tuple[QualityReceiverV1, ...]


class _ReceiverAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.clipped_components = 0
        self.clipped_samples = 0
        self.minimum: np.ndarray | None = None
        self.maximum: np.ndarray | None = None

    def add(self, values: np.ndarray, *, threshold: int) -> None:
        widened = values.astype(np.int32, copy=False)
        magnitudes = np.abs(widened)
        self.count += len(values)
        self.clipped_components += int(np.count_nonzero(magnitudes >= threshold))
        self.clipped_samples += int(np.count_nonzero(np.any(magnitudes >= threshold, axis=1)))
        block_minimum = widened.min(axis=0)
        block_maximum = widened.max(axis=0)
        if self.minimum is None:
            self.minimum = block_minimum
            self.maximum = block_maximum
        else:
            assert self.maximum is not None
            self.minimum = np.minimum(self.minimum, block_minimum)
            self.maximum = np.maximum(self.maximum, block_maximum)

    def report(self, receiver_id: int) -> QualityReceiverV1:
        minimum = self.minimum
        maximum = self.maximum
        if minimum is None or maximum is None:
            return QualityReceiverV1(
                receiver_id=receiver_id,
                observed_sample_count=0,
                clipped_component_count=0,
                clipped_complex_sample_count=0,
                clipped_complex_fraction=0.0,
                constant_iq=False,
                minimum_i=None,
                maximum_i=None,
                minimum_q=None,
                maximum_q=None,
            )
        return QualityReceiverV1(
            receiver_id=receiver_id,
            observed_sample_count=self.count,
            clipped_component_count=self.clipped_components,
            clipped_complex_sample_count=self.clipped_samples,
            clipped_complex_fraction=self.clipped_samples / self.count,
            constant_iq=bool(np.array_equal(minimum, maximum)),
            minimum_i=int(minimum[0]),
            maximum_i=int(maximum[0]),
            minimum_q=int(minimum[1]),
            maximum_q=int(maximum[1]),
        )


class QualityAnalyzer:
    PRODUCT: ClassVar[ProductSpec] = ProductSpec(
        kind="quality.summary",
        schema_version=1,
        role=ProductRole.SCIENTIFIC,
    )
    spec: ClassVar[StageSpec] = StageSpec(
        key="quality",
        algorithm_version="1.0.0",
        configuration_schema="quality.v1",
        output_products=(PRODUCT,),
        resource_class=ResourceClass.STREAMING,
        deterministic=True,
        accepted_outcomes=(
            StageOutcome.COMPLETE,
            StageOutcome.PARTIAL_COVERAGE,
            StageOutcome.INSUFFICIENT_DATA,
        ),
    )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        _products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        config = QualityConfig.model_validate(context.stage_config)
        accumulators = {receiver_id: _ReceiverAccumulator() for receiver_id in iq.receiver_ids}
        observed = 0
        cursor = 0
        uncovered_regions = 0

        for block in validated_blocks(iq, block_samples=config.block_samples):
            start = block.metadata.session_sample_start
            if start > cursor:
                uncovered_regions += 1
            for index, receiver_id in enumerate(iq.receiver_ids):
                accumulators[receiver_id].add(
                    block.samples[:, index, :],
                    threshold=config.clipping_abs_threshold,
                )
            observed += block.metadata.sample_count
            cursor = start + block.metadata.sample_count

        if cursor < iq.sample_count:
            uncovered_regions += 1
        missing = iq.sample_count - observed
        coverage = observed / iq.sample_count if iq.sample_count else 0.0
        report = QualityReportV1(
            sample_rate_hz=iq.sample_rate_hz,
            expected_sample_count=iq.sample_count,
            observed_sample_count=observed,
            missing_sample_count=missing,
            coverage_fraction=coverage,
            uncovered_region_count=uncovered_regions,
            clipping_abs_threshold=config.clipping_abs_threshold,
            receivers=tuple(
                accumulators[receiver_id].report(receiver_id) for receiver_id in iq.receiver_ids
            ),
        )
        published = outputs.publish_json(self.PRODUCT, report.model_dump(mode="json"))

        if observed == 0:
            outcome = StageOutcome.INSUFFICIENT_DATA
            message = "no IQ samples were available"
        elif missing or uncovered_regions:
            outcome = StageOutcome.PARTIAL_COVERAGE
            message = "quality metrics cover only part of the declared sample span"
        else:
            outcome = StageOutcome.COMPLETE
            message = None
        return StageResult(
            outcome=outcome,
            products=(published,),
            summary={
                "coverage_fraction": coverage,
                "observed_sample_count": observed,
                "uncovered_region_count": uncovered_regions,
            },
            message=message,
        )
