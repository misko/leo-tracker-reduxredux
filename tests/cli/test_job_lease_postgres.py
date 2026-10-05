"""Real catalog ownership, renewal, and recovery in an isolated test schema."""

import sys
from datetime import UTC, datetime, timedelta

import pytest

from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.catalog.errors import LeaseLostError
from leo.cli.job_lease import LeaseSupervisor, run_process
from tests.postgres_support import isolated_test_schema_url


@pytest.mark.postgres
def test_real_renewal_recovery_and_stale_owner_fencing():
    with isolated_test_schema_url(prefix="lease_repair") as url:
        engine = create_catalog_engine(url)
        catalog = CatalogRepository(create_session_factory(engine))
        try:
            catalog.enqueue_adaptive_analysis_job(
                session_id="scan-fw-0123456789abcdef",
                input_manifest_digest="sha256:" + "1" * 64,
                configuration_digest="sha256:" + "2" * 64,
            )
            lease = catalog.claim_adaptive_job(
                worker_id="first-process", lease_for=timedelta(seconds=1)
            )
            assert lease is not None
            with LeaseSupervisor(
                catalog, lease, lease_for=timedelta(seconds=1), interval=0.1
            ) as guard:
                run_process(
                    [sys.executable, "-c", "import time; time.sleep(1.3)"],
                    supervisor=guard,
                    poll_seconds=0.03,
                )
                assert catalog.reclaim_expired_jobs(adaptive_only=True) == ()
                guard.complete_job(
                    job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
                )
            catalog.enqueue_adaptive_analysis_job(
                session_id="scan-fw-fedcba9876543210",
                input_manifest_digest="sha256:" + "3" * 64,
                configuration_digest="sha256:" + "4" * 64,
            )
            old = catalog.claim_adaptive_job(
                worker_id="dead-process", lease_for=timedelta(seconds=1)
            )
            assert catalog.reclaim_expired_jobs(
                adaptive_only=True, as_of=datetime.now(UTC) + timedelta(seconds=2)
            ) == (old.job_id,)
            new = catalog.claim_adaptive_job(
                worker_id="replacement-process", lease_for=timedelta(seconds=20)
            )
            assert new.job_id == old.job_id
            assert new.attempt_number == old.attempt_number + 1
            with pytest.raises(LeaseLostError):
                catalog.heartbeat_job(
                    job_id=old.job_id, worker_id=old.worker_id, lease_for=timedelta(seconds=20)
                )
            catalog.complete_job(
                job_id=new.job_id, worker_id=new.worker_id, outcome="already_complete"
            )
        finally:
            engine.dispose()
