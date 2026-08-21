from __future__ import annotations

import pytest

_POSTGRES_FIXTURES = frozenset(
    {
        "catalog_harness",
        "isolated_catalog_url",
        "operations_database",
        "processing_database",
        "read_system",
        "standard_database",
        "trusted_processing_database",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every consumer of a shared real-PostgreSQL fixture.

    Marker assignment is derived from pytest's resolved fixture closure, so an
    indirect consumer cannot accidentally enter the portable test shard.
    """

    marker = pytest.mark.postgres
    for item in items:
        fixture_names = frozenset(getattr(item, "fixturenames", ()))
        if _POSTGRES_FIXTURES.intersection(fixture_names):
            item.add_marker(marker)
