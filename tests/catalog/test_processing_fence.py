from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest

from leo.catalog import (
    AnalysisRunState,
    CatalogNotFoundError,
    InvalidStateError,
    JobDefinition,
    JobState,
    LeaseLostError,
    ProductRegistration,
    WorkerReleaseAuthority,
)
from leo.contracts.digests import canonical_digest

from .conftest import CatalogHarness

RELEASE = "a" * 40
OTHER_RELEASE = "b" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _authority(release: str = RELEASE) -> WorkerReleaseAuthority:
    return WorkerReleaseAuthority(
        pipeline_release_id=release,
        code_revision=release,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration_digest=canonical_digest({}),
        executable_digest=DIGEST_A,
    )


def _seed(
    harness: CatalogHarness,
    *,
    release: str = RELEASE,
    session_id: str = "session-fence",
    run_id: str = "run-fence",
    stages: tuple[str, ...] = ("one", "two"),
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
        release_id=release,
        code_revision=release,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
    )
    repository.create_analysis_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id=release,
        input_manifest_digest=DIGEST_A,
        jobs=tuple(JobDefinition(stage_key=stage) for stage in stages),
    )


def _fence(harness: CatalogHarness, **overrides):
    values = {
        "operation_id": "cutover-1",
        "pipeline_release_id": RELEASE,
        "operator_id": "deployment",
        "reason": "replace old deployment",
        "expected_run_ids": ("run-fence",),
    }
    values.update(overrides)
    return harness.repository.stop_and_fence_release(**values)


def test_fence_revokes_late_publish_and_complete_and_is_idempotent(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(catalog_harness)
    lease = catalog_harness.repository.claim_job(
        worker_id="old-worker", lease_for=timedelta(minutes=5), authority=_authority()
    )
    assert lease is not None

    first = _fence(catalog_harness)
    replay = _fence(catalog_harness)

    assert first.changed is True
    assert first.cancelled_run_count == 1
    assert first.cancelled_job_count == 2
    assert first.expired_attempt_count == 1
    assert replay == replace(first, changed=False)
    with pytest.raises(LeaseLostError):
        catalog_harness.repository.complete_job(
            job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
        )
    with pytest.raises(LeaseLostError):
        catalog_harness.repository.register_product(
            ProductRegistration(
                run_id=lease.run_id,
                stage_key=lease.stage_key,
                kind="late.product",
                schema_version=1,
                role="scientific",
                status="complete",
                media_type="application/json",
                logical_uri="bulk://late.json",
                digest=DIGEST_B,
                byte_size=2,
            )
        )


def test_fence_preserves_succeeded_jobs_and_products(catalog_harness: CatalogHarness) -> None:
    _seed(catalog_harness)
    lease = catalog_harness.repository.claim_job(
        worker_id="worker", lease_for=timedelta(minutes=5), authority=_authority()
    )
    assert lease is not None
    product_id = catalog_harness.repository.register_product(
        ProductRegistration(
            run_id=lease.run_id,
            stage_key=lease.stage_key,
            kind="kept.product",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri="bulk://kept.json",
            digest=DIGEST_B,
            byte_size=2,
        )
    )
    catalog_harness.repository.complete_job(
        job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
    )

    result = _fence(catalog_harness)
    snapshot = catalog_harness.repository.run_seal_snapshot("run-fence")

    assert result.preserved_succeeded_job_count == 1
    assert result.preserved_product_count == 1
    assert [product.product_id for product in snapshot.products] == [product_id]
    assert [job.state for job in snapshot.jobs] == ["succeeded", "cancelled"]


def test_exact_release_selection_fences_multiple_runs_only(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(catalog_harness, session_id="session-a", run_id="run-a")
    _seed(catalog_harness, session_id="session-b", run_id="run-b")
    _seed(
        catalog_harness,
        release=OTHER_RELEASE,
        session_id="session-other",
        run_id="run-other",
    )

    result = _fence(
        catalog_harness,
        expected_run_ids=("run-a", "run-b"),
    )

    assert result.run_ids == ("run-a", "run-b")
    assert catalog_harness.repository.run_state("run-a") is AnalysisRunState.CANCELLED
    assert catalog_harness.repository.run_state("run-b") is AnalysisRunState.CANCELLED
    assert catalog_harness.repository.run_state("run-other") is AnalysisRunState.PENDING


def test_inventory_mismatch_rolls_back_entire_postgres_transaction(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(catalog_harness)

    with pytest.raises(InvalidStateError, match="inventory differs"):
        _fence(catalog_harness, expected_run_ids=("wrong-run",))

    assert catalog_harness.repository.run_state("run-fence") is AnalysisRunState.PENDING
    assert all(
        job.state == JobState.PENDING.value
        for job in catalog_harness.repository.run_seal_snapshot("run-fence").jobs
    )
    with pytest.raises(CatalogNotFoundError):
        _fence(catalog_harness, pipeline_release_id="c" * 40)


def test_claim_racing_fence_cannot_escape_release_authority(
    catalog_harness: CatalogHarness,
) -> None:
    _seed(catalog_harness, stages=("only",))
    barrier = Barrier(2)

    def claim():
        barrier.wait()
        return catalog_harness.repository.claim_job(
            worker_id="racing-worker",
            lease_for=timedelta(minutes=5),
            authority=_authority(),
        )

    def fence():
        barrier.wait()
        return _fence(catalog_harness)

    with ThreadPoolExecutor(max_workers=2) as executor:
        lease_future = executor.submit(claim)
        fence_future = executor.submit(fence)
        lease = lease_future.result()
        result = fence_future.result()

    assert result.cancelled_job_count == 1
    assert catalog_harness.repository.run_state("run-fence") is AnalysisRunState.CANCELLED
    assert catalog_harness.repository.run_seal_snapshot("run-fence").jobs[0].state == "cancelled"
    if lease is not None:
        with pytest.raises(LeaseLostError):
            catalog_harness.repository.complete_job(
                job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
            )
