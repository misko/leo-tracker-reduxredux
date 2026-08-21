from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from leo.catalog import CatalogRepository, create_session_factory
from tests.postgres_support import require_safe_test_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class CatalogHarness:
    repository: CatalogRepository
    engine: Engine
    schema: str
    alembic_config: Config


def _base_url() -> str:
    return require_safe_test_database_url()


def _schema_url(base_url: str, schema: str) -> str:
    url = make_url(base_url)
    options = f"-csearch_path={schema}"
    return url.update_query_dict({"options": options}).render_as_string(hide_password=False)


def _alembic_config(connection: object | None = None) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@pytest.fixture
def catalog_harness() -> Iterator[CatalogHarness]:
    base_url = _base_url()
    schema = f"leo_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(base_url, pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(CreateSchema(schema))
    except Exception as error:
        admin_engine.dispose()
        pytest.fail(
            f"real PostgreSQL test database is required at {base_url!r}: {error}",
            pytrace=False,
        )

    engine = create_engine(_schema_url(base_url, schema), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            config = _alembic_config(connection)
            command.upgrade(config, "head")
        yield CatalogHarness(
            repository=CatalogRepository(create_session_factory(engine)),
            engine=engine,
            schema=schema,
            alembic_config=_alembic_config(),
        )
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin_engine.dispose()
