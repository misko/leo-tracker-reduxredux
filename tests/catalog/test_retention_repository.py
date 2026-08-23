from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from leo.catalog import (
    CurrentSummary,
    InvalidStateError,
    JobDefinition,
    LeaseLostError,
    ProductRegistration,
)

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _session(harness: CatalogHarness, session_id: str, *, source_type: str = "live") -> None:
    harness.repository.create_capture_session(
        session_id=session_id,
        source_type=source_type,
        state="committed",
        bundle_uri=f"bulk://recordings/2026/08/19/{session_id}",
        manifest_digest=DIGEST_A,
        allocated_bytes=100,
        tags=("TEST",) if source_type == "test" else (),
    )


def _release(harness: CatalogHarness, release_id: str = "retention-release") -> None:
    harness.repository.add_pipeline_release(
        release_id=release_id,
        code_revision=f"code-{release_id}",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
    )


def _run_and_promote(
    harness: CatalogHarness,
    session_id: str,
    run_id: str,
    *,
    release_id: str = "retention-release",
) -> int:
    harness.repository.create_analysis_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id=release_id,
        input_manifest_digest=DIGEST_A,
        jobs=(JobDefinition(stage_key="quality"),),
    )
    lease = harness.repository.claim_job(
        worker_id=f"worker-{run_id}", lease_for=timedelta(minutes=1)
    )
    assert lease is not None
    product_id = harness.repository.register_product(
        ProductRegistration(
            run_id=run_id,
            stage_key="quality",
            kind="quality",
            schema_version=1,
            role="presentation",
            status="complete",
            media_type="application/json",
            logical_uri=f"bulk://analysis/{session_id}/{run_id}/quality.json",
            digest=DIGEST_B,
            byte_size=25,
        )
    )
    harness.repository.complete_job(
        job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
    )
    harness.repository.seal_and_promote(
        run_id=run_id,
        manifest_uri=f"bulk://analysis/{session_id}/{run_id}/manifest.json",
        manifest_digest=DIGEST_B,
        summary=CurrentSummary(),
    )
    return product_id


def test_candidates_exclude_holds_test_active_work_and_current_product(
    catalog_harness: CatalogHarness,
) -> None:
    _release(catalog_harness)
    _session(catalog_harness, "old")
    _session(catalog_harness, "held")
    _session(catalog_harness, "test", source_type="test")
    _session(catalog_harness, "active")
    _session(catalog_harness, "unanalysed")
    catalog_harness.repository.add_retention_hold(
        session_id="held", reason="keep", created_by="test"
    )
    current_product = _run_and_promote(catalog_harness, "old", "old-run-1")
    _release(catalog_harness, "retention-release-v2")
    superseded_product = _run_and_promote(
        catalog_harness,
        "old",
        "old-run-2",
        release_id="retention-release-v2",
    )
    catalog_harness.repository.create_analysis_run(
        run_id="active-run",
        session_id="active",
        pipeline_release_id="retention-release",
        input_manifest_digest=DIGEST_A,
        jobs=(JobDefinition(stage_key="quality"),),
    )

    candidates = catalog_harness.repository.retention_candidates()
    identities = {(item.kind, item.item_id) for item in candidates}
    assert ("session", "old") in identities
    assert ("session", "held") not in identities
    assert ("session", "test") not in identities
    assert ("session", "active") not in identities
    assert ("session", "unanalysed") not in identities
    assert (
        catalog_harness.repository.claim_session_for_purge(
            session_id="unanalysed",
            claim_token="claim-unanalysed",
            lease_for=timedelta(minutes=1),
        )
        is None
    )
    assert ("artifact", str(current_product)) in identities
    assert ("artifact", str(superseded_product)) not in identities


def test_session_purge_fence_preserves_tombstone_and_hold_wins(
    catalog_harness: CatalogHarness,
) -> None:
    _release(catalog_harness)
    _session(catalog_harness, "purge-me")
    _run_and_promote(catalog_harness, "purge-me", "purge-run")
    claim = catalog_harness.repository.claim_session_for_purge(
        session_id="purge-me", claim_token="claim-a", lease_for=timedelta(minutes=1)
    )
    assert claim is not None
    with pytest.raises(InvalidStateError, match="hold won"):
        catalog_harness.repository.commit_session_purge(
            session_id="purge-me",
            claim_token="claim-a",
            staged_bytes=100,
            recording_manifest={"session_id": "purge-me"},
            recording_root="/srv/bulk/recordings/2026/08/19/purge-me",
            durable_hold_present=lambda _session_id: True,
        )
    assert catalog_harness.repository.release_session_purge_claim(
        session_id="purge-me", claim_token="claim-a"
    )

    claim = catalog_harness.repository.claim_session_for_purge(
        session_id="purge-me", claim_token="claim-b", lease_for=timedelta(minutes=1)
    )
    assert claim is not None
    catalog_harness.repository.commit_session_purge(
        session_id="purge-me",
        claim_token="claim-b",
        staged_bytes=100,
        recording_manifest={"session_id": "purge-me"},
        recording_root="/srv/bulk/recordings/2026/08/19/purge-me",
        durable_hold_present=lambda _session_id: False,
    )
    with catalog_harness.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT state, raw_available, bundle_uri, attributes "
                "FROM capture_session WHERE id = 'purge-me'"
            )
        ).one()
        event = connection.execute(
            text("SELECT event_type FROM retention_event WHERE session_id = 'purge-me'")
        ).scalar_one()
    assert row.state == "purged"
    assert row.raw_available is False
    assert row.bundle_uri.endswith("/purge-me")
    assert row.attributes["recording_manifest"]["session_id"] == "purge-me"
    assert event == "purge_staged"


def test_product_purge_is_fenced_and_marks_availability(
    catalog_harness: CatalogHarness,
) -> None:
    _release(catalog_harness)
    _session(catalog_harness, "products")
    old_product = _run_and_promote(catalog_harness, "products", "products-run-1")
    _release(catalog_harness, "retention-release-v2")
    _run_and_promote(
        catalog_harness,
        "products",
        "products-run-2",
        release_id="retention-release-v2",
    )
    claim = catalog_harness.repository.claim_product_for_purge(
        product_id=old_product,
        claim_token="artifact-claim",
        lease_for=timedelta(minutes=1),
    )
    assert claim is not None
    catalog_harness.repository.commit_product_purge(
        product_id=old_product, claim_token="artifact-claim", staged_bytes=25
    )
    assert (
        catalog_harness.repository.purge_disposition(
            kind="artifact", item_id=str(old_product), claim_token="artifact-claim"
        )
        == "discard"
    )
    with pytest.raises(LeaseLostError):
        catalog_harness.repository.commit_product_purge(
            product_id=old_product, claim_token="artifact-claim", staged_bytes=25
        )
