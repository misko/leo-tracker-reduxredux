from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from leo.catalog import InvalidStateError, LeaseLostError


def _enqueue(harness, key: str, kind: str = "scheduled_recording"):
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    return harness.repository.enqueue_acquisition_operation(
        operation_key=key,
        kind=kind,
        payload={"profile_name": "live-60s", "radio_ids": ["radio-a", "radio-b"]},
        scheduled_for=due,
    )


def test_cadence_enqueue_is_idempotent_and_conflicts_fail_closed(catalog_harness) -> None:
    first = _enqueue(catalog_harness, "dwell:20260821T080000Z")
    repeated = _enqueue(catalog_harness, "dwell:20260821T080000Z")

    assert repeated.operation_id == first.operation_id
    assert repeated.state == "pending"
    with pytest.raises(InvalidStateError, match="different intent"):
        catalog_harness.repository.enqueue_acquisition_operation(
            operation_key="dwell:20260821T080000Z",
            kind="scanner_sweep",
            payload={},
            scheduled_for=first.scheduled_for,
        )


def test_coalesced_cadence_keeps_only_newest_pending_intent(catalog_harness) -> None:
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    for offset in range(3):
        catalog_harness.repository.enqueue_acquisition_operation(
            operation_key=f"dwell:{offset}",
            kind="scheduled_recording",
            payload={"slot": offset},
            scheduled_for=due + timedelta(minutes=offset),
            coalesce_pending_kind=True,
        )
        catalog_harness.repository.enqueue_acquisition_operation(
            operation_key=f"scan:{offset}",
            kind="scanner_sweep",
            payload={"slot": offset},
            scheduled_for=due + timedelta(minutes=offset, microseconds=1),
            coalesce_pending_kind=True,
        )

    active = catalog_harness.repository.active_acquisition_operations()
    assert [(item.kind, item.operation_key) for item in active] == [
        ("scheduled_recording", "dwell:2"),
        ("scanner_sweep", "scan:2"),
    ]
    with catalog_harness.engine.connect() as connection:
        states = connection.execute(
            text(
                "SELECT kind, state, count(*) FROM acquisition_operation "
                "GROUP BY kind, state ORDER BY kind, state"
            )
        ).all()
    assert states == [
        ("scanner_sweep", "cancelled", 2),
        ("scanner_sweep", "pending", 1),
        ("scheduled_recording", "cancelled", 2),
        ("scheduled_recording", "pending", 1),
    ]


def test_coalesced_enqueue_is_race_safe(catalog_harness) -> None:
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)

    def enqueue(offset: int):
        return catalog_harness.repository.enqueue_acquisition_operation(
            operation_key=f"dwell:race:{offset}",
            kind="scheduled_recording",
            payload={"slot": offset},
            scheduled_for=due + timedelta(seconds=offset),
            coalesce_pending_kind=True,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        tuple(pool.map(enqueue, range(8)))

    active = catalog_harness.repository.active_acquisition_operations()
    assert len(active) == 1
    assert active[0].kind == "scheduled_recording"
    assert active[0].operation_key == "dwell:race:7"


def test_late_or_retried_old_cadence_cannot_replace_newer_pending(catalog_harness) -> None:
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    old = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:old",
        kind="scheduled_recording",
        payload={"slot": "old"},
        scheduled_for=due,
        coalesce_pending_kind=True,
    )
    newest = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:new",
        kind="scheduled_recording",
        payload={"slot": "new"},
        scheduled_for=due + timedelta(minutes=3),
        coalesce_pending_kind=True,
    )
    late = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:late",
        kind="scheduled_recording",
        payload={"slot": "late"},
        scheduled_for=due + timedelta(minutes=1),
        coalesce_pending_kind=True,
    )
    retried = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:old",
        kind="scheduled_recording",
        payload={"slot": "old"},
        scheduled_for=due,
        coalesce_pending_kind=True,
    )

    assert old.state == "pending"
    assert newest.state == "pending"
    assert late.state == "cancelled"
    assert retried.state == "cancelled"
    active = catalog_harness.repository.active_acquisition_operations()
    assert [(item.kind, item.operation_key) for item in active] == [
        ("scheduled_recording", "dwell:new")
    ]


def test_two_workers_can_never_claim_radio_operations_concurrently(catalog_harness) -> None:
    _enqueue(catalog_harness, "dwell:one")
    _enqueue(catalog_harness, "scan:one", "scanner_sweep")

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = tuple(
            pool.map(
                lambda worker: catalog_harness.repository.claim_acquisition_operation(
                    worker_id=worker,
                    lease_for=timedelta(minutes=2),
                ),
                ("worker-a", "worker-b"),
            )
        )

    assert sum(lease is not None for lease in leases) == 1
    assert len(catalog_harness.repository.active_acquisition_operations()) == 2


def test_kind_filtered_claim_skips_other_pending_work_but_keeps_global_mutex(
    catalog_harness,
) -> None:
    dwell = _enqueue(catalog_harness, "dwell:older")
    scan = _enqueue(catalog_harness, "scan:newer", "scanner_sweep")

    visible = catalog_harness.repository.active_acquisition_operations(
        kinds=("scanner_sweep",),
    )
    scanner_lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="scanner-canary",
        lease_for=timedelta(minutes=2),
        kinds=("scanner_sweep",),
    )

    assert [item.operation_id for item in visible] == [scan.operation_id]
    assert scanner_lease is not None
    assert scanner_lease.operation_id == scan.operation_id
    assert (
        catalog_harness.repository.claim_acquisition_operation(
            worker_id="ordinary-worker",
            lease_for=timedelta(minutes=2),
            kinds=("scheduled_recording",),
        )
        is None
    )

    catalog_harness.repository.complete_acquisition_operation(
        operation_id=scan.operation_id,
        worker_id="scanner-canary",
        outcome="scanner canary complete",
    )
    dwell_lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="ordinary-worker",
        lease_for=timedelta(minutes=2),
        kinds=("scheduled_recording",),
    )
    assert dwell_lease is not None
    assert dwell_lease.operation_id == dwell.operation_id


def test_empty_acquisition_operation_kind_filter_is_rejected(catalog_harness) -> None:
    with pytest.raises(ValueError, match="kind filter cannot be empty"):
        catalog_harness.repository.active_acquisition_operations(kinds=())
    with pytest.raises(ValueError, match="kind filter cannot be empty"):
        catalog_harness.repository.claim_acquisition_operation(
            worker_id="worker",
            lease_for=timedelta(minutes=1),
            kinds=(),
        )


def test_expired_lease_is_recovered_without_dropping_the_intent(catalog_harness) -> None:
    operation = _enqueue(catalog_harness, "dwell:recover")
    lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="dead-worker", lease_for=timedelta(microseconds=1)
    )
    assert lease is not None

    reclaimed = catalog_harness.repository.reclaim_expired_acquisition_operations(
        as_of=datetime.now(UTC) + timedelta(seconds=1)
    )
    replacement = catalog_harness.repository.claim_acquisition_operation(
        worker_id="replacement", lease_for=timedelta(minutes=1)
    )

    assert reclaimed == (operation.operation_id,)
    assert replacement is not None
    assert replacement.operation_id == operation.operation_id
    assert replacement.attempt_number == 2


def test_expired_older_leased_cadence_yields_to_newer_pending_without_reclaim_loop(
    catalog_harness,
) -> None:
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    old = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:expired-old",
        kind="scheduled_recording",
        payload={"slot": "old"},
        scheduled_for=due,
        coalesce_pending_kind=True,
    )
    old_lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="expired-worker",
        lease_for=timedelta(microseconds=1),
    )
    assert old_lease is not None and old_lease.operation_id == old.operation_id
    newest = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:newest-pending",
        kind="scheduled_recording",
        payload={"slot": "newest"},
        scheduled_for=due + timedelta(minutes=1),
        coalesce_pending_kind=True,
    )

    reclaimed = catalog_harness.repository.reclaim_expired_acquisition_operations(
        as_of=old_lease.lease_expires_at + timedelta(seconds=1)
    )
    active = catalog_harness.repository.active_acquisition_operations()

    assert reclaimed == (old.operation_id,)
    assert [(item.operation_key, item.state, item.payload) for item in active] == [
        ("dwell:newest-pending", "pending", {"slot": "newest"})
    ]
    assert (
        catalog_harness.repository.reclaim_expired_acquisition_operations(
            as_of=old_lease.lease_expires_at + timedelta(seconds=2)
        )
        == ()
    )

    selected = catalog_harness.repository.claim_acquisition_operation(
        worker_id="replacement",
        lease_for=timedelta(minutes=1),
    )
    assert selected is not None
    assert selected.operation_id == newest.operation_id
    assert selected.operation_key == "dwell:newest-pending"
    assert selected.payload == {"slot": "newest"}
    assert selected.scheduled_for == due + timedelta(minutes=1)

    with catalog_harness.engine.connect() as connection:
        old_row = connection.execute(
            text(
                "SELECT state, lease_owner, lease_expires_at, outcome "
                "FROM acquisition_operation WHERE id=:operation_id"
            ),
            {"operation_id": old.operation_id},
        ).one()
    assert old_row == (
        "cancelled",
        None,
        None,
        "superseded by newer scheduled_recording intent dwell:newest-pending",
    )


def test_expired_newer_leased_cadence_cancels_older_pending_before_requeue(
    catalog_harness,
) -> None:
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    newest = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:expired-newest",
        kind="scheduled_recording",
        payload={"slot": "newest"},
        scheduled_for=due + timedelta(minutes=2),
        coalesce_pending_kind=True,
    )
    newest_lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="expired-worker",
        lease_for=timedelta(microseconds=1),
    )
    assert newest_lease is not None and newest_lease.operation_id == newest.operation_id
    older_pending = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:older-pending",
        kind="scheduled_recording",
        payload={"slot": "older"},
        scheduled_for=due + timedelta(minutes=1),
        coalesce_pending_kind=True,
    )

    reclaimed = catalog_harness.repository.reclaim_expired_acquisition_operations(
        as_of=newest_lease.lease_expires_at + timedelta(seconds=1)
    )
    active = catalog_harness.repository.active_acquisition_operations()

    assert reclaimed == (newest.operation_id,)
    assert [(item.operation_key, item.state, item.payload) for item in active] == [
        ("dwell:expired-newest", "pending", {"slot": "newest"})
    ]
    selected = catalog_harness.repository.claim_acquisition_operation(
        worker_id="replacement",
        lease_for=timedelta(minutes=1),
    )
    assert selected is not None
    assert selected.operation_id == newest.operation_id
    assert selected.operation_key == "dwell:expired-newest"
    assert selected.payload == {"slot": "newest"}
    assert selected.scheduled_for == due + timedelta(minutes=2)
    assert selected.attempt_number == 2

    with catalog_harness.engine.connect() as connection:
        older_row = connection.execute(
            text("SELECT state, outcome FROM acquisition_operation WHERE id=:operation_id"),
            {"operation_id": older_pending.operation_id},
        ).one()
    assert older_row == (
        "cancelled",
        "superseded by newer scheduled_recording intent dwell:expired-newest",
    )


def test_retryable_failure_of_older_cadence_yields_to_newer_pending(
    catalog_harness,
) -> None:
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    old = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:retry-old",
        kind="scheduled_recording",
        payload={"slot": "old"},
        scheduled_for=due,
        coalesce_pending_kind=True,
    )
    old_lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="retry-worker",
        lease_for=timedelta(minutes=1),
    )
    assert old_lease is not None and old_lease.operation_id == old.operation_id
    newest = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="dwell:retry-newest",
        kind="scheduled_recording",
        payload={"slot": "newest"},
        scheduled_for=due + timedelta(minutes=1),
        coalesce_pending_kind=True,
    )

    state = catalog_harness.repository.fail_acquisition_operation(
        operation_id=old.operation_id,
        worker_id="retry-worker",
        error="radio temporarily busy",
        retryable=True,
        retry_after=timedelta(seconds=30),
    )
    active = catalog_harness.repository.active_acquisition_operations()

    assert state == "cancelled"
    assert [(item.operation_key, item.state, item.payload) for item in active] == [
        ("dwell:retry-newest", "pending", {"slot": "newest"})
    ]
    selected = catalog_harness.repository.claim_acquisition_operation(
        worker_id="replacement",
        lease_for=timedelta(minutes=1),
    )
    assert selected is not None
    assert selected.operation_id == newest.operation_id
    assert selected.operation_key == "dwell:retry-newest"
    assert selected.payload == {"slot": "newest"}
    assert selected.scheduled_for == due + timedelta(minutes=1)

    with catalog_harness.engine.connect() as connection:
        old_row = connection.execute(
            text(
                "SELECT state, lease_owner, lease_expires_at, error, outcome "
                "FROM acquisition_operation WHERE id=:operation_id"
            ),
            {"operation_id": old.operation_id},
        ).one()
    assert old_row == (
        "cancelled",
        None,
        None,
        None,
        "superseded by newer scheduled_recording intent dwell:retry-newest",
    )


def test_completion_releases_global_owner_and_prioritizes_a_due_scanner(
    catalog_harness,
) -> None:
    dwell = _enqueue(catalog_harness, "dwell:alternate")
    due = datetime(2026, 8, 21, 8, 20, tzinfo=UTC)
    scan = catalog_harness.repository.enqueue_acquisition_operation(
        operation_key="scan:alternate",
        kind="scanner_sweep",
        payload={"slot": "scanner"},
        scheduled_for=due,
        priority=1,
    )
    first = catalog_harness.repository.claim_acquisition_operation(
        worker_id="supervisor", lease_for=timedelta(minutes=1)
    )
    assert first is not None and first.operation_id == scan.operation_id

    catalog_harness.repository.complete_acquisition_operation(
        operation_id=first.operation_id,
        worker_id="supervisor",
        outcome="capture committed",
    )
    second = catalog_harness.repository.claim_acquisition_operation(
        worker_id="supervisor", lease_for=timedelta(minutes=1)
    )
    assert second is not None and second.operation_id == dwell.operation_id


def test_stale_worker_cannot_complete_recovered_operation(catalog_harness) -> None:
    _enqueue(catalog_harness, "dwell:fence")
    stale = catalog_harness.repository.claim_acquisition_operation(
        worker_id="stale", lease_for=timedelta(microseconds=1)
    )
    assert stale is not None
    catalog_harness.repository.reclaim_expired_acquisition_operations(
        as_of=datetime.now(UTC) + timedelta(seconds=1)
    )
    with pytest.raises(LeaseLostError):
        catalog_harness.repository.complete_acquisition_operation(
            operation_id=stale.operation_id,
            worker_id="stale",
            outcome="must not publish",
        )
