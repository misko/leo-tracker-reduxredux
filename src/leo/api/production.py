"""Production composition for the open, read-only LAN API and compiled UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from leo.api.app import create_app
from leo.application import CatalogPresentationRepository
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.storage import RecordingStore

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ProductionSettings:
    database_url: str = "postgresql+psycopg:///leo_tracker"
    bulk_root: Path = Path("/srv/bulk/leo")
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
            static_directory=Path(
                os.environ.get("LEO_WEB_DIST", str(_PROJECT_ROOT / "web" / "dist"))
            ),
            host="0.0.0.0",
            port=port,
        )


def create_production_app(settings: ProductionSettings | None = None) -> FastAPI:
    configured = ProductionSettings.from_environment() if settings is None else settings
    configured.bulk_root.mkdir(parents=True, exist_ok=True)
    engine = create_catalog_engine(configured.database_url)
    catalog = CatalogRepository(create_session_factory(engine))
    recordings = RecordingStore(configured.bulk_root)
    artifacts = AnalysisArtifactStore(configured.bulk_root)
    repository = CatalogPresentationRepository(
        catalog,
        recordings,
        artifacts,
        bulk_root=configured.bulk_root,
    )
    try:
        app = create_app(
            repository,
            artifact_root=configured.bulk_root,
            static_directory=configured.static_directory,
        )
    except Exception:
        engine.dispose()
        raise
    app.router.add_event_handler("shutdown", engine.dispose)
    app.state.catalog_engine = engine
    app.state.production_settings = configured
    return app


def main() -> None:
    settings = ProductionSettings.from_environment()
    uvicorn.run(
        create_production_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=True,
    )
