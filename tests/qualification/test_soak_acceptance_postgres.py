from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from leo.qualification.soak_acceptance import PostgresSoakCohortReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _schema_url(base_url: str, schema: str) -> str:
    url = make_url(base_url)
    return url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
        hide_password=False
    )


@pytest.fixture
def isolated_catalog_url() -> Iterator[str]:
    base_url = os.environ.get("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker")
    schema = f"leo_soak_audit_{uuid.uuid4().hex}"
    admin_engine = create_engine(base_url, pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
    except Exception as error:
        admin_engine.dispose()
        pytest.fail(
            f"real PostgreSQL test database is required at {base_url!r}: {error}",
            pytrace=False,
        )

    schema_url = _schema_url(base_url, schema)
    engine = create_engine(schema_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            config = Config(str(PROJECT_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield schema_url
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.mark.postgres
def test_postgres_reader_uses_expected_cohort_and_inherited_boundary(
    isolated_catalog_url: str,
) -> None:
    engine = create_engine(isolated_catalog_url)
    cutoff = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    before = cutoff - timedelta(seconds=1)
    after = cutoff + timedelta(seconds=1)
    digest = "sha256:" + "0" * 64
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO pipeline_release
                    (id, code_revision, environment_digest, graph_digest,
                     configuration_digest, executable_digest, authority_version, configuration)
                VALUES ('standard-v1', 'test', :digest, :digest,
                        :digest, :digest, 0, '{}')
                """
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                """
                INSERT INTO capture_session
                    (id, source_type, state, allocated_bytes, raw_available)
                VALUES
                    ('expected-session', 'test', 'committed', 0, true),
                    ('inherited-session', 'test', 'committed', 0, true)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO analysis_run
                    (id, session_id, pipeline_release_id, trigger, state,
                     input_manifest_digest, created_at, started_at, sealed_at)
                VALUES
                    ('expected-run', 'expected-session', 'standard-v1', 'automatic',
                     'succeeded', :digest, :after, :after, :after),
                    ('inherited-run', 'inherited-session', 'standard-v1', 'automatic',
                     'running', :digest, :before, :before, NULL)
                """
            ),
            {"digest": digest, "before": before, "after": after},
        )
        connection.execute(
            text(
                """
                INSERT INTO processing_job
                    (run_id, stage_key, scope_key, priority, state, attempt_count, max_attempts,
                     available_at, created_at, updated_at)
                VALUES
                    ('expected-run', 'raw-validate', 'stream-0', 0, 'succeeded', 1, 3,
                     :after, :after, :after),
                    ('inherited-run', 'raw-validate', 'stream-0', 0, 'pending', 0, 3,
                     :before, :before, :before)
                """
            ),
            {"before": before, "after": after},
        )
    engine.dispose()

    result = PostgresSoakCohortReader(isolated_catalog_url).read(
        expected_runs=(("expected-run", "expected-session"),),
        soak_created_utc_ns=int(cutoff.timestamp() * 1_000_000_000),
    )

    assert result.inherited_pending_or_leased == 1
    assert result.transaction_read_only is True
    assert result.transaction_isolation == "repeatable read"
    assert [(run.run_id, run.state, run.pipeline_release_id) for run in result.found_runs] == [
        ("expected-run", "succeeded", "standard-v1")
    ]
    assert [(job.run_id, job.stage_key, job.scope_key) for job in result.jobs] == [
        ("expected-run", "raw-validate", "stream-0")
    ]
