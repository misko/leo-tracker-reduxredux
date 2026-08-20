"""Typed operational composition for calibration predeclare, queue, promote and show."""

from __future__ import annotations

from typing import Literal, Protocol

from leo.application.frequency_calibration import (
    DurableCalibrationPublicationRefV1,
    ImmutableDocumentRefV1,
    TrustedCalibrationDwellInputV1,
    TrustedFrequencyCalibrationPromoter,
    TrustedReleaseEvidencePort,
)
from leo.contracts.base import ContractModel
from leo.contracts.calibration import ReceiverFrequencyCalibrationSetV1
from leo.qualification.frequency_calibration import (
    FrequencyCalibrationPlanV1,
    frozen_topology_for_radio,
)
from leo.qualification.frequency_calibration_documents import ImmutableCalibrationPlanStore
from leo.qualification.frequency_calibration_stage import CALIBRATION_EXTRACTOR_STAGE
from leo.qualification.frequency_calibration_store import AuthoritativeCalibrationResolver


class CalibrationQueuePort(Protocol):
    def queue_evidence_only(
        self,
        *,
        plan: FrequencyCalibrationPlanV1,
        session_id: str,
        pipeline_release_id: str,
        selected_stage_key: str,
        promotion_policy: Literal["evidence_only"],
    ) -> str: ...


class CalibrationCatalogProjectionV1(ContractModel):
    schema_version: Literal[1] = 1
    promotion_id: str
    publication: DurableCalibrationPublicationRefV1
    calibration_set_id: str
    calibration_ids: tuple[str, ...]


class CalibrationCatalogPort(Protocol):
    def promotion_inputs(
        self,
        plan: FrequencyCalibrationPlanV1,
    ) -> tuple[TrustedCalibrationDwellInputV1, ...]: ...

    def publish(
        self,
        publication: DurableCalibrationPublicationRefV1,
    ) -> CalibrationCatalogProjectionV1: ...

    def lookup(self, promotion_id: str) -> CalibrationCatalogProjectionV1: ...


class CalibrationPredeclarationResultV1(ContractModel):
    schema_version: Literal[1] = 1
    plan_ref: ImmutableDocumentRefV1
    plan: FrequencyCalibrationPlanV1


class CalibrationQueueResultV1(ContractModel):
    schema_version: Literal[1] = 1
    plan_ref: ImmutableDocumentRefV1
    stage_key: str
    promotion_policy: Literal["evidence_only"] = "evidence_only"
    session_run_ids: tuple[tuple[str, str], ...]


class CalibrationPromotionResultV1(ContractModel):
    schema_version: Literal[1] = 1
    publication: DurableCalibrationPublicationRefV1
    calibration_set: ReceiverFrequencyCalibrationSetV1
    catalog: CalibrationCatalogProjectionV1


class CalibrationOperations:
    def __init__(
        self,
        *,
        plans: ImmutableCalibrationPlanStore,
        releases: TrustedReleaseEvidencePort,
        queue: CalibrationQueuePort,
        promoter: TrustedFrequencyCalibrationPromoter,
        resolver: AuthoritativeCalibrationResolver,
        catalog: CalibrationCatalogPort,
        pipeline_release_id: str,
    ) -> None:
        self._plans = plans
        self._releases = releases
        self._queue = queue
        self._promoter = promoter
        self._resolver = resolver
        self._catalog = catalog
        self._pipeline_release_id = pipeline_release_id

    def predeclare(
        self,
        *,
        plan_id: str,
        radio_id: str,
        scheduled_session_ids: tuple[str, ...],
    ) -> CalibrationPredeclarationResultV1:
        if len(scheduled_session_ids) < 3 or len(set(scheduled_session_ids)) != len(
            scheduled_session_ids
        ):
            raise ValueError("calibration predeclaration requires at least three unique sessions")
        expected_evidence_uri = f"qualification://frequency-calibration/{plan_id}/evidence.json"
        release = self._releases.current_release()
        serial, physical_path, epoch, topology_digest = frozen_topology_for_radio(radio_id)

        def build(sealed_utc_ns: int) -> FrequencyCalibrationPlanV1:
            return FrequencyCalibrationPlanV1.create(
                plan_id=plan_id,
                declared_utc_ns=sealed_utc_ns,
                radio_id=radio_id,
                radio_serial=serial,
                physical_receiver_id=physical_path,
                hardware_epoch_id=epoch,
                topology_evidence_digest=topology_digest,
                scheduled_session_ids=scheduled_session_ids,
                extractor_git_revision=release.git_revision,
                extractor_source_tree_digest=release.source_tree_digest,
                extractor_executable_digest=release.executable_digest,
                evidence_uri=expected_evidence_uri,
                starlink_channel="ch4",
                starlink_edge="lower",
            )

        ref = self._plans.publish_builder(plan_id, build)
        stored = self._plans.load(ref)
        return CalibrationPredeclarationResultV1(
            plan_ref=ref,
            plan=FrequencyCalibrationPlanV1.model_validate(stored.document),
        )

    def queue(self, plan_ref: ImmutableDocumentRefV1) -> CalibrationQueueResultV1:
        plan = FrequencyCalibrationPlanV1.model_validate(self._plans.load(plan_ref).document)
        queued = tuple(
            (
                session_id,
                self._queue.queue_evidence_only(
                    plan=plan,
                    session_id=session_id,
                    pipeline_release_id=self._pipeline_release_id,
                    selected_stage_key=CALIBRATION_EXTRACTOR_STAGE.key,
                    promotion_policy="evidence_only",
                ),
            )
            for session_id in plan.scheduled_session_ids
        )
        return CalibrationQueueResultV1(
            plan_ref=plan_ref,
            stage_key=CALIBRATION_EXTRACTOR_STAGE.key,
            session_run_ids=queued,
        )

    def promote(
        self,
        *,
        plan_ref: ImmutableDocumentRefV1,
        promotion_id: str,
        calibration_id: str,
        calibration_set_id: str,
        valid_until_utc_ns: int | None = None,
    ) -> CalibrationPromotionResultV1:
        plan = FrequencyCalibrationPlanV1.model_validate(self._plans.load(plan_ref).document)
        publication = self._promoter.promote(
            plan_ref=plan_ref,
            dwell_inputs=self._catalog.promotion_inputs(plan),
            promotion_id=promotion_id,
            calibration_id=calibration_id,
            calibration_set_id=calibration_set_id,
            valid_until_utc_ns=valid_until_utc_ns,
        )
        calibration_set = self._resolver.resolve(publication)
        projection = self._catalog.publish(publication)
        return CalibrationPromotionResultV1(
            publication=publication,
            calibration_set=calibration_set,
            catalog=projection,
        )

    def show(self, promotion_id: str) -> CalibrationPromotionResultV1:
        projection = self._catalog.lookup(promotion_id)
        calibration_set = self._resolver.resolve(projection.publication)
        if (
            projection.calibration_set_id != calibration_set.calibration_set_id
            or projection.calibration_ids
            != tuple(item.calibration_id for item in calibration_set.calibrations)
        ):
            raise ValueError("calibration catalog projection differs from durable publication")
        return CalibrationPromotionResultV1(
            publication=projection.publication,
            calibration_set=calibration_set,
            catalog=projection,
        )
