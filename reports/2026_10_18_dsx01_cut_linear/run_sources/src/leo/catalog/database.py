"""Engine and session-factory construction for PostgreSQL."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_catalog_engine(database_url: str, *, pool_pre_ping: bool = True) -> Engine:
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not database_url.startswith("postgresql+psycopg://"):
        raise ValueError("the catalog requires a PostgreSQL psycopg URL")
    return create_engine(database_url, pool_pre_ping=pool_pre_ping)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
