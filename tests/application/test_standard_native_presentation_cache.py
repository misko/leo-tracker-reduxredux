from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from leo.application.standard_native_presentation import (
    CatalogStandardNativePresentationRepository,
)


def test_verified_native_projection_is_reused_until_catalog_snapshot_changes(
    monkeypatch,
) -> None:
    first_snapshot = object()
    second_snapshot = object()
    catalog = Mock()
    catalog.presentation_snapshot.return_value = first_snapshot
    repository = CatalogStandardNativePresentationRepository(catalog, Mock())
    first_hierarchy = object()
    second_hierarchy = object()
    uncached = Mock(
        side_effect=(
            SimpleNamespace(snapshot=first_snapshot, hierarchy=first_hierarchy),
            SimpleNamespace(snapshot=second_snapshot, hierarchy=second_hierarchy),
        )
    )
    monkeypatch.setattr(repository, "_load_uncached", uncached)

    assert repository.subject_hierarchy("session") is first_hierarchy
    assert repository.subject_hierarchy("session") is first_hierarchy
    assert uncached.call_count == 1

    catalog.presentation_snapshot.return_value = second_snapshot
    assert repository.subject_hierarchy("session") is second_hierarchy
    assert uncached.call_count == 2
