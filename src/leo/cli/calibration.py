"""Typed CLI adapter for operational frequency-calibration composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from leo.application.calibration_operations import (
    CalibrationCatalogPort,
    CalibrationOperations,
    CalibrationQueuePort,
)
from leo.application.calibration_runtime import (
    CalibrationOperationalEvidenceError,
    PostgresCalibrationOperationsAdapter,
    ProcessingCalibrationQueueAdapter,
)
from leo.application.frequency_calibration import (
    CalibrationPromotionError,
    ImmutableDocumentRefV1,
    NativeReleaseCalibrationEvidenceAdapter,
    RecordingStoreCalibrationAdapter,
    TrustedFrequencyCalibrationPromoter,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import ActiveRunExistsError, CatalogNotFoundError, ProductConflictError
from leo.cli.backend import CliBackendError
from leo.cli.models import (
    CalibrationPredeclareDataV1,
    CalibrationPromoteDataV1,
    CalibrationQueueDataV1,
    CalibrationShowDataV1,
    ExitCode,
)
from leo.qualification.frequency_calibration_documents import (
    AnalysisArtifactTrustedDocumentAdapter,
    CalibrationPlanConflict,
    ImmutableCalibrationPlanStore,
)
from leo.qualification.frequency_calibration_native import ReleaseLocalCalibrationExtractor
from leo.qualification.frequency_calibration_store import (
    AuthoritativeCalibrationResolver,
    CalibrationPublicationConflict,
    ImmutableCalibrationPromotionStore,
)
from leo.qualification.native_release import _beneath_qnap
from leo.storage import PinnedLocalRoot, RecordingStore
from leo.storage.errors import BundleNotFoundError


@dataclass(frozen=True, slots=True)
class CalibrationBackendSettings:
    qualification_root: Path
    bulk_root: Path
    pipeline_release_id: str
    current_release_link: Path = Path("/opt/leo-tracker/current")
    deployment_root: Path = Path("/opt/leo-tracker")
    scratch_root: Path = Path("/var/tmp")


class CalibrationCliBackend:
    def __init__(self, operations: CalibrationOperations) -> None:
        self._operations = operations

    def calibration_predeclare(
        self,
        *,
        plan_id: str,
        radio_id: str,
        scheduled_session_ids: tuple[str, ...],
        starlink_channel: Literal["ch4"],
        starlink_edge: Literal["lower"],
    ) -> CalibrationPredeclareDataV1:
        try:
            return CalibrationPredeclareDataV1(
                result=self._operations.predeclare(
                    plan_id=plan_id,
                    radio_id=radio_id,
                    scheduled_session_ids=scheduled_session_ids,
                    starlink_channel=starlink_channel,
                    starlink_edge=starlink_edge,
                )
            )
        except CalibrationPlanConflict as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error

    def calibration_queue(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
    ) -> CalibrationQueueDataV1:
        try:
            return CalibrationQueueDataV1(
                result=self._operations.queue(
                    ImmutableDocumentRefV1(logical_uri=plan_uri, digest=plan_digest)
                )
            )
        except (BundleNotFoundError, CatalogNotFoundError, FileNotFoundError, KeyError) as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except (ActiveRunExistsError, ProductConflictError) as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error

    def calibration_promote(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
        promotion_id: str,
        calibration_id: str,
        calibration_set_id: str,
        valid_until_utc_ns: int | None,
    ) -> CalibrationPromoteDataV1:
        try:
            return CalibrationPromoteDataV1(
                result=self._operations.promote(
                    plan_ref=ImmutableDocumentRefV1(
                        logical_uri=plan_uri,
                        digest=plan_digest,
                    ),
                    promotion_id=promotion_id,
                    calibration_id=calibration_id,
                    calibration_set_id=calibration_set_id,
                    valid_until_utc_ns=valid_until_utc_ns,
                )
            )
        except (CatalogNotFoundError, FileNotFoundError, KeyError) as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except (CalibrationPublicationConflict, ProductConflictError) as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except CalibrationPromotionError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error
        except CalibrationOperationalEvidenceError as error:
            raise CliBackendError(str(error), ExitCode.UNHEALTHY) from error

    def calibration_show(self, promotion_id: str) -> CalibrationShowDataV1:
        try:
            return CalibrationShowDataV1(result=self._operations.show(promotion_id))
        except (CatalogNotFoundError, FileNotFoundError, KeyError) as error:
            raise CliBackendError(
                f"calibration promotion not found: {promotion_id}",
                ExitCode.NOT_FOUND,
            ) from error


def build_calibration_backend(
    settings: CalibrationBackendSettings,
    *,
    queue: CalibrationQueuePort,
    catalog: CalibrationCatalogPort,
) -> CalibrationCliBackend:
    """Compose only pre-created local roots; catalog/queue stay injected ports."""

    for label, root in (
        ("qualification", settings.qualification_root),
        ("bulk", settings.bulk_root),
        ("scratch", settings.scratch_root),
    ):
        if not root.is_absolute() or _beneath_qnap(root):
            raise ValueError(f"calibration {label} root must be absolute local storage")
    pinned_bulk = PinnedLocalRoot(settings.bulk_root)
    recording_store: RecordingStore | None = None
    try:
        recording_store = RecordingStore.open_pinned(pinned_bulk)
        artifact_store = AnalysisArtifactStore.open_pinned(pinned_bulk)
    except Exception:
        if recording_store is not None:
            recording_store.close()
        raise
    finally:
        pinned_bulk.close()
    try:
        return _build_calibration_backend_with_stores(
            settings,
            queue=queue,
            catalog=catalog,
            recording_store=recording_store,
            artifact_store=artifact_store,
        )
    except Exception:
        artifact_store.close()
        recording_store.close()
        raise


def _build_calibration_backend_with_stores(
    settings: CalibrationBackendSettings,
    *,
    queue: CalibrationQueuePort,
    catalog: CalibrationCatalogPort,
    recording_store: RecordingStore,
    artifact_store: AnalysisArtifactStore,
) -> CalibrationCliBackend:
    plans = ImmutableCalibrationPlanStore(
        settings.qualification_root / "frequency-calibration-plans"
    )
    outputs = ImmutableCalibrationPromotionStore(
        settings.qualification_root / "frequency-calibration-promotions"
    )
    releases = NativeReleaseCalibrationEvidenceAdapter(
        settings.pipeline_release_id,
        current_link=settings.current_release_link,
        deployment_root=settings.deployment_root,
    )
    promoter = TrustedFrequencyCalibrationPromoter(
        plans=plans,
        recordings=RecordingStoreCalibrationAdapter(recording_store),
        artifacts=AnalysisArtifactTrustedDocumentAdapter(artifact_store),
        outputs=outputs,
        releases=releases,
        extractor_executor=ReleaseLocalCalibrationExtractor(scratch_root=settings.scratch_root),
    )
    resolver = AuthoritativeCalibrationResolver(
        outputs,
        releases,
        allowed_release_ids=(settings.pipeline_release_id,),
    )
    return CalibrationCliBackend(
        CalibrationOperations(
            plans=plans,
            releases=releases,
            queue=queue,
            promoter=promoter,
            resolver=resolver,
            catalog=catalog,
            pipeline_release_id=settings.pipeline_release_id,
        )
    )


def build_postgres_calibration_backend(
    settings: CalibrationBackendSettings,
    *,
    services: object,
) -> CalibrationCliBackend:
    """Wire the concrete processing queue and authoritative PostgreSQL catalog."""

    from leo.cli.processing import ProcessingServices

    if not isinstance(services, ProcessingServices):
        raise TypeError("calibration composition requires concrete processing services")
    for label, root in (
        ("qualification", settings.qualification_root),
        ("bulk", settings.bulk_root),
        ("scratch", settings.scratch_root),
    ):
        if not root.is_absolute() or _beneath_qnap(root):
            raise ValueError(f"calibration {label} root must be absolute local storage")
    if _beneath_qnap(services.recordings.root):
        raise ValueError("calibration processing services cannot use QNAP")
    expected_bulk = PinnedLocalRoot(settings.bulk_root)
    try:
        if (
            services.recordings.pinned_root_identity != expected_bulk.identity
            or services.artifacts.pinned_root_identity != expected_bulk.identity
        ):
            raise ValueError("calibration processing services require one pinned bulk root")
    finally:
        expected_bulk.close()
    plan_root = settings.qualification_root / "frequency-calibration-plans"
    promotion_root = settings.qualification_root / "frequency-calibration-promotions"
    plans = ImmutableCalibrationPlanStore(plan_root)
    outputs = ImmutableCalibrationPromotionStore(promotion_root)
    releases = NativeReleaseCalibrationEvidenceAdapter(
        settings.pipeline_release_id,
        current_link=settings.current_release_link,
        deployment_root=settings.deployment_root,
    )
    resolver = AuthoritativeCalibrationResolver(
        outputs,
        releases,
        allowed_release_ids=(settings.pipeline_release_id,),
    )
    promoter = TrustedFrequencyCalibrationPromoter(
        plans=plans,
        recordings=RecordingStoreCalibrationAdapter(services.recordings),
        artifacts=AnalysisArtifactTrustedDocumentAdapter(services.artifacts),
        outputs=outputs,
        releases=releases,
        extractor_executor=ReleaseLocalCalibrationExtractor(scratch_root=settings.scratch_root),
    )
    return CalibrationCliBackend(
        CalibrationOperations(
            plans=plans,
            releases=releases,
            queue=ProcessingCalibrationQueueAdapter(
                services.catalog,
                services.processing,
                services.recordings,
            ),
            promoter=promoter,
            resolver=resolver,
            catalog=PostgresCalibrationOperationsAdapter(
                services.catalog,
                resolver,
                services.recordings,
            ),
            pipeline_release_id=settings.pipeline_release_id,
        )
    )
