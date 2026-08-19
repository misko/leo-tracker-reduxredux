from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from leo.catalog import AttemptState, JobDefinition, JobState

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _seed(
    harness: CatalogHarness, *, session_id: str, run_id: str, jobs: list[JobDefinition]
) -> None:
    repository = harness.repository
    repository.create_capture_session(
        session_id=session_id,
        source_type="live",
        state="committed",
        bundle_uri=f"bulk://recordings/{session_id}",
        manifest_digest=DIGEST_A,
    )
    repository.add_pipeline_release(
        release_id="release-1",
        code_revision="code-1",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
    )
    repository.create_analysis_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id="release-1",
        input_manifest_digest=DIGEST_A,
        jobs=jobs,
    )


def test_eight_workers_claim_unique_jobs_with_skip_locked(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(
        catalog_harness,
        session_id="session-concurrent",
        run_id="run-concurrent",
        jobs=[JobDefinition(stage_key=f"stage-{index}") for index in range(8)],
    )
    barrier = Barrier(8)

    def claim(index: int) -> int:
        barrier.wait()
        lease = catalog_harness.repository.claim_job(
            worker_id=f"worker-{index}", lease_for=timedelta(minutes=5)
        )
        assert lease is not None
        return lease.job_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        job_ids = tuple(executor.map(claim, range(8)))

    assert len(set(job_ids)) == 8
    assert (
        catalog_harness.repository.claim_job(
            worker_id="ninth-worker", lease_for=timedelta(minutes=5)
        )
        is None
    )


def test_dependency_gating_waits_for_successful_predecessor(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(
        catalog_harness,
        session_id="session-dependency",
        run_id="run-dependency",
        jobs=[
            JobDefinition(stage_key="quality"),
            JobDefinition(stage_key="power", dependencies=("quality",)),
        ],
    )
    first = catalog_harness.repository.claim_job(
        worker_id="worker-quality", lease_for=timedelta(minutes=5)
    )

    assert first is not None
    assert first.stage_key == "quality"
    assert (
        catalog_harness.repository.claim_job(
            worker_id="worker-blocked", lease_for=timedelta(minutes=5)
        )
        is None
    )

    catalog_harness.repository.complete_job(
        job_id=first.job_id,
        worker_id=first.worker_id,
        outcome="complete",
    )
    second = catalog_harness.repository.claim_job(
        worker_id="worker-power", lease_for=timedelta(minutes=5)
    )
    assert second is not None
    assert second.stage_key == "power"


def test_expired_lease_is_recorded_and_reclaimed_for_next_attempt(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(
        catalog_harness,
        session_id="session-expiry",
        run_id="run-expiry",
        jobs=[JobDefinition(stage_key="quality", max_attempts=2)],
    )
    first = catalog_harness.repository.claim_job(
        worker_id="worker-old", lease_for=timedelta(minutes=5)
    )
    assert first is not None

    reclaimed = catalog_harness.repository.reclaim_expired_jobs(
        as_of=first.lease_expires_at + timedelta(seconds=1)
    )
    assert reclaimed == (first.job_id,)
    assert catalog_harness.repository.job_state(first.job_id) is JobState.PENDING
    assert catalog_harness.repository.attempt_states(first.job_id) == (AttemptState.EXPIRED,)

    second = catalog_harness.repository.claim_job(
        worker_id="worker-new", lease_for=timedelta(minutes=5)
    )
    assert second is not None
    assert second.job_id == first.job_id
    assert second.attempt_number == 2
    extended = catalog_harness.repository.heartbeat_job(
        job_id=second.job_id,
        worker_id=second.worker_id,
        lease_for=timedelta(minutes=10),
    )
    assert extended > second.lease_expires_at
    catalog_harness.repository.complete_job(
        job_id=second.job_id,
        worker_id=second.worker_id,
        outcome="complete",
    )
    assert catalog_harness.repository.attempt_states(second.job_id) == (
        AttemptState.EXPIRED,
        AttemptState.SUCCEEDED,
    )
