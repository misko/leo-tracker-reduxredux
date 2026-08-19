"""Production-only composition for authoritative trusted-campaign publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from sqlalchemy import Engine

from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.frequency_calibration import (
    ImmutableDocumentRefV1,
    NativeReleaseCalibrationEvidenceAdapter,
)
from leo.application.trusted_campaign import (
    ConfinedLegacyExecutionAuthority,
    ImmutableCaptureCampaignAuthority,
    TrustedCampaignFinalizer,
    TrustedCampaignMemberInput,
    TrustedCampaignPublicationV1,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository
from leo.catalog.database import create_catalog_engine, create_session_factory
from leo.qualification.frequency_calibration_store import (
    AuthoritativeCalibrationResolver,
    ImmutableCalibrationPromotionStore,
)
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.trusted_campaign_store import ImmutableTrustedCampaignStore
from leo.storage import PinnedLocalRoot, RecordingStore


@dataclass(frozen=True, slots=True)
class TrustedCampaignProductionSettings:
    database_url: str
    bulk_root: Path
    qualification_root: Path
    capture_evidence_root: Path
    legacy_evidence_root: Path
    pipeline_release_id: str
    current_release_link: Path = Path("/opt/leo-tracker/current")
    deployment_root: Path = Path("/opt/leo-tracker")
    scratch_root: Path = Path("/var/tmp")


class TrustedCampaignService:
    """Narrow facade; publication capabilities and stores never leave composition."""

    def __init__(
        self,
        finalizer: TrustedCampaignFinalizer,
        *,
        engine: Engine,
        artifacts: AnalysisArtifactStore,
        recordings: RecordingStore,
        capture: ImmutableCaptureCampaignAuthority,
        legacy: ConfinedLegacyExecutionAuthority,
        calibration_store: ImmutableCalibrationPromotionStore,
        outputs: ImmutableTrustedCampaignStore,
    ) -> None:
        self.__finalizer = finalizer
        self.__engine = engine
        self.__artifacts = artifacts
        self.__recordings = recordings
        self.__capture = capture
        self.__legacy = legacy
        self.__calibration_store = calibration_store
        self.__outputs = outputs
        self.__closed = False

    def finalize(
        self,
        *,
        campaign_id: str,
        capture_ref: ImmutableDocumentRefV1,
        members: tuple[TrustedCampaignMemberInput, ...],
    ) -> TrustedCampaignPublicationV1:
        self.__require_open()
        return self.__finalizer.finalize(
            campaign_id=campaign_id,
            capture_ref=capture_ref,
            members=members,
        )

    def resolve(self, campaign_id: str) -> TrustedCampaignPublicationV1:
        self.__require_open()
        return self.__finalizer.resolve_publication(campaign_id)

    def close(self) -> None:
        if self.__closed:
            return
        self.__closed = True
        self.__outputs.close()
        self.__calibration_store.close()
        self.__legacy.close()
        self.__capture.close()
        self.__recordings.close()
        self.__artifacts.close()
        self.__engine.dispose()

    def __enter__(self) -> TrustedCampaignService:
        self.__require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def __require_open(self) -> None:
        if self.__closed:
            raise RuntimeError("trusted campaign service is closed")


def open_trusted_campaign_service(
    settings: TrustedCampaignProductionSettings,
) -> TrustedCampaignService:
    """Own every concrete authority and expose only the narrow service facade."""

    engine = create_catalog_engine(settings.database_url)
    artifacts: AnalysisArtifactStore | None = None
    recordings: RecordingStore | None = None
    capture: ImmutableCaptureCampaignAuthority | None = None
    legacy: ConfinedLegacyExecutionAuthority | None = None
    calibration_store: ImmutableCalibrationPromotionStore | None = None
    outputs: ImmutableTrustedCampaignStore | None = None
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        catalog = CatalogRepository(create_session_factory(engine))
        artifacts = AnalysisArtifactStore.open_pinned(PinnedLocalRoot(settings.bulk_root))
        recordings = RecordingStore.open_pinned(PinnedLocalRoot(settings.bulk_root))
        capture = ImmutableCaptureCampaignAuthority(PinnedLocalRoot(settings.capture_evidence_root))
        legacy = ConfinedLegacyExecutionAuthority(PinnedLocalRoot(settings.legacy_evidence_root))
        releases = NativeReleaseCalibrationEvidenceAdapter(
            settings.pipeline_release_id,
            current_link=settings.current_release_link,
            deployment_root=settings.deployment_root,
        )
        calibration_store = ImmutableCalibrationPromotionStore(
            settings.qualification_root / "frequency-calibration-promotions"
        )
        calibration_resolver = AuthoritativeCalibrationResolver(
            calibration_store,
            releases,
            allowed_release_ids=(settings.pipeline_release_id,),
        )
        calibrations = PostgresCalibrationCatalogAdapter(catalog, calibration_resolver)
        outputs = ImmutableTrustedCampaignStore(PinnedLocalRoot(settings.qualification_root))
        finalizer = TrustedCampaignFinalizer._bootstrap_production(
            catalog=catalog,
            artifacts=artifacts,
            recordings=recordings,
            calibrations=calibrations,
            capture=capture,
            legacy=legacy,
            releases=releases,
            native_executor=ReleaseLocalNativeEvidenceExecutor(scratch_root=settings.scratch_root),
            outputs=outputs,
        )
        return TrustedCampaignService(
            finalizer,
            engine=engine,
            artifacts=artifacts,
            recordings=recordings,
            capture=capture,
            legacy=legacy,
            calibration_store=calibration_store,
            outputs=outputs,
        )
    except Exception:
        if outputs is not None:
            outputs.close()
        if calibration_store is not None:
            calibration_store.close()
        if legacy is not None:
            legacy.close()
        if capture is not None:
            capture.close()
        if recordings is not None:
            recordings.close()
        if artifacts is not None:
            artifacts.close()
        engine.dispose()
        raise
