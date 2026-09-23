from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def test_tracking_jobs_use_memory_capacity_and_keep_their_immutable_binding(
    catalog_harness,
) -> None:
    repository = catalog_harness.repository
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE processing_resource_capacity SET maximum_leases = 2 "
                "WHERE resource_class = 'memory'"
            )
        )
    for index in range(3):
        assert repository.enqueue_adaptive_tracking_job(
            session_id=f"scan-fw-tracking-{index}",
            input_manifest_digest=_digest(str(index + 1)),
            configuration_digest=_digest(str(index + 4)),
        )

    first = repository.claim_adaptive_job(
        worker_id="adaptive-tracking-1", lease_for=timedelta(minutes=20)
    )
    second = repository.claim_adaptive_job(
        worker_id="adaptive-tracking-2", lease_for=timedelta(minutes=20)
    )
    third = repository.claim_adaptive_job(
        worker_id="adaptive-tracking-3", lease_for=timedelta(minutes=20)
    )

    assert first is not None
    assert second is not None
    assert first.job_kind == second.job_kind == "adaptive_tracking"
    assert first.resource_class == second.resource_class == "memory"
    assert first.input_manifest_digest == _digest("1")
    assert first.configuration_digest == _digest("4")
    assert third is None


def test_tracking_enqueue_is_idempotent_for_the_same_policy_binding(catalog_harness) -> None:
    repository = catalog_harness.repository
    arguments = {
        "session_id": "scan-fw-tracking-idempotent",
        "input_manifest_digest": _digest("a"),
        "configuration_digest": _digest("b"),
    }

    assert repository.enqueue_adaptive_tracking_job(**arguments)
    assert not repository.enqueue_adaptive_tracking_job(**arguments)
