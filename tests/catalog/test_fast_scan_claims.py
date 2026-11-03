from datetime import timedelta

import pytest

from leo.catalog import JobDefinition
from tests.catalog.test_jobs import _seed

pytestmark = pytest.mark.postgres


def test_run_restriction_preserves_other_pending_work(catalog_harness):
    repository = catalog_harness.repository
    for run in ("ordinary", "fast"):
        _seed(
            catalog_harness,
            session_id=f"session-{run}",
            run_id=run,
            jobs=[JobDefinition(stage_key=run)],
        )
    lease = repository.claim_job(
        worker_id="fast", lease_for=timedelta(minutes=1), run_ids=("fast",)
    )
    assert lease.run_id == "fast"
    assert (
        repository.claim_job(worker_id="fast", lease_for=timedelta(minutes=1), run_ids=("fast",))
        is None
    )
    ordinary = repository.claim_job(worker_id="ordinary", lease_for=timedelta(minutes=1))
    assert ordinary.run_id == "ordinary"
    with pytest.raises(ValueError, match="non-empty and unique"):
        repository.claim_job(worker_id="bad", lease_for=timedelta(minutes=1), run_ids=())


def test_supported_stage_filter_leaves_new_stages_for_capable_workers(catalog_harness):
    repository = catalog_harness.repository
    _seed(
        catalog_harness,
        session_id="mixed",
        run_id="mixed",
        jobs=[JobDefinition(stage_key="fast-scan", priority=100), JobDefinition(stage_key="power")],
    )
    ordinary = repository.claim_job(
        worker_id="ordinary", lease_for=timedelta(minutes=1), stage_keys=("power",)
    )
    assert ordinary.stage_key == "power"
    assert (
        repository.claim_job(worker_id="empty", lease_for=timedelta(minutes=1), stage_keys=())
        is None
    )
    fast = repository.claim_job(
        worker_id="fast",
        lease_for=timedelta(minutes=1),
        run_ids=("mixed",),
        stage_keys=("fast-scan",),
    )
    assert fast.stage_key == "fast-scan"
