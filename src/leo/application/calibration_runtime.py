"""Concrete catalog and processing adapters for operational calibration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import IntegrityError

from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.calibration_operations import CalibrationCatalogProjectionV1
from leo.application.frequency_calibration import (
    DurableCalibrationPublicationRefV1,
    ImmutableDocumentRefV1,
    TrustedCalibrationDwellInputV1,
)
from leo.catalog import (
    AnalysisRunState,
    CatalogNotFoundError,
    CatalogRepository,
    JobState,
    PromotionPolicy,
)
from leo.contracts.calibration import ReceiverPathIdentityV1
from leo.contracts.digests import canonical_digest
from leo.pipeline import AnalysisContext, IqReader
from leo.processing import ProcessingService
from leo.qualification.frequency_calibration import (
    CalibrationCaptureEnvelopeV1,
    FrequencyCalibrationPlanV1,
)
from leo.qualification.frequency_calibration_documents import ImmutableCalibrationPlanStore
from leo.qualification.frequency_calibration_extractor import EXTRACTOR_PRODUCT
from leo.qualification.frequency_calibration_stage import CALIBRATION_EXTRACTOR_STAGE
from leo.qualification.frequency_calibration_store import AuthoritativeCalibrationResolver
from leo.storage import RecordingStore


class CalibrationOperationalEvidenceError(RuntimeError):
    """Cataloged calibration evidence exists but is not promotion-ready."""


def calibration_run_id(plan: FrequencyCalibrationPlanV1, session_id: str) -> str:
    digest = canonical_digest(
        {
            "kind": "wp11-calibration-extractor-run-v1",
            "plan_digest": plan.plan_digest,
            "session_id": session_id,
        }
    ).removeprefix("sha256:")
    return f"wp11-calibration-{digest}"


class ImmutableCalibrationScopeProvider:
    """Rebuild the exact capture envelope from immutable plan and recording stores."""

    def __init__(self, plans: ImmutableCalibrationPlanStore, recordings: RecordingStore) -> None:
        self._plans = plans
        self._recordings = recordings

    def resolve(
        self,
        context: AnalysisContext,
        _iq: IqReader,
    ) -> tuple[FrequencyCalibrationPlanV1, CalibrationCaptureEnvelopeV1]:
        _ref, plan = self._plans.plan_for_session(context.session_id)
        if context.run_id != calibration_run_id(plan, context.session_id):
            raise ValueError("calibration run is not bound to the immutable plan digest")
        bundle = self._recordings.inspect(context.session_id)
        if len(bundle.manifest.streams) != 1:
            raise ValueError("calibration recording must contain exactly one stream")
        return plan, CalibrationCaptureEnvelopeV1.create(
            recording_uri=bundle.uri,
            manifest_digest=bundle.manifest_sha256,
            manifest=bundle.manifest,
            stream_id=context.scope_key,
            physical_receiver_id=plan.physical_receiver_id,
            hardware_epoch_id=plan.hardware_epoch_id,
            topology_evidence_digest=plan.topology_evidence_digest,
        )


class ProcessingCalibrationQueueAdapter:
    def __init__(
        self,
        catalog: CatalogRepository,
        processing: ProcessingService,
        recordings: RecordingStore,
    ) -> None:
        self._catalog = catalog
        self._processing = processing
        self._recordings = recordings

    def queue_evidence_only(
        self,
        *,
        plan: FrequencyCalibrationPlanV1,
        session_id: str,
        pipeline_release_id: str,
        selected_stage_key: str,
        promotion_policy: Literal["evidence_only"],
    ) -> str:
        if session_id not in plan.scheduled_session_ids:
            raise ValueError("session is absent from calibration predeclaration")
        if selected_stage_key != CALIBRATION_EXTRACTOR_STAGE.key:
            raise ValueError("calibration queue accepts only the frozen extractor stage")
        if promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value:
            raise ValueError("calibration queue is evidence-only")
        bundle = self._recordings.inspect(session_id)
        if len(bundle.manifest.streams) != 1:
            raise ValueError("calibration recording must contain exactly one stream")
        stream_id = bundle.manifest.streams[0].stream_id
        run_id = calibration_run_id(plan, session_id)
        try:
            execution = self._catalog.run_execution_info(run_id)
        except CatalogNotFoundError:
            try:
                self._processing.create_reprocess_run(
                    run_id=run_id,
                    session_id=session_id,
                    pipeline_release_id=pipeline_release_id,
                    input_manifest_digest=bundle.manifest_sha256,
                    scope_keys=(stream_id,),
                    promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
                    stage_keys=(CALIBRATION_EXTRACTOR_STAGE.key,),
                )
            except IntegrityError:
                execution = self._catalog.run_execution_info(run_id)
            else:
                execution = self._catalog.run_execution_info(run_id)
        self._validate_run(
            run_id=run_id,
            session_id=session_id,
            stream_id=stream_id,
            pipeline_release_id=pipeline_release_id,
            manifest_digest=bundle.manifest_sha256,
        )
        return execution.run_id

    def _validate_run(
        self,
        *,
        run_id: str,
        session_id: str,
        stream_id: str,
        pipeline_release_id: str,
        manifest_digest: str,
    ) -> None:
        snapshot = self._catalog.run_seal_snapshot(run_id)
        execution = snapshot.execution
        if (
            execution.session_id != session_id
            or execution.pipeline_release_id != pipeline_release_id
            or execution.input_manifest_digest != manifest_digest
            or execution.promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value
            or tuple((job.stage_key, job.scope_key) for job in snapshot.jobs)
            != ((CALIBRATION_EXTRACTOR_STAGE.key, stream_id),)
        ):
            raise ValueError("existing calibration run differs from requested evidence run")


class PostgresCalibrationOperationsAdapter:
    """Join sealed extractor lineage to the authoritative PostgreSQL adapter."""

    def __init__(
        self,
        repository: CatalogRepository,
        resolver: AuthoritativeCalibrationResolver,
        recordings: RecordingStore,
    ) -> None:
        self._repository = repository
        self._resolver = resolver
        self._recordings = recordings
        self._catalog = PostgresCalibrationCatalogAdapter(repository, resolver)
        self._bootstraps: dict[tuple[str, str, int, str, str], _ReceiverPathBootstrap] = {}

    def promotion_inputs(
        self,
        plan: FrequencyCalibrationPlanV1,
    ) -> tuple[TrustedCalibrationDwellInputV1, ...]:
        try:
            return self._promotion_inputs(plan)
        except CatalogNotFoundError:
            raise
        except (ValueError, RuntimeError) as error:
            raise CalibrationOperationalEvidenceError(str(error)) from error

    def _promotion_inputs(
        self,
        plan: FrequencyCalibrationPlanV1,
    ) -> tuple[TrustedCalibrationDwellInputV1, ...]:
        inputs: list[TrustedCalibrationDwellInputV1] = []
        envelopes: list[CalibrationCaptureEnvelopeV1] = []
        for session_id in plan.scheduled_session_ids:
            snapshot = self._repository.run_seal_snapshot(calibration_run_id(plan, session_id))
            if (
                self._repository.run_state(snapshot.execution.run_id)
                is not AnalysisRunState.SUCCEEDED
                or snapshot.execution.promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value
                or len(snapshot.jobs) != 1
                or snapshot.jobs[0].state != JobState.SUCCEEDED.value
                or snapshot.jobs[0].stage_key != CALIBRATION_EXTRACTOR_STAGE.key
            ):
                raise ValueError("calibration extractor run is not sealed and successful")
            products = tuple(
                product
                for product in snapshot.products
                if product.stage_key == CALIBRATION_EXTRACTOR_STAGE.key
                and product.scope_key == snapshot.jobs[0].scope_key
                and product.kind == EXTRACTOR_PRODUCT.kind
                and product.schema_version == EXTRACTOR_PRODUCT.schema_version
                and product.available
            )
            if len(products) != 1 or len(snapshot.products) != 1:
                raise ValueError("calibration run must seal exactly one extractor product")
            if (
                products[0].summary.get("plan_id") != plan.plan_id
                or products[0].summary.get("plan_digest") != plan.plan_digest
            ):
                raise ValueError("extractor product is not bound to the immutable plan")
            bundle = self._recordings.inspect_uri(snapshot.execution.bundle_uri)
            if bundle.manifest_sha256 != snapshot.execution.input_manifest_digest:
                raise ValueError("catalog recording digest differs from immutable manifest")
            self._recordings.verify(bundle)
            envelopes.append(
                CalibrationCaptureEnvelopeV1.create(
                    recording_uri=bundle.uri,
                    manifest_digest=bundle.manifest_sha256,
                    manifest=bundle.manifest,
                    stream_id=snapshot.jobs[0].scope_key,
                    physical_receiver_id=plan.physical_receiver_id,
                    hardware_epoch_id=plan.hardware_epoch_id,
                    topology_evidence_digest=plan.topology_evidence_digest,
                )
            )
            inputs.append(
                TrustedCalibrationDwellInputV1(
                    session_id=session_id,
                    recording_uri=snapshot.execution.bundle_uri,
                    extractor_product_ref=ImmutableDocumentRefV1(
                        logical_uri=products[0].logical_uri,
                        digest=products[0].digest,
                    ),
                )
            )
        bootstrap = _bootstrap_from_verified_envelopes(plan, tuple(envelopes))
        existing = self._bootstraps.setdefault(bootstrap.key, bootstrap)
        if existing != bootstrap:
            raise ValueError("receiver path bootstrap conflicts across calibration evidence")
        return tuple(inputs)

    def publish(
        self,
        publication: DurableCalibrationPublicationRefV1,
    ) -> CalibrationCatalogProjectionV1:
        value = self._resolver.resolve(publication)
        for calibration in value.calibrations:
            key = (
                calibration.radio_id,
                calibration.radio_serial,
                calibration.receiver_id,
                calibration.physical_receiver_id,
                calibration.hardware_epoch_id,
            )
            try:
                bootstrap = self._bootstraps[key]
            except KeyError as error:
                raise ValueError(
                    "authoritative calibration lacks verified receiver-path bootstrap"
                ) from error
            self._catalog.register_receiver_path(
                bootstrap.identity,
                radio_uri=bootstrap.radio_uri,
                transport=bootstrap.transport,
                hardware_epoch_started_utc_ns=bootstrap.hardware_epoch_started_utc_ns,
            )
        stored = self._catalog.publish(publication)
        return _projection(stored.publication, stored.calibration_set)

    def lookup(self, promotion_id: str) -> CalibrationCatalogProjectionV1:
        stored = self._catalog.lookup(promotion_id)
        return _projection(stored.publication, stored.calibration_set)


def _projection(
    publication: DurableCalibrationPublicationRefV1,
    calibration_set: object,
) -> CalibrationCatalogProjectionV1:
    from leo.contracts.calibration import ReceiverFrequencyCalibrationSetV1

    value = ReceiverFrequencyCalibrationSetV1.model_validate(calibration_set)
    return CalibrationCatalogProjectionV1(
        promotion_id=publication.promotion_id,
        publication=publication,
        calibration_set_id=value.calibration_set_id,
        calibration_ids=tuple(item.calibration_id for item in value.calibrations),
    )


@dataclass(frozen=True, slots=True)
class _ReceiverPathBootstrap:
    identity: ReceiverPathIdentityV1
    radio_uri: str
    transport: str
    hardware_epoch_started_utc_ns: int

    @property
    def key(self) -> tuple[str, str, int, str, str]:
        identity = self.identity
        return (
            identity.radio_id,
            identity.radio_serial,
            identity.receiver_id,
            identity.physical_receiver_id,
            identity.hardware_epoch_id,
        )


def _bootstrap_from_verified_envelopes(
    plan: FrequencyCalibrationPlanV1,
    envelopes: tuple[CalibrationCaptureEnvelopeV1, ...],
) -> _ReceiverPathBootstrap:
    if len(envelopes) != len(plan.scheduled_session_ids):
        raise ValueError("receiver-path bootstrap requires every predeclared dwell")
    if tuple(item.manifest.session_id for item in envelopes) != plan.scheduled_session_ids:
        raise ValueError("receiver-path bootstrap dwell order differs from predeclaration")
    radios = tuple(envelope.manifest.streams[0].radio for envelope in envelopes)
    first_radio = radios[0]
    if any(radio != first_radio for radio in radios[1:]):
        raise ValueError("calibration dwell radio identities disagree")
    if first_radio.radio_id != plan.radio_id or first_radio.serial != plan.radio_serial:
        raise ValueError("capture radio identity differs from frozen calibration plan")
    intervals = tuple(envelope.interval_bounds() for envelope in envelopes)
    first_index = min(range(len(envelopes)), key=lambda index: intervals[index][0])
    envelope = envelopes[first_index]
    start, end = intervals[first_index]
    return _ReceiverPathBootstrap(
        identity=ReceiverPathIdentityV1(
            radio_id=plan.radio_id,
            radio_serial=plan.radio_serial,
            receiver_id=1,
            physical_receiver_id=plan.physical_receiver_id,
            capture_utc_ns=start,
            capture_end_utc_ns=end,
            hardware_epoch_id=plan.hardware_epoch_id,
            session_id=envelope.manifest.session_id,
            stream_id=envelope.stream_id,
            manifest_digest=envelope.manifest_digest,
            profile_revision_digest=(
                envelope.manifest.capture_plan.profile_revision.revision_digest
            ),
        ),
        radio_uri=first_radio.uri,
        transport=first_radio.transport.value,
        hardware_epoch_started_utc_ns=min(start for start, _end in intervals),
    )
