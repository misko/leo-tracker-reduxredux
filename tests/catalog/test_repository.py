from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from leo.catalog import (
    ActiveRunExistsError,
    AnalysisRunState,
    AttemptState,
    CurrentSummary,
    InvalidStateError,
    JobDefinition,
    JobState,
    ProductConflictError,
    ProductRegistration,
    PromotionError,
    PromotionPolicy,
    SessionSearch,
)

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _seed_session(harness: CatalogHarness, *, session_id: str, source_type: str = "live") -> None:
    harness.repository.create_capture_session(
        session_id=session_id,
        source_type=source_type,
        state="committed",
        bundle_uri=f"bulk://recordings/{session_id}",
        manifest_digest=DIGEST_A,
        tags=("TEST",) if source_type == "test" else ("campaign-a",),
    )


def _seed_release(harness: CatalogHarness) -> None:
    harness.repository.add_pipeline_release(
        release_id="release-1",
        code_revision="code-1",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
    )


def _create_run(harness: CatalogHarness, *, session_id: str, run_id: str) -> None:
    harness.repository.create_analysis_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id="release-1",
        input_manifest_digest=DIGEST_A,
        jobs=[JobDefinition(stage_key="quality")],
    )


def _complete_run_job(harness: CatalogHarness, worker_id: str) -> None:
    lease = harness.repository.claim_job(
        worker_id=worker_id,
        lease_for=timedelta(minutes=5),
    )
    assert lease is not None
    harness.repository.complete_job(
        job_id=lease.job_id,
        worker_id=worker_id,
        outcome="complete",
    )


def test_product_registration_is_idempotent_but_rejects_conflict(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-product")
    _seed_release(catalog_harness)
    _create_run(catalog_harness, session_id="session-product", run_id="run-product")
    registration = ProductRegistration(
        run_id="run-product",
        stage_key="quality",
        kind="quality.summary",
        schema_version=1,
        role="scientific",
        status="complete",
        media_type="application/json",
        logical_uri="bulk://analysis/session-product/run-product/quality.json",
        digest=DIGEST_B,
        byte_size=123,
        coverage=1.0,
        summary={"clipped": 0},
    )

    first = catalog_harness.repository.register_product(registration)
    second = catalog_harness.repository.register_product(registration)
    assert first == second

    with pytest.raises(ProductConflictError, match="conflicts"):
        catalog_harness.repository.register_product(replace(registration, digest=DIGEST_C))


def test_one_active_run_and_failed_vs_successful_atomic_promotion(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-promotion")
    _seed_release(catalog_harness)
    _create_run(catalog_harness, session_id="session-promotion", run_id="run-good-1")
    with pytest.raises(ActiveRunExistsError, match="already has an active"):
        _create_run(catalog_harness, session_id="session-promotion", run_id="run-overlap")

    _complete_run_job(catalog_harness, "worker-1")
    catalog_harness.repository.seal_and_promote(
        run_id="run-good-1",
        manifest_uri="bulk://analysis/session-promotion/run-good-1/manifest.json",
        manifest_digest=DIGEST_B,
        summary=CurrentSummary(mean_power_dbfs=-10.0, candidate_count=1, coverage=1.0),
    )
    assert catalog_harness.repository.current_run_id("session-promotion") == "run-good-1"

    _create_run(catalog_harness, session_id="session-promotion", run_id="run-failed")
    failed_lease = catalog_harness.repository.claim_job(
        worker_id="worker-failed", lease_for=timedelta(minutes=5)
    )
    assert failed_lease is not None
    catalog_harness.repository.fail_job(
        job_id=failed_lease.job_id,
        worker_id=failed_lease.worker_id,
        error="injected analyzer failure",
        retryable=False,
    )
    with pytest.raises(PromotionError, match="unfinished or failed"):
        catalog_harness.repository.seal_and_promote(
            run_id="run-failed",
            manifest_uri="bulk://analysis/session-promotion/run-failed/manifest.json",
            manifest_digest=DIGEST_C,
            summary=CurrentSummary(candidate_count=99),
        )
    assert catalog_harness.repository.current_run_id("session-promotion") == "run-good-1"
    catalog_harness.repository.fail_analysis_run(
        run_id="run-failed", failure="injected analyzer failure"
    )
    assert catalog_harness.repository.run_state("run-failed") is AnalysisRunState.FAILED

    _create_run(catalog_harness, session_id="session-promotion", run_id="run-good-2")
    _complete_run_job(catalog_harness, "worker-2")
    catalog_harness.repository.seal_and_promote(
        run_id="run-good-2",
        manifest_uri="bulk://analysis/session-promotion/run-good-2/manifest.json",
        manifest_digest=DIGEST_C,
        summary=CurrentSummary(mean_power_dbfs=-9.0, candidate_count=2, coverage=0.9),
    )
    assert catalog_harness.repository.current_run_id("session-promotion") == "run-good-2"


def test_evidence_only_run_seals_products_without_replacing_current(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-evidence")
    _seed_release(catalog_harness)
    _create_run(catalog_harness, session_id="session-evidence", run_id="run-current")
    _complete_run_job(catalog_harness, "current-worker")
    catalog_harness.repository.seal_and_promote(
        run_id="run-current",
        manifest_uri="bulk://analysis/session-evidence/run-current/manifest.json",
        manifest_digest=DIGEST_B,
        summary=CurrentSummary(candidate_count=1),
    )

    catalog_harness.repository.create_analysis_run(
        run_id="run-evidence",
        session_id="session-evidence",
        pipeline_release_id="release-1",
        input_manifest_digest=DIGEST_A,
        jobs=(JobDefinition(stage_key="qualification"),),
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
    )
    lease = catalog_harness.repository.claim_job(
        worker_id="evidence-worker", lease_for=timedelta(minutes=5)
    )
    assert lease is not None and lease.run_id == "run-evidence"
    product_id = catalog_harness.repository.register_product(
        ProductRegistration(
            run_id="run-evidence",
            stage_key="qualification",
            kind="qualification.receipt",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri="bulk://analysis/session-evidence/run-evidence/receipt.json",
            digest=DIGEST_C,
            byte_size=321,
        )
    )
    catalog_harness.repository.complete_job(
        job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
    )
    catalog_harness.repository.seal_and_promote(
        run_id="run-evidence",
        manifest_uri="bulk://analysis/session-evidence/run-evidence/manifest.json",
        manifest_digest=DIGEST_C,
        summary=CurrentSummary(candidate_count=99),
    )

    evidence = catalog_harness.repository.run_seal_snapshot("run-evidence")
    assert evidence.execution.promotion_policy == PromotionPolicy.EVIDENCE_ONLY.value
    assert [product.product_id for product in evidence.products] == [product_id]
    assert catalog_harness.repository.run_state("run-evidence") is AnalysisRunState.SUCCEEDED
    assert catalog_harness.repository.current_run_id("session-evidence") == "run-current"


def test_invalid_promotion_policy_fails_before_run_creation(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-invalid-policy")
    _seed_release(catalog_harness)

    with pytest.raises(ValueError, match="unknown analysis-run promotion policy"):
        catalog_harness.repository.create_analysis_run(
            run_id="run-invalid-policy",
            session_id="session-invalid-policy",
            pipeline_release_id="release-1",
            input_manifest_digest=DIGEST_A,
            jobs=(JobDefinition(stage_key="quality"),),
            promotion_policy="publish_everything",
        )

    assert catalog_harness.repository.current_run_id("session-invalid-policy") is None


def test_cancel_run_preserves_completed_dependency_evidence_and_is_idempotent(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-cancel")
    _seed_release(catalog_harness)
    catalog_harness.repository.create_analysis_run(
        run_id="run-cancel",
        session_id="session-cancel",
        pipeline_release_id="release-1",
        input_manifest_digest=DIGEST_A,
        jobs=(
            JobDefinition(stage_key="quality"),
            JobDefinition(stage_key="power", dependencies=("quality",)),
        ),
    )
    lease = catalog_harness.repository.claim_job(
        worker_id="cancel-evidence-worker",
        lease_for=timedelta(minutes=5),
    )
    assert lease is not None and lease.stage_key == "quality"
    product_id = catalog_harness.repository.register_product(
        ProductRegistration(
            run_id="run-cancel",
            stage_key="quality",
            kind="quality.summary",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri="bulk://analysis/session-cancel/run-cancel/quality.json",
            digest=DIGEST_B,
            byte_size=123,
        )
    )
    catalog_harness.repository.complete_job(
        job_id=lease.job_id,
        worker_id=lease.worker_id,
        outcome="complete",
    )

    assert catalog_harness.repository.cancel_analysis_run(
        run_id="run-cancel",
        reason="operator stopped erroneous campaign",
    )
    assert not catalog_harness.repository.cancel_analysis_run(
        run_id="run-cancel",
        reason="operator stopped erroneous campaign",
    )
    snapshot = catalog_harness.repository.run_seal_snapshot("run-cancel")
    assert catalog_harness.repository.run_state("run-cancel") is AnalysisRunState.CANCELLED
    assert [job.state for job in snapshot.jobs] == [
        JobState.SUCCEEDED.value,
        JobState.CANCELLED.value,
    ]
    assert catalog_harness.repository.attempt_states(lease.job_id) == (AttemptState.SUCCEEDED,)
    assert [product.product_id for product in snapshot.products] == [product_id]


def test_cancel_run_refuses_a_live_worker_lease_without_stealing_it(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-live-lease")
    _seed_release(catalog_harness)
    _create_run(catalog_harness, session_id="session-live-lease", run_id="run-live-lease")
    lease = catalog_harness.repository.claim_job(
        worker_id="live-worker",
        lease_for=timedelta(minutes=5),
    )
    assert lease is not None

    with pytest.raises(InvalidStateError, match="live worker leases"):
        catalog_harness.repository.cancel_analysis_run(
            run_id="run-live-lease",
            reason="operator cancellation",
        )

    catalog_harness.repository.complete_job(
        job_id=lease.job_id,
        worker_id=lease.worker_id,
        outcome="complete",
    )
    assert catalog_harness.repository.job_state(lease.job_id) is JobState.SUCCEEDED


def test_cancel_run_cannot_replace_or_cancel_current_analysis(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-current-protected")
    _seed_release(catalog_harness)
    _create_run(
        catalog_harness,
        session_id="session-current-protected",
        run_id="run-current-protected",
    )
    _complete_run_job(catalog_harness, "current-worker")
    catalog_harness.repository.seal_and_promote(
        run_id="run-current-protected",
        manifest_uri=(
            "bulk://analysis/session-current-protected/run-current-protected/manifest.json"
        ),
        manifest_digest=DIGEST_B,
        summary=CurrentSummary(candidate_count=1),
    )

    with pytest.raises(InvalidStateError, match="current analysis"):
        catalog_harness.repository.cancel_analysis_run(
            run_id="run-current-protected",
            reason="must not replace current",
        )

    assert (
        catalog_harness.repository.current_run_id("session-current-protected")
        == "run-current-protected"
    )


def test_test_session_is_held_and_searchable_by_tag_and_hold(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_session(catalog_harness, session_id="session-test", source_type="test")
    _seed_session(catalog_harness, session_id="session-live")

    results = catalog_harness.repository.search_sessions(
        SessionSearch(source_type="test", tag="TEST", held=True)
    )
    assert len(results) == 1
    assert results[0].session_id == "session-test"
    assert results[0].held is True
    assert results[0].tags == ("TEST",)

    assert catalog_harness.repository.release_retention_hold(session_id="session-test") is True
    assert catalog_harness.repository.add_retention_hold(
        session_id="session-test", reason="permanent fixture", created_by="operator"
    )
