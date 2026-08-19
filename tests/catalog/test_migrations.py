from __future__ import annotations

from alembic import command
from sqlalchemy import inspect

from leo.catalog.models import Base

from .conftest import CatalogHarness


def test_empty_schema_upgrades_to_single_head_without_model_drift(
    catalog_harness: CatalogHarness,
) -> None:
    inspector = inspect(catalog_harness.engine)

    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.check(catalog_harness.alembic_config)
