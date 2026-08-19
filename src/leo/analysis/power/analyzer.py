"""Deterministic bounded-memory mean complex power for native CI16 IQ."""

from __future__ import annotations

import math
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

CI16_FULL_SCALE = 32_768
CI16_FULL_SCALE_SQUARED = CI16_FULL_SCALE**2


class PowerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PowerConfig(PowerModel):
    schema_version: Literal[1] = 1
    block_samples: Annotated[int, Field(ge=1, le=1_000_000)] = 262_144


class PowerReceiverV1(PowerModel):
    schema_version: Literal[1] = 1
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    mean_power_full_scale_squared: Annotated[float | None, Field(ge=0.0)]
    mean_power_dbfs: float | None
    rms_complex_amplitude_full_scale: Annotated[float | None, Field(ge=0.0)]


class PowerReportV1(PowerModel):
    """Mean power with a precise complex CI16 normalization.

    ``mean_power_full_scale_squared`` is
    ``E[I**2 + Q**2] / 32768**2``. Therefore a complex sinusoid with
    full-scale magnitude is approximately 0 dBFS. Exact zero power is encoded
    as a null dBFS value rather than non-finite JSON.
    """

    schema_version: Literal[1] = 1
    sample_rate_hz: Annotated[int, Field(gt=0)]
    expected_sample_count: Annotated[int, Field(ge=0)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    coverage_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    uncovered_region_count: Annotated[int, Field(ge=0)]
    normalization: Literal["E[I^2+Q^2]/32768^2"] = "E[I^2+Q^2]/32768^2"
    logarithmic_unit: Literal["dBFS"] = "dBFS"
    receivers: tuple[PowerReceiverV1, ...]


class PowerAnalyzer:
    PRODUCT: ClassVar[ProductSpec] = ProductSpec(
        kind="power.summary",
        schema_version=1,
        role=ProductRole.SCIENTIFIC,
    )
    spec: ClassVar[StageSpec] = StageSpec(
        key="power",
        algorithm_version="1.0.0",
        configuration_schema="power.v1",
        dependencies=("quality",),
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
        config = PowerConfig.model_validate(context.stage_config)
        sums = {receiver_id: 0 for receiver_id in iq.receiver_ids}
        observed = 0
        cursor = 0
        uncovered_regions = 0

        for block in validated_blocks(iq, block_samples=config.block_samples):
            start = block.metadata.session_sample_start
            if start > cursor:
                uncovered_regions += 1
            widened = block.samples.astype(np.int64, copy=False)
            squared = widened * widened
            for index, receiver_id in enumerate(iq.receiver_ids):
                block_sum = np.sum(squared[:, index, :], dtype=np.int64)
                sums[receiver_id] += int(block_sum)
            observed += block.metadata.sample_count
            cursor = start + block.metadata.sample_count

        if cursor < iq.sample_count:
            uncovered_regions += 1
        missing = iq.sample_count - observed
        coverage = observed / iq.sample_count if iq.sample_count else 0.0
        receiver_reports: list[PowerReceiverV1] = []
        for receiver_id in iq.receiver_ids:
            if observed == 0:
                linear_power = None
                dbfs = None
                rms = None
            else:
                linear_power = sums[receiver_id] / (observed * CI16_FULL_SCALE_SQUARED)
                dbfs = 10.0 * math.log10(linear_power) if linear_power > 0.0 else None
                rms = math.sqrt(linear_power)
            receiver_reports.append(
                PowerReceiverV1(
                    receiver_id=receiver_id,
                    observed_sample_count=observed,
                    mean_power_full_scale_squared=linear_power,
                    mean_power_dbfs=dbfs,
                    rms_complex_amplitude_full_scale=rms,
                )
            )

        report = PowerReportV1(
            sample_rate_hz=iq.sample_rate_hz,
            expected_sample_count=iq.sample_count,
            observed_sample_count=observed,
            missing_sample_count=missing,
            coverage_fraction=coverage,
            uncovered_region_count=uncovered_regions,
            receivers=tuple(receiver_reports),
        )
        published = outputs.publish_json(self.PRODUCT, report.model_dump(mode="json"))

        if observed == 0:
            outcome = StageOutcome.INSUFFICIENT_DATA
            message = "no IQ samples were available"
        elif missing or uncovered_regions:
            outcome = StageOutcome.PARTIAL_COVERAGE
            message = "power metrics cover only part of the declared sample span"
        else:
            outcome = StageOutcome.COMPLETE
            message = None
        return StageResult(
            outcome=outcome,
            products=(published,),
            summary={
                "coverage_fraction": coverage,
                "observed_sample_count": observed,
            },
            message=message,
        )
