from __future__ import annotations

import os
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class OperationsDatabase:
    catalog: CatalogRepository
    engine: Engine


@pytest.fixture
def operations_database() -> Iterator[OperationsDatabase]:
    base_url = os.environ.get("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker")
    schema = f"leo_operations_{uuid.uuid4().hex}"
    admin = create_engine(base_url, pool_pre_ping=True)
    try:
        with admin.begin() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(CreateSchema(schema))
    except Exception as error:
        admin.dispose()
        pytest.fail(
            f"real PostgreSQL test database is required at {base_url!r}: {error}",
            pytrace=False,
        )
    url = make_url(base_url).update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(url, pool_pre_ping=True)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield OperationsDatabase(
            catalog=CatalogRepository(create_session_factory(engine)), engine=engine
        )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()
