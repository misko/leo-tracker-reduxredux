from __future__ import annotations

from pathlib import Path

import pytest

from tests.postgres_support import UnsafeTestDatabaseError, require_safe_test_database_url


def test_database_authority_requires_an_explicit_test_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEO_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("LEO_DATABASE_URL", "postgresql+psycopg:///leo_tracker")

    with pytest.raises(UnsafeTestDatabaseError, match="no database connection was attempted"):
        require_safe_test_database_url()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg:///leo_tracker",
        "postgresql+psycopg:///postgres",
        "sqlite+pysqlite:///:memory:",
        "postgresql+psycopg:///research",
    ],
)
def test_database_authority_rejects_production_or_ambiguous_targets(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.setenv("LEO_TEST_DATABASE_URL", database_url)

    with pytest.raises(UnsafeTestDatabaseError):
        require_safe_test_database_url()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg:///leo_qualification",
        "postgresql+psycopg:///leo_component_test",
    ],
)
def test_database_authority_accepts_only_explicit_test_owned_targets(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.setenv("LEO_TEST_DATABASE_URL", database_url)

    assert require_safe_test_database_url() == database_url


def test_database_authority_uses_e2e_override_without_production_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEO_E2E_DATABASE_URL", "postgresql+psycopg:///browser_test")
    monkeypatch.setenv("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_qualification")

    assert require_safe_test_database_url(
        ("LEO_E2E_DATABASE_URL", "LEO_TEST_DATABASE_URL")
    ).endswith("/browser_test")


def test_database_fixture_modules_have_no_production_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture_paths = (
        "tests/catalog/conftest.py",
        "tests/processing/conftest.py",
        "tests/operations/conftest.py",
        "tests/integration/test_read_vertical.py",
        "tests/qualification/test_soak_acceptance_postgres.py",
        "tests/qualification/test_trusted_campaign_store.py",
        "tests/e2e/server.py",
    )

    for relative_path in fixture_paths:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "postgresql+psycopg:///leo_tracker" not in source, relative_path
        assert "require_safe_test_database_url" in source, relative_path
