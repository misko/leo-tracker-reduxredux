"""Production composition for the open, read-only LAN API and compiled UI."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from leo.api.app import create_app
from leo.application import CatalogPresentationRepository, CatalogStandardPresentationRepository
from leo.application.campaign_presentation import CatalogCampaignPresentation
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.storage import PinnedLocalRoot, RecordingStore

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ProductionSettings:
    database_url: str = "postgresql+psycopg:///leo_tracker"
    bulk_root: Path = Path("/srv/bulk/leo")
    qualification_root: Path | None = None
    static_directory: Path = _PROJECT_ROOT / "web" / "dist"
    host: str = "0.0.0.0"
    port: int = 8000

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
        )


def create_production_app(settings: ProductionSettings | None = None) -> FastAPI:
    configured = ProductionSettings.from_environment() if settings is None else settings
    qualification_root = configured.qualification_root or configured.bulk_root / "qualification"
    bulk_pin = PinnedLocalRoot(configured.bulk_root)
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
    standard_repository = CatalogStandardPresentationRepository(catalog, artifacts)
    try:
        app = create_app(
            repository,
            artifact_root=configured.bulk_root,
            static_directory=configured.static_directory,
            standard_repository=standard_repository,
        )
    except Exception:
        for resource in (campaigns, artifacts, recordings):
            with suppress(Exception):
                resource.close()
        engine.dispose()
        raise

    def close_resources() -> None:
        errors: list[Exception] = []
        for callback in (
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
