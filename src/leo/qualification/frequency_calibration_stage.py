"""Evidence-only pipeline stage for frozen WP11 calibration extraction."""

from __future__ import annotations

from typing import Protocol, cast

from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    ResourceClass,
    StageOutcome,
    StageResult,
    StageSpec,
)
from leo.qualification.frequency_calibration import (
    CalibrationCaptureEnvelopeV1,
    FrequencyCalibrationPlanV1,
)
from leo.qualification.frequency_calibration_extractor import (
    EXTRACTOR_PRODUCT,
    BlindPilotCalibrationExtractor,
    ExactWindowIqReader,
)

CALIBRATION_EXTRACTOR_STAGE = StageSpec(
    key="wp11-frequency-calibration-extractor",
    algorithm_version="1.0.0",
    configuration_schema="wp11-frequency-calibration-extractor.v1",
    output_products=(EXTRACTOR_PRODUCT,),
    resource_class=ResourceClass.HEAVY,
)


class CalibrationExtractorScopeProvider(Protocol):
    def resolve(
        self,
        context: AnalysisContext,
        iq: IqReader,
    ) -> tuple[FrequencyCalibrationPlanV1, CalibrationCaptureEnvelopeV1]: ...


class CalibrationExtractorAnalyzer:
    """Publish the workspace evidence product; never public calibration truth."""

    spec = CALIBRATION_EXTRACTOR_STAGE

    def __init__(self, scopes: CalibrationExtractorScopeProvider) -> None:
        self._scopes = scopes

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        _products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        plan, capture = self._scopes.resolve(context, iq)
        if (
            context.session_id != capture.manifest.session_id
            or context.scope_key != capture.stream_id
        ):
            raise ValueError("calibration stage scope differs from capture envelope")
        receipt, published = BlindPilotCalibrationExtractor().publish(
            plan=plan,
            capture=capture,
            reader=cast(ExactWindowIqReader, iq),
            sink=outputs,
        )
        return StageResult(
            outcome=StageOutcome.COMPLETE,
            products=(published,),
            summary={
                "product_scope": receipt.product_scope,
                "acceptance_eligible": receipt.acceptance_eligible,
                "observation_count": len(receipt.observations),
                "candidate_count": sum(
                    item.decision == "candidate" for item in receipt.observations
                ),
                "receipt_digest": receipt.receipt_digest,
                "plan_id": plan.plan_id,
                "plan_digest": plan.plan_digest,
            },
            message="evidence-only calibration extraction completed",
        )
