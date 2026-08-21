from __future__ import annotations

import os
from collections.abc import Iterable

from sqlalchemy.engine import URL, make_url

_PRODUCTION_DATABASE_NAMES = frozenset(
    {
        "leo_tracker",
        "postgres",
        "template0",
        "template1",
    }
)


class UnsafeTestDatabaseError(RuntimeError):
    """The configured database is absent or is not explicitly test-owned."""


def require_safe_test_database_url(
    environment_names: Iterable[str] = ("LEO_TEST_DATABASE_URL",),
) -> str:
    """Return an explicitly configured, unmistakably non-production PostgreSQL URL.

    Tests must never inherit the application's ``LEO_DATABASE_URL`` and must never
    guess a local database name.  Qualification and E2E callers may provide their
    own dedicated variable first, followed by ``LEO_TEST_DATABASE_URL``.
    """

    names = tuple(environment_names)
    configured_name = next((name for name in names if os.environ.get(name)), None)
    if configured_name is None:
        joined = " or ".join(names)
        raise UnsafeTestDatabaseError(
            f"PostgreSQL tests require explicit {joined}; no database connection was attempted"
        )
    raw_url = os.environ[configured_name]
    try:
        url = make_url(raw_url)
    except Exception as error:
        raise UnsafeTestDatabaseError(
            f"{configured_name} is not a valid SQLAlchemy database URL"
        ) from error
    _validate_test_database_url(url, configured_name=configured_name)
    return url.render_as_string(hide_password=False)


def _validate_test_database_url(url: URL, *, configured_name: str) -> None:
    if not url.drivername.startswith("postgresql"):
        raise UnsafeTestDatabaseError(
            f"{configured_name} must select PostgreSQL, not {url.drivername!r}"
        )
    database = (url.database or "").strip().casefold()
    if not database:
        raise UnsafeTestDatabaseError(f"{configured_name} must name a dedicated test database")
    if database in _PRODUCTION_DATABASE_NAMES:
        raise UnsafeTestDatabaseError(
            f"{configured_name} refuses protected database {database!r}; "
            "no connection was attempted"
        )
    if "qualification" not in database and not database.endswith("_test"):
        raise UnsafeTestDatabaseError(
            f"{configured_name} database {database!r} must contain 'qualification' "
            "or end in '_test'"
        )
