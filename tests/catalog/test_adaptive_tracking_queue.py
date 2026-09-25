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


def test_adaptive_job_inventory_groups_kinds_by_immutable_session(catalog_harness) -> None:
    repository = catalog_harness.repository
    assert repository.enqueue_adaptive_analysis_job(
        session_id="scan-fw-inventory",
        input_manifest_digest=_digest("1"),
        configuration_digest=_digest("2"),
    )
    assert repository.enqueue_adaptive_tracking_job(
        session_id="scan-fw-inventory",
        input_manifest_digest=_digest("1"),
        configuration_digest=_digest("3"),
    )
    assert repository.enqueue_adaptive_analysis_job(
        session_id="scan-fw-analysis-only",
        input_manifest_digest=_digest("4"),
        configuration_digest=_digest("5"),
    )

    assert repository.adaptive_job_kinds_by_session() == {
        "scan-fw-analysis-only": frozenset(("adaptive_scan",)),
        "scan-fw-inventory": frozenset(("adaptive_scan", "adaptive_tracking")),
    }


def test_new_tracking_policy_atomically_cancels_pending_old_policy(catalog_harness) -> None:
    repository = catalog_harness.repository
    common = {
        "session_id": "scan-fw-tracking-superseded",
        "input_manifest_digest": _digest("c"),
    }
    assert repository.enqueue_adaptive_tracking_job(**common, configuration_digest=_digest("d"))
    assert repository.enqueue_adaptive_tracking_job(**common, configuration_digest=_digest("e"))
    assert not repository.enqueue_adaptive_tracking_job(**common, configuration_digest=_digest("d"))
    with catalog_harness.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT adaptive_configuration_digest, state, outcome "
                "FROM processing_job WHERE adaptive_session_id = :session ORDER BY id"
            ),
            {"session": common["session_id"]},
        ).all()
    assert rows == [
        (_digest("d"), "cancelled", "superseded-by-tracking-policy"),
        (_digest("e"), "pending", None),
    ]
