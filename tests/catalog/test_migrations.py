from __future__ import annotations

from alembic import command
from sqlalchemy import inspect, text

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


def test_previous_head_upgrades_without_changing_existing_catalog_rows(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "a8d4c2e91b70")
        connection.execute(
            text(
                "INSERT INTO pipeline_release "
                "(id, code_revision, environment_digest, graph_digest) "
                "VALUES ('pre-campaign', 'code', :digest, :digest)"
            ),
            {"digest": "sha256:" + "a" * 64},
        )
        command.upgrade(catalog_harness.alembic_config, "head")
        assert (
            connection.execute(
                text("SELECT code_revision FROM pipeline_release WHERE id = 'pre-campaign'")
            ).scalar_one()
            == "code"
        )
        command.check(catalog_harness.alembic_config)
