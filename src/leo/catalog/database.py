"""Engine and session-factory construction for PostgreSQL."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_catalog_engine(
    database_url: str,
    *,
    pool_pre_ping: bool = True,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> Engine:
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not database_url.startswith("postgresql+psycopg://"):
        raise ValueError("the catalog requires a PostgreSQL psycopg URL")
    if pool_size is not None and pool_size < 1:
        raise ValueError("catalog engine pool_size must be positive")
    if max_overflow is not None and max_overflow < 0:
        raise ValueError("catalog engine max_overflow cannot be negative")
    options: dict[str, object] = {"pool_pre_ping": pool_pre_ping}
    if pool_size is not None:
        options["pool_size"] = pool_size
    if max_overflow is not None:
        options["max_overflow"] = max_overflow
    return create_engine(database_url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
