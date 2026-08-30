"""Production-only composition for authoritative trusted-campaign publication."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from sqlalchemy import Engine
from sqlalchemy.engine import Connection

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
    _trusted_finalizer_is_registered,
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


class TrustedCampaignService(Protocol):
    def finalize(
        self,
        *,
        campaign_id: str,
        capture_ref: ImmutableDocumentRefV1,
        members: tuple[TrustedCampaignMemberInput, ...],
    ) -> TrustedCampaignPublicationV1: ...

    def resolve(self, campaign_id: str) -> TrustedCampaignPublicationV1: ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


_SERVICE_TOKEN = object()


class _TrustedCampaignService:
    """Capability-owning implementation hidden behind the public narrow protocol."""

    __slots__ = (
        "__finalizer",
        "__engine",
        "__artifacts",
        "__recordings",
        "__capture",
        "__legacy",
        "__calibration_store",
        "__outputs",
        "__closed",
    )

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
        token: object,
    ) -> None:
        if token is not _SERVICE_TOKEN:
            raise TypeError("trusted campaign facade is factory-owned")
        sentinel = getattr(finalizer, "_initialization_sentinel", None)
        if (
            type(finalizer) is not TrustedCampaignFinalizer
            or sentinel is None
            or not _trusted_finalizer_is_registered(finalizer, sentinel)
        ):
            raise TypeError("trusted campaign facade requires a registered finalizer")
        if (
            type(artifacts) is not AnalysisArtifactStore
            or type(recordings) is not RecordingStore
            or type(capture) is not ImmutableCaptureCampaignAuthority
            or type(legacy) is not ConfinedLegacyExecutionAuthority
            or type(calibration_store) is not ImmutableCalibrationPromotionStore
            or type(outputs) is not ImmutableTrustedCampaignStore
        ):
            raise TypeError("trusted campaign facade requires concrete owned authorities")
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
        _close_all(
            self.__outputs.close,
            self.__calibration_store.close,
            self.__legacy.close,
            self.__capture.close,
            self.__recordings.close,
            self.__artifacts.close,
            self.__engine.dispose,
        )

    def __enter__(self) -> _TrustedCampaignService:
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
    qualification: PinnedLocalRoot | None = None
    try:
        with engine.connect() as connection:
            _require_authoritative_schema(connection)
        catalog = CatalogRepository(create_session_factory(engine))
        releases = NativeReleaseCalibrationEvidenceAdapter(
            settings.pipeline_release_id,
            current_link=settings.current_release_link,
            deployment_root=settings.deployment_root,
        )
        current_release = releases.current_release()
        if current_release.release_id != settings.pipeline_release_id:
            raise ValueError("configured pipeline release differs from deployed current release")
        bulk = PinnedLocalRoot(settings.bulk_root)
        try:
            artifacts = AnalysisArtifactStore.open_pinned(bulk)
            recordings = RecordingStore.open_pinned(bulk)
            if artifacts.pinned_root_identity != recordings.pinned_root_identity:
                raise RuntimeError("artifact and recording stores do not share one pinned root")
        finally:
            bulk.close()
        qualification = PinnedLocalRoot(settings.qualification_root)
        capture_namespace: PinnedLocalRoot | None = None
        legacy_namespace: PinnedLocalRoot | None = None
        try:
            capture_namespace = _qualification_child(qualification, settings.capture_evidence_root)
            legacy_namespace = _qualification_child(qualification, settings.legacy_evidence_root)
            capture = ImmutableCaptureCampaignAuthority(capture_namespace)
            legacy = ConfinedLegacyExecutionAuthority(legacy_namespace)
        finally:
            if capture_namespace is not None:
                capture_namespace.close()
            if legacy_namespace is not None:
                legacy_namespace.close()
        calibration_namespace = qualification.child("frequency-calibration-promotions")
        try:
            calibration_store = ImmutableCalibrationPromotionStore.open_pinned(
                calibration_namespace
            )
        finally:
            calibration_namespace.close()
        calibration_resolver = AuthoritativeCalibrationResolver(
            calibration_store,
            releases,
            allowed_release_ids=(settings.pipeline_release_id,),
        )
        calibrations = PostgresCalibrationCatalogAdapter(catalog, calibration_resolver)
        outputs = ImmutableTrustedCampaignStore(qualification)
        qualification.close()
        qualification = None
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
        return _TrustedCampaignService(
            finalizer,
            engine=engine,
            artifacts=artifacts,
            recordings=recordings,
            capture=capture,
            legacy=legacy,
            calibration_store=calibration_store,
            outputs=outputs,
            token=_SERVICE_TOKEN,
        )
    except Exception:
        _close_all(
            None if outputs is None else outputs.close,
            None if calibration_store is None else calibration_store.close,
            None if legacy is None else legacy.close,
            None if capture is None else capture.close,
            None if recordings is None else recordings.close,
            None if artifacts is None else artifacts.close,
            None if qualification is None else qualification.close,
            engine.dispose,
            suppress_errors=True,
        )
        raise


def _require_authoritative_schema(connection: Connection) -> None:
    try:
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        columns = set(
            connection.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'scientific_campaign'"
            ).scalars()
        )
        trigger = connection.exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM pg_trigger trigger "
            "JOIN pg_class relation ON relation.oid = trigger.tgrelid "
            "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
            "JOIN pg_proc function ON function.oid = trigger.tgfoid "
            "JOIN pg_namespace function_namespace "
            "ON function_namespace.oid = function.pronamespace "
            "WHERE relation.relname = 'scientific_campaign' "
            "AND namespace.nspname = current_schema() "
            "AND trigger.tgname = 'scientific_campaign_authority_version_fence' "
            "AND trigger.tgenabled = 'O' "
            "AND trigger.tgtype = 23 "
            "AND function.proname = 'scientific_campaign_authority_version_fence' "
            "AND function_namespace.nspname = current_schema() "
            "AND NOT trigger.tgisinternal)"
        ).scalar_one()
    except Exception as error:
        raise RuntimeError("trusted campaign catalog schema is unavailable") from error
    required_columns = {"outer_seal_uri", "outer_seal_digest", "seal_authority_version"}
    if version != "4e8c1b7a2d90" or not required_columns.issubset(columns) or not trigger:
        raise RuntimeError("trusted campaign catalog is not at the authoritative schema head")


def _qualification_child(root: PinnedLocalRoot, requested: Path) -> PinnedLocalRoot:
    normalized = Path(os.path.normpath(os.fspath(requested)))
    if not normalized.is_absolute() or normalized.parent != root.root:
        raise ValueError("qualification authority root must be a direct configured child")
    return root.child(normalized.name)


def _close_all(
    *callbacks: Callable[[], object] | None,
    suppress_errors: bool = False,
) -> None:
    errors: list[BaseException] = []
    for callback in callbacks:
        if callback is None:
            continue
        try:
            callback()
        except BaseException as error:
            errors.append(error)
    if suppress_errors or not errors:
        return
    if len(errors) == 1:
        raise errors[0]
    raise BaseExceptionGroup("trusted campaign resource cleanup failed", errors)
