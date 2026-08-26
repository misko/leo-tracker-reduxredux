"""Production composition for the mostly read-only LAN API and operator UI."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from leo.acquisition import LocalCaptureAuthority
from leo.analysis.research import (
    production_research_v1_configuration,
    production_research_v1_registry,
    research_pipeline_definition_id,
)
from leo.analysis.standard import production_standard_v2_registry
from leo.analysis.standard.native_analyzers import production_standard_native_evidence_registry
from leo.api.app import create_app
from leo.application import (
    CatalogPresentationRepository,
    CatalogStandardNativePresentationRepository,
    CatalogStandardPresentationRepository,
    DefinitionDispatchedStandardPresentationRepository,
    OperatorCaptureControl,
    ResearchReprocessService,
    StandardReprocessService,
)
from leo.application.campaign_presentation import CatalogCampaignPresentation
from leo.application.sky_field import SkyFieldService
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.contracts.pipeline_lanes import PipelineLane
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.scanner import ScannerReportStore
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.storage import PinnedLocalRoot, RecordingStore, ScannerAnalysisStore, ScannerIqStore

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ProductionSettings:
    database_url: str = "postgresql+psycopg:///leo_tracker"
    bulk_root: Path = Path("/srv/bulk/leo")
    qualification_root: Path | None = None
    static_directory: Path = _PROJECT_ROOT / "web" / "dist"
    tle_root: Path = Path("/var/lib/leo/tle")
    host: str = "0.0.0.0"
    port: int = 8000
    pipeline_release_id: str | None = None
    scanner_report_root: Path | None = None

    @classmethod
    def from_environment(cls) -> ProductionSettings:
        port_text = os.environ.get("LEO_API_PORT", "8000")
        try:
            port = int(port_text)
        except ValueError as error:
            raise ValueError("LEO_API_PORT must be an integer") from error
        if not 1 <= port <= 65_535:
            raise ValueError("LEO_API_PORT must be between 1 and 65535")
        return cls(
            database_url=os.environ.get("LEO_DATABASE_URL", "postgresql+psycopg:///leo_tracker"),
            bulk_root=Path(os.environ.get("LEO_BULK_ROOT", "/srv/bulk/leo")),
            qualification_root=Path(
                os.environ.get("LEO_QUALIFICATION_ROOT", "/srv/bulk/leo/qualification")
            ),
            static_directory=Path(
                os.environ.get("LEO_WEB_DIST", str(_PROJECT_ROOT / "web" / "dist"))
            ),
            host="0.0.0.0",
            port=port,
            tle_root=Path(os.environ.get("LEO_TLE_ROOT", "/var/lib/leo/tle")),
            pipeline_release_id=os.environ.get("LEO_PIPELINE_RELEASE_ID"),
            scanner_report_root=(
                Path(value) if (value := os.environ.get("LEO_SCANNER_REPORT_ROOT")) else None
            ),
        )


def create_production_app(settings: ProductionSettings | None = None) -> FastAPI:
    configured = ProductionSettings.from_environment() if settings is None else settings
    qualification_root = configured.qualification_root or configured.bulk_root / "qualification"
    bulk_pin = PinnedLocalRoot(configured.bulk_root)
    scanner_iq = ScannerIqStore(configured.bulk_root)
    try:
        qualification_pin = PinnedLocalRoot(qualification_root)
    except Exception:
        bulk_pin.close()
        raise
    engine = create_catalog_engine(configured.database_url)
    catalog = CatalogRepository(create_session_factory(engine))
    recordings: RecordingStore | None = None
    artifacts: AnalysisArtifactStore | None = None
    campaigns: CatalogCampaignPresentation | None = None
    try:
        recordings = RecordingStore.open_pinned(bulk_pin)
        artifacts = AnalysisArtifactStore.open_pinned(bulk_pin)
        campaigns = CatalogCampaignPresentation(catalog, artifacts, qualification_pin)
    except Exception:
        for resource in (campaigns, artifacts, recordings):
            if resource is not None:
                with suppress(Exception):
                    resource.close()
        engine.dispose()
        raise
    finally:
        bulk_pin.close()
        qualification_pin.close()
    repository = CatalogPresentationRepository(
        catalog,
        recordings,
        artifacts,
        bulk_root=configured.bulk_root,
        campaigns=campaigns,
    )
    standard_v2_repository = CatalogStandardPresentationRepository(catalog, artifacts)
    standard_repository = DefinitionDispatchedStandardPresentationRepository(
        standard_v2_repository,
        CatalogStandardNativePresentationRepository(catalog, artifacts),
    )
    # Bound unconditionally.  The reader resolves availability per request, so
    # an API started before the hourly collector first creates its state
    # directory begins serving as soon as a snapshot appears, rather than
    # staying unavailable until the next restart.
    sky_service = SkyFieldService(TleArchiveReader(configured.tle_root))
    research_repository = CatalogStandardPresentationRepository(
        catalog,
        artifacts,
        pipeline_lane=PipelineLane.RESEARCH,
    )
    reprocess_processing: ProcessingService | None = None
    standard_reprocessor: StandardReprocessService | None = None
    research_reprocessor: ResearchReprocessService | None = None
    if configured.pipeline_release_id is not None:
        registry = production_standard_v2_registry()
        default_stage_keys = registry.keys
        native_registry = production_standard_native_evidence_registry()
        for stage_key in native_registry.keys:
            registry.register(native_registry.get(stage_key))
        research_configuration = production_research_v1_configuration()
        research_definition_id = research_pipeline_definition_id(
            pipeline_release_id=configured.pipeline_release_id,
            configuration=research_configuration,
        )
        research_registry = production_research_v1_registry(research_definition_id)
        reprocess_processing = ProcessingService(
            catalog=catalog,
            artifacts=artifacts,
            registry=registry,
            iq_readers=RecordingIqReaderProvider(recordings),
            default_stage_keys=default_stage_keys,
            lane_registries={PipelineLane.RESEARCH: research_registry},
        )
        standard_reprocessor = StandardReprocessService(
            catalog=catalog,
            recordings=recordings,
            processing=reprocess_processing,
            pipeline_release_id=configured.pipeline_release_id,
        )
        research_reprocessor = ResearchReprocessService(
            catalog=catalog,
            recordings=recordings,
            processing=reprocess_processing,
            pipeline_release_id=configured.pipeline_release_id,
        )
    try:
        app = create_app(
            repository,
            artifact_root=configured.bulk_root,
            static_directory=configured.static_directory,
            standard_repository=standard_repository,
            research_repository=research_repository,
            standard_reprocessor=standard_reprocessor,
            sky_service=sky_service,
            sky_archive_root=configured.tle_root,
            research_reprocessor=research_reprocessor,
            scanner_reports=ScannerReportStore(
                configured.scanner_report_root or configured.bulk_root / "scanner-reports"
            ),
            scanner_analyses=ScannerAnalysisStore(
                configured.bulk_root,
                capture_times=scanner_iq,
            ),
            capture_control=OperatorCaptureControl(
                # The global operation lock is sufficient for this control-only
                # adapter to observe an active dwell. Radio ownership remains
                # with the acquisition process and its fully configured authority.
                LocalCaptureAuthority(configured.bulk_root / "control", ())
            ),
        )
    except Exception:
        if reprocess_processing is not None:
            with suppress(Exception):
                reprocess_processing.close()
        for resource in (campaigns, artifacts, recordings):
            with suppress(Exception):
                resource.close()
        engine.dispose()
        raise

    def close_resources() -> None:
        errors: list[Exception] = []
        for callback in (
            *(() if reprocess_processing is None else (reprocess_processing.close,)),
            campaigns.close,
            artifacts.close,
            recordings.close,
            engine.dispose,
        ):
            try:
                callback()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("production API cleanup failed", errors)

    app.router.add_event_handler("shutdown", close_resources)
    app.state.catalog_engine = engine
    app.state.production_settings = configured
    return app


def main() -> None:
    if sys.argv[1:] == ["--check"]:
        settings = ProductionSettings.from_environment()
        print(
            f"leo-api entrypoint ok: host={settings.host} port={settings.port} "
            f"static={settings.static_directory}"
        )
        return
    settings = ProductionSettings.from_environment()
    uvicorn.run(
        create_production_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=True,
    )
